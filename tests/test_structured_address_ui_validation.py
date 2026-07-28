import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from validators.invoice_validator import validate_invoice


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _valid_invoice():
    return {
        "invoice_no": "TEST-ADDRESS-1",
        "date": "28.07.2026",
        "time": "12:00",
        "customer_tax_id": "11111111111",
        "customer_name": "Test Müşteri",
        "items": [
            {
                "code": "TEST",
                "description": "Test hizmeti",
                "quantity": "1",
                "unit_price": "100,00",
                "tax_rate": "20",
                "total_price": "100,00",
            }
        ],
        "subtotal": "100,00",
        "discount_amount": "0,00",
        "tax_amount": "20,00",
        "total_amount": "120,00",
        "currency": "TRY",
        "customer_address": (
            "CEVİZLİ MAH. TOROS CAD. ALBAYRAK APT NO: 24 A "
            "MALTEPE / İSTANBUL"
        ),
        "customer_postal_address": {
            "street_name": "TOROS CAD.",
            "building_name": "ALBAYRAK APT",
            "building_number": "24 A",
            "city_subdivision_name": "MALTEPE",
            "city_name": "İSTANBUL",
            "postal_zone": "34840",
            "district": "CEVİZLİ MAH.",
            "country_code": "tr",
            "country_name": "Türkiye",
            "address_lines": ["Teslimat: Arka giriş"],
        },
    }


def _address_errors(invoice):
    is_valid, errors = validate_invoice(invoice)
    return is_valid, [error for error in errors if "adres" in error.lower()]


def test_structured_address_accepts_only_the_canonical_typed_schema():
    invoice = _valid_invoice()

    is_valid, errors = validate_invoice(invoice)

    assert is_valid, errors
    assert invoice["customer_postal_address"]["country_code"] == "TR"


@pytest.mark.parametrize(
    ("field", "value", "message_fragment"),
    [
        ("street_name", [], "yalnızca metin"),
        ("address_lines", "tek satır", "metinlerden oluşan bir liste"),
        ("address_lines", ["uygun", {"unsafe": True}], "2. değer"),
        ("country_code", "TUR", "iki harfli ISO"),
        ("city_name", "A" * 101, "en fazla 100"),
        ("postal_zone", "\x00" + "34000", "kontrol karakterleri"),
    ],
)
def test_structured_address_rejects_wrong_types_and_unbounded_values(
    field, value, message_fragment
):
    invoice = _valid_invoice()
    invoice["customer_postal_address"][field] = value

    is_valid, errors = _address_errors(invoice)

    assert not is_valid
    assert any(message_fragment in error for error in errors), errors


def test_structured_address_rejects_unknown_keys_even_when_not_strings():
    invoice = _valid_invoice()
    invoice["customer_postal_address"]["unexpected"] = "value"
    invoice["customer_postal_address"][7] = "value"

    is_valid, errors = _address_errors(invoice)

    assert not is_valid
    assert sum("Geçersiz adres alanı" in error for error in errors) == 2


def test_address_validation_preserves_address_data_without_database_access():
    invoice = _valid_invoice()
    before = copy.deepcopy(invoice)

    is_valid, errors = validate_invoice(invoice)

    assert is_valid, errors
    # The validator may canonicalize values, but it must not remove address data.
    assert invoice["customer_address"] == before["customer_address"]
    assert invoice["customer_postal_address"]["address_lines"] == [
        "Teslimat: Arka giriş"
    ]




def test_javascript_address_round_trip_preserves_raw_and_legacy_values():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; JavaScript runtime contract skipped.")

    app_js = PROJECT_ROOT / "ui" / "app.js"
    probe = r"""
global.window = {};
global.document = { addEventListener: () => {} };
require(process.argv[1]);

const api = window.InvoiceAddressUi;
const raw = 'CEVIZLI MAH. TOROS CAD. NO: 24 MALTEPE / ISTANBUL';
const flat = { customer_address: raw };
const normalizedFlat = api.normalizePostalAddress(flat);
const edited = api.mergePostalAddress(flat, 'street_name', 'TOROS CAD.');
const withLines = api.mergePostalAddress(
    { customer_address: raw, customer_postal_address: edited },
    'address_lines',
    'Blok B\nKat 2'
);
const legacy = api.normalizePostalAddress({
    customer_address: {
        street: 'FOREIGN STREET',
        district: 'WESTMINSTER',
        city: 'LONDON',
        country: 'GB',
        postal_code: 'SW1A 1AA',
        address_line: 'Suite 7'
    }
});
const partial = api.normalizePostalAddress({
    customer_address: raw,
    customer_postal_address: { city_name: 'ISTANBUL' }
});
const csvRows = api.postalAddressCsvRows({
    customer_address: raw,
    customer_postal_address: withLines
});

process.stdout.write(JSON.stringify({
    normalizedFlat,
    edited,
    withLines,
    legacy,
    partial,
    csvRows
}));
"""
    completed = subprocess.run(
        [node, "-e", probe, str(app_js)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["normalizedFlat"]["address_lines"] == [
        "CEVIZLI MAH. TOROS CAD. NO: 24 MALTEPE / ISTANBUL"
    ]
    assert set(result["edited"]) == {
        "street_name",
        "building_name",
        "building_number",
        "city_subdivision_name",
        "city_name",
        "postal_zone",
        "district",
        "country_code",
        "country_name",
        "address_lines",
    }
    assert result["edited"]["street_name"] == "TOROS CAD."
    assert result["edited"]["address_lines"] == [raw := (
        "CEVIZLI MAH. TOROS CAD. NO: 24 MALTEPE / ISTANBUL"
    )]
    assert result["withLines"]["address_lines"] == ["Blok B", "Kat 2"]
    assert result["legacy"]["street_name"] == "FOREIGN STREET"
    assert result["legacy"]["city_subdivision_name"] == "WESTMINSTER"
    assert result["legacy"]["city_name"] == "LONDON"
    assert result["legacy"]["country_code"] == "GB"
    assert result["legacy"]["postal_zone"] == "SW1A 1AA"
    assert result["partial"]["city_name"] == "ISTANBUL"
    assert result["partial"]["address_lines"] == [raw]
    assert ["Adres Ulke Kodu", ""] in result["csvRows"]
    assert ["Adres Ek Satirlari", "Blok B | Kat 2"] in result["csvRows"]
    assert all("[object Object]" not in str(row) for row in result["csvRows"])
