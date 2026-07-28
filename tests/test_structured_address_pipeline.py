import pandas as pd

import extractors.xml_extractor as xml_extractor
from extractors.ai_extractor import _stringify_amount_fields
from extractors.excel_extractor import parse_excel_invoice
from extractors.pdf_extractor import parse_invoice_text
from extractors.xml_extractor import parse_xml_invoice
from integrators.mikro_v16_bridge import _build_customer_row
from integrators.uyumsoft_excel import export_to_uyumsoft_excel
from utils.serial_numbers import safe_merge_ai_data


def _line_item():
    return {
        "code": "SKU-1",
        "description": "Service",
        "quantity": "1",
        "unit_price": "100",
        "total_price": "100",
        "tax_rate": "20",
    }


def test_xml_foreign_postal_address_preserves_every_canonical_field(monkeypatch):
    xml = """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
      xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
      <cbc:ID>INV-DE-1</cbc:ID>
      <cbc:IssueDate>2026-07-28</cbc:IssueDate>
      <cac:AccountingCustomerParty><cac:Party>
        <cac:PartyIdentification><cbc:ID schemeID="VKN">1234567890</cbc:ID></cac:PartyIdentification>
        <cac:PartyName><cbc:Name>Example GmbH</cbc:Name></cac:PartyName>
        <cac:PostalAddress>
          <cbc:StreetName>Unter den Linden</cbc:StreetName>
          <cbc:BuildingName>Lindenhaus</cbc:BuildingName>
          <cbc:BuildingNumber>7A</cbc:BuildingNumber>
          <cbc:CitySubdivisionName>Mitte</cbc:CitySubdivisionName>
          <cbc:CityName>Berlin</cbc:CityName>
          <cbc:PostalZone>10117</cbc:PostalZone>
          <cbc:District>Regierungsviertel</cbc:District>
          <cac:AddressLine><cbc:Line>Floor 4</cbc:Line></cac:AddressLine>
          <cac:AddressLine><cbc:Line>Suite 8</cbc:Line></cac:AddressLine>
          <cac:Country>
            <cbc:IdentificationCode>DE</cbc:IdentificationCode>
            <cbc:Name>Germany</cbc:Name>
          </cac:Country>
        </cac:PostalAddress>
      </cac:Party></cac:AccountingCustomerParty>
    </Invoice>"""
    root = xml_extractor.ET.fromstring(xml)

    class ParsedTree:
        def getroot(self):
            return root

    monkeypatch.setattr(xml_extractor.ET, "parse", lambda _: ParsedTree())

    result = parse_xml_invoice("foreign.xml")

    assert result["customer_postal_address"] == {
        "street_name": "Unter den Linden",
        "building_name": "Lindenhaus",
        "building_number": "7A",
        "city_subdivision_name": "Mitte",
        "city_name": "Berlin",
        "postal_zone": "10117",
        "district": "Regierungsviertel",
        "country_code": "DE",
        "country_name": "Germany",
        "address_lines": ["Floor 4", "Suite 8"],
    }
    assert isinstance(result["customer_address"], str)
    assert "Unter den Linden" in result["customer_address"]
    assert "Germany" in result["customer_address"]


def test_ai_merge_keeps_strong_local_components_and_fills_missing_values():
    ai_result = {
        "customer_address": "AI raw address",
        "customer_postal_address": {
            "street_name": "AI Street",
            "city_name": "Berlin",
            "country_code": "DE",
            "country_name": "Germany",
            "address_lines": ["AI-only delivery note"],
        },
        "items": [],
    }
    local_result = {
        "customer_address": "LOCAL RAW ADDRESS",
        "customer_postal_address": {
            "street_name": "Local Street",
            "building_number": "24 A",
            "district": "Local District",
        },
        "items": [],
    }

    merged = safe_merge_ai_data(ai_result, local_result)

    assert merged["customer_address"] == "LOCAL RAW ADDRESS"
    assert merged["customer_postal_address"] == {
        "street_name": "Local Street",
        "building_number": "24 A",
        "district": "Local District",
        "city_name": "Berlin",
        "country_code": "DE",
        "country_name": "Germany",
        "address_lines": ["AI-only delivery note"],
    }


def test_ai_response_normalizes_legacy_address_object():
    result = _stringify_amount_fields(
        {
            "customer_address": {
                "street": "Legacy Street",
                "city": "Paris",
                "country": "France",
            },
            "items": [],
        }
    )

    assert result["customer_postal_address"] == {
        "street_name": "Legacy Street",
        "city_name": "Paris",
        "country_name": "France",
    }
    assert result["customer_address"] == "Legacy Street, Paris, France"


def test_excel_ingests_split_address_columns(monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "Invoice No": "INV-1",
                "Customer Name": "Example GmbH",
                "Street Name": "Unter den Linden",
                "Building Name": "Lindenhaus",
                "Building Number": "7A",
                "City Subdivision Name": "Mitte",
                "City Name": "Berlin",
                "Postal Zone": "10117",
                "District": "Regierungsviertel",
                "Country Code": "DE",
                "Country Name": "Germany",
                "Address Lines": "Floor 4|Suite 8",
                "Description": "Service",
                "Quantity": 1,
                "Unit Price": 100,
                "Line Total": 100,
            }
        ]
    )
    monkeypatch.setattr("extractors.excel_extractor._read_table", lambda _: frame)

    result = parse_excel_invoice("invoice.xlsx")

    assert result["customer_postal_address"]["street_name"] == "Unter den Linden"
    assert result["customer_postal_address"]["address_lines"] == [
        "Floor 4",
        "Suite 8",
    ]
    assert result["customer_postal_address"]["country_code"] == "DE"
    assert isinstance(result["customer_address"], str)
    assert "Berlin" in result["customer_address"]


def test_excel_ingests_and_structures_flat_address(monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "Customer Address": (
                    "CEVIZLI MAH. TOROS CAD. ALBAYRAK APT "
                    "NO: 24 A MALTEPE / ISTANBUL"
                ),
                "Description": "Service",
                "Quantity": 1,
                "Unit Price": 100,
                "Line Total": 100,
            }
        ]
    )
    monkeypatch.setattr("extractors.excel_extractor._read_table", lambda _: frame)

    result = parse_excel_invoice("invoice.xlsx")

    assert result["customer_address"].startswith("CEVIZLI MAH.")
    assert result["customer_postal_address"]["street_name"] == "TOROS CAD."
    assert result["customer_postal_address"]["building_number"] == "24 A"
    assert result["customer_postal_address"]["city_subdivision_name"] == "MALTEPE"


def test_uyumsoft_excel_round_trip_never_serializes_an_object(monkeypatch):
    invoice = {
        "date": "2026-07-28",
        "customer_tax_id": "1234567890",
        "customer_name": "Example GmbH",
        "customer_address": "Source raw address",
        "customer_postal_address": {
            "street_name": "Unter den Linden",
            "building_number": "7A",
            "city_name": "Berlin",
            "country_code": "DE",
            "country_name": "Germany",
            "address_lines": ["Floor 4", "Suite 8"],
        },
        "items": [_line_item()],
        "subtotal": "100",
        "tax_amount": "20",
        "total_amount": "120",
    }
    captured = {}

    def capture_frame(frame, _path, index=False):
        captured["frame"] = frame.copy()
        captured["index"] = index

    monkeypatch.setattr(pd.DataFrame, "to_excel", capture_frame)
    export_to_uyumsoft_excel([invoice], "uyumsoft.xlsx")
    exported = captured["frame"]
    values = " ".join(str(value) for value in exported.iloc[0].tolist())
    monkeypatch.setattr(
        "extractors.excel_extractor._read_table",
        lambda _: exported.copy(),
    )
    reparsed = parse_excel_invoice("uyumsoft.xlsx")

    assert "[object Object]" not in values
    assert "{'street_name'" not in values
    assert reparsed["customer_address"] == "Source raw address"
    assert reparsed["customer_postal_address"]["street_name"] == "Unter den Linden"
    assert reparsed["customer_postal_address"]["address_lines"] == [
        "Floor 4",
        "Suite 8",
    ]


def test_pdf_text_extraction_propagates_raw_and_structured_address():
    text = """Alici
ACME LTD STI
CEVIZLI MAH. TOROS CAD. ALBAYRAK APT NO: 24 A
MALTEPE / ISTANBUL
VKN: 1234567890
Kodu Aciklama Miktar Birim Fiyat
"""

    result = parse_invoice_text(text)

    assert result["customer_address"].startswith("CEVIZLI MAH.")
    assert result["customer_postal_address"]["street_name"] == "TOROS CAD."
    assert result["customer_postal_address"]["building_name"] == "ALBAYRAK APT"
    assert result["customer_postal_address"]["building_number"] == "24 A"
    assert result["customer_postal_address"]["city_subdivision_name"] == "MALTEPE"


def test_mikro_customer_export_uses_structured_city_country_and_clean_address():
    row = _build_customer_row(
        {
            "customer_tax_id": "1234567890",
            "customer_name": "Example GmbH",
            "customer_postal_address": {
                "street_name": "Unter den Linden",
                "city_name": "Berlin",
                "country_code": "DE",
                "address_lines": ["Floor 4"],
            },
        },
        "invoice-reader",
    )

    assert row["city"] == "Berlin"
    assert row["country"] == "DE"
    assert row["address"] == "Floor 4, Unter den Linden, Berlin, DE"
    assert "[object Object]" not in row["address"]
