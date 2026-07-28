import asyncio
from decimal import Decimal
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from api import SendUyumsoftRequest, send_uyumsoft_api
from integrators.uyumsoft_api import build_ubl_invoice
from validators.invoice_validator import validate_invoice


def _usd_invoice():
    return {
        "invoice_no": "USD-PIPELINE-1",
        "date": "28.07.2026",
        "time": "10:33:05",
        "customer_tax_id": "11111111111",
        "customer_name": "Mufemu Dijital Reklam Ve Promosyon",
        # TRY is a stale legacy default. The explicit settlement/document
        # markers must make this a USD document.
        "currency": "TRY",
        "document_currency": "USD",
        "settlement_currency": "USD",
        "accounting_currency": "TRY",
        "exchange_rate": "47,0517",
        "subtotal": "3.840,00",
        "tax_amount": "768,00",
        "total_amount": "4.608,00",
        "foreign_total": "4.608,00",
        "local_subtotal": "180.678,53",
        "local_tax_amount": "36.135,71",
        "local_total": "216.814,23",
        "items": [
            {
                "code": "4100.0382",
                "description": "NXP Mifare Desfire EV1 4K - PVC Kart CR80",
                "quantity": "2.000,00",
                "unit_price": "1,92",
                "total_price": "3.840,00",
                "local_unit_price": "90,34",
                "local_total_price": "180.678,53",
                "tax_rate": "20",
            }
        ],
    }


def _children(node, local_name):
    return [
        child
        for child in node
        if child.tag.rsplit("}", 1)[-1] == local_name
    ]


def _descendants(node, local_name):
    return [
        child
        for child in node.iter()
        if child.tag.rsplit("}", 1)[-1] == local_name
    ]


def test_validator_canonicalizes_dual_currency_without_losing_try_metadata():
    invoice = _usd_invoice()

    assert validate_invoice(invoice) == (True, [])
    assert invoice["currency"] == "USD"
    assert invoice["document_currency"] == "USD"
    assert invoice["settlement_currency"] == "USD"
    assert invoice["accounting_currency"] == "TRY"
    assert invoice["local_subtotal"] == "180.678,53"
    assert invoice["local_tax_amount"] == "36.135,71"
    assert invoice["local_total"] == "216.814,23"


def test_uyumsoft_ubl_uses_usd_values_once_and_keeps_try_accounting_tax():
    invoice = _usd_invoice()
    root = ET.fromstring(build_ubl_invoice(invoice))

    assert _descendants(root, "DocumentCurrencyCode")[0].text == "USD"
    assert _descendants(root, "SourceCurrencyCode")[0].text == "USD"
    assert _descendants(root, "TargetCurrencyCode")[0].text == "TRY"
    assert Decimal(_descendants(root, "CalculationRate")[0].text) == Decimal(
        "47.0517"
    )

    invoice_line = _descendants(root, "InvoiceLine")[0]
    line_extension = _children(invoice_line, "LineExtensionAmount")[0]
    price = _descendants(invoice_line, "PriceAmount")[0]
    assert line_extension.attrib["currencyID"] == "USD"
    assert Decimal(line_extension.text) == Decimal("3840.00")
    assert price.attrib["currencyID"] == "USD"
    assert Decimal(price.text) == Decimal("1.92")

    legal_total = _descendants(root, "LegalMonetaryTotal")[0]
    legal_values = {
        child.tag.rsplit("}", 1)[-1]: (
            child.attrib.get("currencyID"),
            Decimal(child.text),
        )
        for child in legal_total
    }
    assert legal_values["LineExtensionAmount"] == ("USD", Decimal("3840.00"))
    assert legal_values["TaxExclusiveAmount"] == ("USD", Decimal("3840.00"))
    assert legal_values["TaxInclusiveAmount"] == ("USD", Decimal("4608.00"))
    assert legal_values["PayableAmount"] == ("USD", Decimal("4608.00"))

    top_level_tax_totals = _children(root, "TaxTotal")
    top_level_tax_amounts = [
        _children(tax_total, "TaxAmount")[0] for tax_total in top_level_tax_totals
    ]
    assert [
        (amount.attrib["currencyID"], Decimal(amount.text))
        for amount in top_level_tax_amounts
    ] == [
        ("USD", Decimal("768.00")),
        ("TRY", Decimal("36135.71")),
    ]

    usd_values = [
        Decimal(node.text)
        for node in root.iter()
        if node.attrib.get("currencyID") == "USD" and node.text
    ]
    assert Decimal("180678.53") not in usd_values
    assert Decimal("216814.23") not in usd_values


def test_send_endpoint_passes_the_canonical_usd_invoice_to_uyumsoft():
    invoice = _usd_invoice()
    result = {
        "success": True,
        "message": "Taslak oluşturuldu",
        "response_code": 200,
        "document_id": "DOC-USD-1",
    }

    with (
        patch("api.send_invoice_to_uyumsoft", return_value=result) as sender,
        patch("database.save_invoice"),
    ):
        response = asyncio.run(
            send_uyumsoft_api(
                SendUyumsoftRequest(invoice_data=invoice, action="draft")
            )
        )

    assert response == result
    sent = sender.call_args.args[0]
    assert sent["currency"] == "USD"
    assert sent["document_currency"] == "USD"
    assert sent["settlement_currency"] == "USD"
    assert sent["accounting_currency"] == "TRY"
    assert sent["total_amount"] == "4.608,00"
    assert sent["local_total"] == "216.814,23"


def test_validator_and_ubl_reject_possible_double_conversion():
    invoice = _usd_invoice()
    invoice["items"][0]["unit_price"] = "90,34"
    invoice["items"][0]["total_price"] = "180.678,53"
    invoice["subtotal"] = "180.678,53"
    invoice["tax_amount"] = "36.135,71"
    invoice["total_amount"] = "216.814,24"
    invoice["foreign_total"] = "216.814,24"
    invoice["local_total"] = "216.814,23"

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("kur üzerinden uyuşmuyor" in error for error in errors)
    with pytest.raises(ValueError, match="does not match"):
        build_ubl_invoice(invoice)


def test_conflicting_foreign_currency_markers_are_rejected():
    invoice = _usd_invoice()
    invoice["document_currency"] = "EUR"

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("para birimi" in error for error in errors)
    with pytest.raises(ValueError, match="conflicting foreign"):
        build_ubl_invoice(invoice)


def test_incomplete_usd_conversion_is_blocked_before_uyumsoft():
    invoice = _usd_invoice()
    invoice["fx_conversion_required"] = True
    invoice["exchange_rate"] = None

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("valid exchange rate" in error for error in errors)
    with pytest.raises(ValueError, match="conversion is incomplete"):
        build_ubl_invoice(invoice)


def test_tampered_local_tax_is_rejected_by_validator_and_ubl():
    invoice = _usd_invoice()
    invoice["local_tax_amount"] = "1,00"

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("local_tax_amount does not match" in error for error in errors)
    with pytest.raises(ValueError, match="local_tax_amount does not match"):
        build_ubl_invoice(invoice)


def test_discounted_try_tax_subtotal_uses_net_taxable_amount():
    invoice = _usd_invoice()
    invoice.update(
        exchange_rate="40,00",
        subtotal="100,00",
        discount_amount="10,00",
        tax_amount="18,00",
        total_amount="108,00",
        foreign_total="108,00",
        local_subtotal="4.000,00",
        local_discount_amount="400,00",
        local_tax_amount="720,00",
        local_total="4.320,00",
    )
    invoice["items"] = [
        {
            "description": "Discounted USD item",
            "quantity": "1",
            "unit_price": "100,00",
            "total_price": "100,00",
            "tax_rate": "20",
        }
    ]

    assert validate_invoice(invoice) == (True, [])
    root = ET.fromstring(build_ubl_invoice(invoice))
    try_tax_total = next(
        tax_total
        for tax_total in _children(root, "TaxTotal")
        if _children(tax_total, "TaxAmount")[0].attrib["currencyID"] == "TRY"
    )
    taxable = _descendants(try_tax_total, "TaxableAmount")[0]
    local_tax = _children(try_tax_total, "TaxAmount")[0]

    assert taxable.attrib["currencyID"] == "TRY"
    assert Decimal(taxable.text) == Decimal("3600.00")
    assert Decimal(local_tax.text) == Decimal("720.00")


def test_multi_rate_try_tax_subtotals_reconcile_to_local_tax_total():
    invoice = _usd_invoice()
    invoice.update(
        exchange_rate="47,0517",
        subtotal="0,55",
        discount_amount="0,00",
        tax_amount="0,10",
        total_amount="0,65",
        foreign_total="0,65",
        local_subtotal="25,88",
        local_discount_amount="0,00",
        local_tax_amount="4,71",
        local_total="30,58",
    )
    invoice["items"] = [
        {
            "description": "Ten percent",
            "quantity": "1",
            "unit_price": "0,10",
            "total_price": "0,10",
            "tax_rate": "10",
        },
        {
            "description": "Twenty percent",
            "quantity": "1",
            "unit_price": "0,45",
            "total_price": "0,45",
            "tax_rate": "20",
        },
    ]

    assert validate_invoice(invoice) == (True, [])
    root = ET.fromstring(build_ubl_invoice(invoice))
    try_tax_total = next(
        tax_total
        for tax_total in _children(root, "TaxTotal")
        if _children(tax_total, "TaxAmount")[0].attrib["currencyID"] == "TRY"
    )
    top_tax = Decimal(_children(try_tax_total, "TaxAmount")[0].text)
    subtotal_taxes = [
        Decimal(_children(subtotal, "TaxAmount")[0].text)
        for subtotal in _children(try_tax_total, "TaxSubtotal")
    ]

    assert top_tax == Decimal("4.71")
    assert sum(subtotal_taxes) == top_tax
