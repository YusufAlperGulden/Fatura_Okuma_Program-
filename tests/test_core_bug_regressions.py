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


def test_one_lira_header_difference_is_rejected_instead_of_rewritten():
    invoice = _invoice(tax_amount="19,01", total_amount="119,01")

    is_valid, errors = validate_invoice(invoice)

    assert is_valid is False
    assert any("KDV" in error for error in errors)


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

