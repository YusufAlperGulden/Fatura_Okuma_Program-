import json
import os
from decimal import Decimal
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from integrators.uyumsoft_api import (
    UyumsoftResult,
    build_invoice_info_body,
    build_ubl_invoice,
    send_invoice_to_uyumsoft,
)
from validators.invoice_validator import validate_invoice


def _invoice(**overrides):
    invoice = {
        "invoice_no": "REGRESSION-1",
        "date": "17.07.2026",
        "time": "10:15",
        "customer_tax_id": "1234567890",
        "customer_name": "Regression Customer",
        "items": [
            {
                "code": "SKU-1",
                "description": "Regression Item",
                "quantity": "1",
                "unit_price": "100,00",
                "total_price": "100,00",
                "tax_rate": "20",
            }
        ],
        "subtotal": "100,00",
        "discount_amount": "0,00",
        "tax_amount": "20,00",
        "total_amount": "120,00",
        "currency": "TRY",
    }
    invoice.update(overrides)
    return invoice


def _local_values(xml_text, local_name):
    root = ET.fromstring(xml_text)
    return [
        element.text
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == local_name
    ]


def _nodes(root, local_name):
    return [
        node
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == local_name
    ]


def test_three_and_four_decimal_values_keep_their_numeric_meaning_and_precision():
    invoice = _invoice(
        items=[
            {
                "code": "FRACTION",
                "description": "Fractional quantity",
                "quantity": "0,125",
                "unit_price": "800,0000",
                "total_price": "100,00",
                "tax_rate": "20",
            }
        ]
    )

    assert validate_invoice(invoice) == (True, [])
    root = ET.fromstring(build_ubl_invoice(invoice))

    assert Decimal(_nodes(root, "InvoicedQuantity")[0].text) == Decimal("0.125")
    assert Decimal(_nodes(root, "PriceAmount")[0].text) == Decimal("800")

    precision_invoice = _invoice(
        items=[
            {
                "code": "PRECISION",
                "description": "Precise unit price",
                "quantity": "3",
                "unit_price": "0,3333",
                "total_price": "1,00",
                "tax_rate": "20",
            }
        ],
        subtotal="1,00",
        tax_amount="0,20",
        total_amount="1,20",
    )
    assert validate_invoice(precision_invoice) == (True, [])
    precision_root = ET.fromstring(build_ubl_invoice(precision_invoice))
    assert Decimal(_nodes(precision_root, "PriceAmount")[0].text) == Decimal("0.3333")


def test_gbp_is_preserved_and_unknown_currency_is_rejected():
    gbp = _invoice(currency="GBP", exchange_rate="44,5959")
    assert validate_invoice(gbp) == (True, [])
    root = ET.fromstring(build_ubl_invoice(gbp))
    assert _nodes(root, "DocumentCurrencyCode")[0].text == "GBP"
    assert Decimal(_nodes(root, "CalculationRate")[0].text) == Decimal("44.5959")

    unsupported = _invoice(currency="CHF", exchange_rate="40")
    is_valid, errors = validate_invoice(unsupported)
    assert is_valid is False
    assert any("para birimi" in error.lower() for error in errors)
    with pytest.raises(ValueError, match="currency"):
        build_ubl_invoice(unsupported)


def test_foreign_currency_rate_lookup_failure_stops_the_draft():
    invoice = _invoice(currency="USD", exchange_rate=None)

    with patch("integrators.uyumsoft_api.get_tcmb_rate", return_value=None):
        with pytest.raises(ValueError, match="exchange rate"):
            build_ubl_invoice(invoice)


def test_header_difference_beyond_configured_tolerance_is_rejected():
    invoice = _invoice(tax_amount="21,01", total_amount="121,01")

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("KDV" in error for error in errors)
    assert invoice["tax_amount"] == "21,01"
    assert invoice["total_amount"] == "121,01"


def test_one_lira_document_difference_is_accepted_by_business_rule():
    invoice = _invoice(tax_amount="21,00", total_amount="121,00")

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is True
    assert errors == []


def test_send_uses_server_owned_supplier_identity_not_payload_values():
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def save_as_draft_data(self, invoice):
            captured.update(invoice)
            return UyumsoftResult(True, "OK", 200, "SaveAsDraft", [], "<ok />")

    injected = _invoice(
        supplier_tax_id="1111111111",
        supplier_name="Injected Seller",
        supplier_tax_office="Injected Office",
    )
    environment = {
        "UYUMSOFT_ENV": "prod",
        "UYUMSOFT_USERNAME": "real-user",
        "UYUMSOFT_PASSWORD": "real-password",
        "UYUMSOFT_SUPPLIER_VKN": "99-99999999",
        "UYUMSOFT_SUPPLIER_NAME": "Configured Seller",
        "UYUMSOFT_SUPPLIER_TAX_OFFICE": "Configured Office",
    }

    with (
        patch.dict(os.environ, environment, clear=True),
        patch("integrators.uyumsoft_api.UyumsoftSoapClient", FakeClient),
    ):
        result = send_invoice_to_uyumsoft(injected, action="draft")

    assert result["success"] is True
    assert captured["supplier_tax_id"] == "9999999999"
    assert captured["supplier_name"] == "Configured Seller"
    assert captured["supplier_tax_office"] == "Configured Office"


def test_discounted_line_taxes_sum_to_document_tax():
    invoice = _invoice(
        discount_amount="10,00",
        tax_amount="18,00",
        total_amount="108,00",
    )
    assert validate_invoice(invoice) == (True, [])
    root = ET.fromstring(build_ubl_invoice(invoice))
    document_tax_total = next(
        child for child in root if child.tag.rsplit("}", 1)[-1] == "TaxTotal"
    )
    document_tax = Decimal(
        next(
            child.text
            for child in document_tax_total
            if child.tag.rsplit("}", 1)[-1] == "TaxAmount"
        )
    )
    line_taxes = []
    for line in _nodes(root, "InvoiceLine"):
        line_tax_total = next(
            child for child in line if child.tag.rsplit("}", 1)[-1] == "TaxTotal"
        )
        line_taxes.append(
            Decimal(
                next(
                    child.text
                    for child in line_tax_total
                    if child.tag.rsplit("}", 1)[-1] == "TaxAmount"
                )
            )
        )

    assert document_tax == Decimal("18.00")
    assert sum(line_taxes) == document_tax


def test_customer_alias_is_emitted_only_for_the_vkn_it_was_resolved_for():
    stale = _invoice(
        customer_tax_id="2222222222",
        customer_alias="urn:mail:old@example.test",
        customer_alias_tax_id="1111111111",
    )
    stale_body = build_invoice_info_body("SaveAsDraft", stale)
    assert 'Alias="urn:mail:old@example.test"' not in stale_body

    current = _invoice(
        customer_alias="urn:mail:current@example.test",
        customer_alias_tax_id="1234567890",
    )
    current_body = build_invoice_info_body("SaveAsDraft", current)
    assert 'Alias="urn:mail:current@example.test"' in current_body


def test_malformed_items_returns_validation_errors_instead_of_crashing():
    invoice = _invoice(items=1)

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("kalem" in error.lower() for error in errors)


def test_serial_count_must_match_integral_item_quantity():
    invoice = _invoice()
    invoice["items"][0]["serial_numbers"] = ["SERIAL-1", "SERIAL-2"]

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("seri numarası adedi" in error for error in errors)


def test_uyumsoft_builder_honors_one_lira_tolerance_with_canonical_xml_totals():
    invoice = _invoice(tax_amount="20,50", total_amount="120,50")

    assert validate_invoice(invoice) == (True, [])
    xml_text = build_ubl_invoice(invoice)

    assert _local_values(xml_text, "PayableAmount") == ["120.00"]
    assert set(_local_values(xml_text, "TaxAmount")) == {"20.00"}


def test_invalid_vkn_checksum_is_rejected_before_uyumsoft():
    invoice = _invoice(customer_tax_id="1234567891")

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("kontrol basamağı" in error for error in errors)


def test_item_name_fallback_is_consistent_in_validator_and_ubl_builder():
    invoice = _invoice()
    invoice["items"][0]["description"] = None
    invoice["items"][0]["name"] = "Fallback ürün"

    assert validate_invoice(invoice) == (True, [])
    xml_text = build_ubl_invoice(invoice)

    assert "<cbc:Name>Fallback ürün</cbc:Name>" in xml_text

def test_10_digit_vkn_checksum_verification():
    invoice = _invoice(customer_tax_id="1234567891")
    is_valid, errors = validate_invoice(invoice)
    assert is_valid is False
    assert any("kontrol basamağı" in error.lower() for error in errors)

def test_vkn_strip_persists_in_data():
    invoice = _invoice(customer_tax_id=" 1111111111 ")
    validate_invoice(invoice)
    assert invoice["customer_tax_id"] == "1111111111"

def test_turkish_lira_uppercase_mapping():
    from utils.invoice_values import parse_localized_decimal
    assert parse_localized_decimal("10,00 Türk Lirası") == Decimal("10.00")

def test_uyumsoft_uuid_idempotency():
    invoice = _invoice()
    xml1 = build_ubl_invoice(invoice)
    xml2 = build_ubl_invoice(invoice)
    uuid1 = _local_values(xml1, "UUID")[0]
    uuid2 = _local_values(xml2, "UUID")[0]
    assert uuid1 == uuid2

def test_gemini_fallback_preserves_local_errors_if_ai_fails():
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    with patch("api.parse_pdf_invoice") as mock_local, \
         patch("extractors.ai_extractor.extract_invoice_with_ai") as mock_ai, \
         patch.dict("os.environ", {"GEMINI_API_KEY": "dummy"}):
        
        mock_local.return_value = _invoice(tax_amount="21,01", total_amount="121,01")
        mock_ai.return_value = {}
        
        response = client.post("/upload", files={"file": ("test.pdf", b"dummy content", "application/pdf")})
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert data["data"] is not None
        assert data["data"]["tax_amount"] == "21,01"

