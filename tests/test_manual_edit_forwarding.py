import asyncio
import os
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from api import SendUyumsoftRequest, api_validate, runtime_config, send_uyumsoft_api
from integrators.uyumsoft_api import (
    PROD_ENDPOINT,
    TEST_ENDPOINT,
    UyumsoftSoapClient,
    build_invoice_info_body,
    send_invoice_to_uyumsoft,
)
from validators.invoice_validator import recalculate_invoice_totals, validate_invoice


def _invoice():
    return {
        "invoice_no": "EDIT-2026-77",
        "date": "17.07.2026",
        "time": "09:05",
        "customer_tax_id": "1234567890",
        "customer_name": "Düzenlenmiş Müşteri A.Ş.",
        "customer_title": "Eski Müşteri A.Ş.",
        "items": [
            {
                "code": "EDIT-CODE",
                "description": "Düzenlenmiş ürün",
                "serial_numbers": [
                    "SERIAL-EDIT-1",
                    "SERIAL-EDIT-2",
                    "SERIAL-EDIT-3",
                ],
                "quantity": "3",
                "unit_price": "25,00",
                "tax_rate": "10",
                "total_price": "75,00",
            }
        ],
        "subtotal": "75,00",
        "discount_amount": "0,00",
        "tax_amount": "7,50",
        "total_amount": "82,50",
        "currency": "TRY",
    }


def _local_values(xml_text, local_name):
    root = ET.fromstring(xml_text)
    return [
        element.text
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == local_name
    ]


def test_send_endpoint_preserves_every_editable_field_and_forces_draft():
    success = {"success": True, "message": "Taslak oluşturuldu", "response_code": 200}
    request = SendUyumsoftRequest(invoice_data=_invoice(), action="send")

    with patch("api.send_invoice_to_uyumsoft", return_value=success) as sender:
        result = asyncio.run(send_uyumsoft_api(request))

    sender.assert_called_once()
    sent = sender.call_args.args[0]
    assert sender.call_args.kwargs == {"action": "draft"}
    assert result == success
    assert sent["invoice_no"] == "EDIT-2026-77"
    assert sent["date"] == "17.07.2026"
    assert sent["time"] == "09:05:00"
    assert sent["customer_tax_id"] == "1234567890"
    assert sent["customer_name"] == "Düzenlenmiş Müşteri A.Ş."
    assert sent["customer_title"] == sent["customer_name"]
    assert sent["items"][0] == {
        "code": "EDIT-CODE",
        "description": "Düzenlenmiş ürün",
        "serial_numbers": [
            "SERIAL-EDIT-1",
            "SERIAL-EDIT-2",
            "SERIAL-EDIT-3",
        ],
        "quantity": "3",
        "unit_price": "25,00",
        "tax_rate": "10",
        "total_price": "75,00",
    }


def test_every_edited_value_round_trips_into_uyumsoft_xml():
    body = build_invoice_info_body("SaveAsDraft", _invoice())

    assert 'LocalDocumentId="EDIT-2026-77"' in body
    assert 'VknTckn="1234567890"' in body
    assert 'Title="Düzenlenmiş Müşteri A.Ş."' in body
    assert "<cbc:IssueDate>2026-07-17</cbc:IssueDate>" in body
    assert "<cbc:IssueTime>09:05:00</cbc:IssueTime>" in body
    assert "<cbc:Name>Düzenlenmiş Müşteri A.Ş.</cbc:Name>" in body
    assert "<cbc:Name>Düzenlenmiş ürün</cbc:Name>" in body
    assert "<cbc:ID>EDIT-CODE</cbc:ID>" in body
    assert "<cbc:SerialID>SERIAL-EDIT-1</cbc:SerialID>" in body
    assert "<cbc:InvoicedQuantity unitCode=\"C62\">3</cbc:InvoicedQuantity>" in body
    assert "<cbc:PriceAmount currencyID=\"TRY\">25.00</cbc:PriceAmount>" in body
    assert "<cbc:LineExtensionAmount currencyID=\"TRY\">75.00</cbc:LineExtensionAmount>" in body
    assert "10.00" in _local_values(body, "Percent")
    assert "7.50" in _local_values(body, "TaxAmount")
    assert "82.50" in _local_values(body, "PayableAmount")


def test_kdv_edit_requires_coherent_totals_and_never_sends_stale_header():
    stale = _invoice()
    stale["items"][0]["tax_rate"] = "20"

    with patch("api.send_invoice_to_uyumsoft") as sender:
        result = asyncio.run(
            send_uyumsoft_api(SendUyumsoftRequest(invoice_data=stale, action="draft"))
        )

    sender.assert_not_called()
    import json
    result_data = json.loads(result.body.decode("utf-8")) if hasattr(result, "body") else result
    assert result_data["success"] is False
    assert result_data["response_code"] == 400
    assert any("KDV" in error for error in result_data["details"])

    recalculate_invoice_totals(stale)
    assert validate_invoice(stale) == (True, [])
    body = build_invoice_info_body("SaveAsDraft", stale)
    assert "15.00" in _local_values(body, "TaxAmount")
    assert "90.00" in _local_values(body, "PayableAmount")


@pytest.mark.parametrize(
    ("scope", "field", "value"),
    [
        ("invoice", "time", "25:61"),
        ("item", "description", ""),
        ("item", "quantity", "abc"),
        ("item", "quantity", "0"),
        ("item", "unit_price", "abc"),
        ("item", "total_price", "abc"),
        ("item", "tax_rate", ""),
        ("item", "tax_rate", "101"),
    ],
)
def test_invalid_manual_edits_never_reach_uyumsoft(scope, field, value):
    invoice = _invoice()
    target = invoice if scope == "invoice" else invoice["items"][0]
    target[field] = value

    with patch("api.send_invoice_to_uyumsoft") as sender:
        result = asyncio.run(
            send_uyumsoft_api(
                SendUyumsoftRequest(invoice_data=invoice, action="draft")
            )
        )

    sender.assert_not_called()
    import json
    result_data = json.loads(result.body.decode("utf-8")) if hasattr(result, "body") else result
    assert result_data["success"] is False
    assert result_data["response_code"] == 400


def test_invalid_numeric_edit_is_not_silently_replaced_with_zero():
    invoice = _invoice()
    invoice["items"][0]["quantity"] = "abc"

    result = asyncio.run(api_validate(invoice))

    assert result["is_valid"] is False
    assert result["data"]["items"][0]["quantity"] == "abc"


def test_missing_rate_is_inferred_but_blank_and_explicit_zero_stay_distinct():
    missing = _invoice()
    missing["items"][0]["tax_rate"] = None
    assert validate_invoice(missing) == (True, [])
    assert missing["items"][0]["tax_rate"] == "10"

    blank = _invoice()
    blank["items"][0]["tax_rate"] = ""
    is_valid, errors = validate_invoice(blank)
    assert is_valid is False
    assert any("KDV oranı" in error for error in errors)

    zero = _invoice()
    zero["items"][0]["tax_rate"] = 0
    zero["tax_amount"] = "0,00"
    zero["total_amount"] = "75,00"
    assert validate_invoice(zero) == (True, [])
    body = build_invoice_info_body("SaveAsDraft", zero)
    assert "0.00" in _local_values(body, "Percent")
    assert "75.00" in _local_values(body, "PayableAmount")


def test_blank_optional_time_and_code_are_omitted_not_invented():
    invoice = _invoice()
    invoice["time"] = ""
    invoice["items"][0]["code"] = ""

    body = build_invoice_info_body("SaveAsDraft", invoice)

    assert "<cbc:IssueTime>" not in body
    assert "<cac:SellersItemIdentification>" not in body
    assert 'LocalDocumentId="EDIT-2026-77"' in body


def test_discount_rounding_keeps_taxable_groups_equal_to_document_taxable():
    invoice = _invoice()
    invoice["items"] = [
        {"description": "A", "quantity": "1", "unit_price": "100", "total_price": "100", "tax_rate": "10"},
        {"description": "B", "quantity": "1", "unit_price": "100", "total_price": "100", "tax_rate": "20"},
    ]
    invoice.update(
        subtotal="200,00",
        discount_amount="0,01",
        tax_amount="30,00",
        total_amount="229,99",
    )

    body = build_invoice_info_body("SaveAsDraft", invoice)
    root = ET.fromstring(body)
    document_tax_total = next(
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "TaxTotal"
    )
    taxable_values = [
        element.text
        for element in document_tax_total.iter()
        if element.tag.rsplit("}", 1)[-1] == "TaxableAmount"
    ]

    assert sum(map(float, taxable_values)) == pytest.approx(199.99)
    assert "199.99" in _local_values(body, "TaxExclusiveAmount")
    assert "229.99" in _local_values(body, "PayableAmount")


def test_runtime_config_and_soap_client_use_the_same_normalized_environment():
    with patch.dict(
        os.environ,
        {
            "UYUMSOFT_ENV": " PROD ",
            "UYUMSOFT_PORTAL_URL": "https://portal.example.invalid/Taslak",
        },
        clear=False,
    ):
        config = runtime_config()
        client = UyumsoftSoapClient("user", "password", environment=" PROD ")

    assert config == {
        "uyumsoft_environment": "prod",
        "uyumsoft_portal_url": "https://portal.example.invalid/Taslak",
    }
    assert client.endpoint == PROD_ENDPOINT
    assert "username" not in config
    assert "password" not in config

    with patch.dict(os.environ, {"UYUMSOFT_ENV": "unknown"}, clear=False):
        assert runtime_config()["uyumsoft_environment"] == "test"
        assert UyumsoftSoapClient("u", "p", environment="unknown").endpoint == TEST_ENDPOINT


def test_production_send_requires_real_supplier_configuration_before_network():
    with patch.dict(
        os.environ,
        {
            "UYUMSOFT_ENV": "prod",
            "UYUMSOFT_USERNAME": "real-user",
            "UYUMSOFT_PASSWORD": "real-password",
        },
        clear=True,
    ):
        result = send_invoice_to_uyumsoft(_invoice(), action="draft")

    assert result["success"] is False
    if result["response_code"] != 422:
        print("RESULT IS", result)
    assert result["response_code"] == 422
    assert "işyeri bilgileri eksik" in result["message"]


def test_comma_decimal_exchange_rate_is_preserved():
    invoice = _invoice()
    invoice["currency"] = "USD"
    invoice["exchange_rate"] = "40,2000"

    body = build_invoice_info_body("SaveAsDraft", invoice)

    assert "<cbc:CalculationRate>40.2000</cbc:CalculationRate>" in body
