from __future__ import annotations

from xml.etree import ElementTree as ET

from integrators.uyumsoft_api import (
    CAC_NS,
    CBC_NS,
    build_ubl_invoice,
    parse_turkish_address,
)


NS = {"cac": CAC_NS, "cbc": CBC_NS}
CANONICAL_KEYS = {
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


def _invoice(*, tax_id: str = "1234567890", address=None) -> dict:
    return {
        "invoice_no": "TEST-ADDRESS-1",
        "date": "2026-07-28",
        "customer_tax_id": tax_id,
        "customer_name": "Test Müşteri",
        "supplier_tax_id": "9000068418",
        "supplier_name": "Test Tedarikçi",
        "currency": "TRY",
        "subtotal": "100.00",
        "tax_amount": "20.00",
        "total_amount": "120.00",
        "tax_rate": "20",
        "items": [
            {
                "description": "Test hizmeti",
                "quantity": "1",
                "unit_price": "100.00",
                "total_price": "100.00",
                "tax_rate": "20",
            }
        ],
        "customer_postal_address": address,
    }


def _customer_party(xml: str) -> ET.Element:
    root = ET.fromstring(xml)
    party = root.find("cac:AccountingCustomerParty/cac:Party", NS)
    assert party is not None
    return party


def _local_names(element: ET.Element) -> list[str]:
    return [child.tag.rsplit("}", 1)[-1] for child in element]


def test_empty_address_has_exact_canonical_schema():
    address = parse_turkish_address(None)

    assert set(address) == CANONICAL_KEYS
    assert address["address_lines"] == []
    assert all(not value for key, value in address.items() if key != "address_lines")


def test_all_empty_structured_object_does_not_emit_empty_postal_address():
    party = _customer_party(
        build_ubl_invoice(_invoice(address=parse_turkish_address(None)))
    )

    assert party.find("cac:PostalAddress", NS) is None


def test_mufemu_address_is_split_without_losing_components():
    address = parse_turkish_address(
        "CEVİZLİ MAH. TOROS CAD. ALBAYRAK APT "
        "NO: 24 A MALTEPE/ İSTANBUL"
    )

    assert address == {
        "street_name": "TOROS CAD.",
        "building_name": "ALBAYRAK APT",
        "building_number": "24 A",
        "city_subdivision_name": "MALTEPE",
        "city_name": "İSTANBUL",
        "postal_zone": "",
        "district": "CEVİZLİ MAH.",
        "country_code": "TR",
        "country_name": "Türkiye",
        "address_lines": [],
    }


def test_rightmost_city_wins_over_ankara_street_in_izmir():
    address = parse_turkish_address(
        "ATATÜRK MAH. ANKARA CAD. NO: 8 KONAK / İZMİR"
    )

    assert address["street_name"] == "ANKARA CAD."
    assert address["building_number"] == "8"
    assert address["city_subdivision_name"] == "KONAK"
    assert address["city_name"] == "İZMİR"


def test_rightmost_city_wins_over_istanbul_street_in_ankara():
    address = parse_turkish_address(
        "İSTANBUL CADDESİ NO: 4 ÇANKAYA / ANKARA"
    )

    assert address["street_name"] == "İSTANBUL CADDESİ"
    assert address["building_number"] == "4"
    assert address["city_subdivision_name"] == "ÇANKAYA"
    assert address["city_name"] == "ANKARA"


def test_postal_code_numbered_street_and_unit_are_preserved():
    address = parse_turkish_address(
        "1234. SOKAK GÜNEŞ APT. DIŞ KAPI NO: 12 "
        "İÇ KAPI NO: 5 KONAK/İZMİR 35210"
    )

    assert address["street_name"] == "1234. SOKAK"
    assert address["building_name"] == "GÜNEŞ APT."
    assert address["building_number"] == "12"
    assert address["city_subdivision_name"] == "KONAK"
    assert address["city_name"] == "İZMİR"
    assert address["postal_zone"] == "35210"
    assert address["address_lines"] == ["İÇ KAPI NO: 5"]


def test_postal_code_after_city_is_not_dropped():
    address = parse_turkish_address(
        "İSTİKLAL CAD. NO:10 BEYOĞLU/İSTANBUL 34430"
    )

    assert address["postal_zone"] == "34430"
    assert address["city_name"] == "İSTANBUL"
    assert address["city_subdivision_name"] == "BEYOĞLU"


def test_unmapped_trailing_slice_is_kept_as_address_line():
    address = parse_turkish_address(
        "ATATÜRK MAH. İSTİKLAL CAD. NO:1 "
        "BEYOĞLU/İSTANBUL TARİHİ HAN GİRİŞİ"
    )

    assert address["address_lines"] == ["TARİHİ HAN GİRİŞİ"]


def test_foreign_canonical_address_is_not_defaulted_to_turkey():
    structured = {
        "street_name": "Friedrichstraße",
        "building_number": "10",
        "city_name": "Berlin",
        "postal_zone": "10117",
        "country_code": "DE",
        "country_name": "Deutschland",
        "address_lines": ["3. Etage"],
    }

    address = parse_turkish_address(structured)

    assert set(address) == CANONICAL_KEYS
    assert address["country_code"] == "DE"
    assert address["country_name"] == "Deutschland"
    assert address["city_name"] == "Berlin"


def test_foreign_name_without_code_does_not_gain_tr_code_in_ubl():
    address = {
        "street_name": "Rue de Rivoli",
        "building_number": "4",
        "city_name": "Paris",
        "postal_zone": "75001",
        "country_name": "France",
    }

    party = _customer_party(build_ubl_invoice(_invoice(address=address)))
    postal_address = party.find("cac:PostalAddress", NS)
    assert postal_address is not None
    country = postal_address.find("cac:Country", NS)
    assert country is not None
    assert country.find("cbc:IdentificationCode", NS) is None
    assert country.findtext("cbc:Name", namespaces=NS) == "France"


def test_partial_structured_edit_uses_flat_address_for_missing_components():
    invoice = _invoice(address={"building_number": "24 B"})
    invoice["customer_address"] = (
        "CEVİZLİ MAH. TOROS CAD. ALBAYRAK APT "
        "NO: 24 A MALTEPE/ İSTANBUL"
    )

    party = _customer_party(build_ubl_invoice(invoice))
    postal_address = party.find("cac:PostalAddress", NS)
    assert postal_address is not None

    assert postal_address.findtext("cbc:StreetName", namespaces=NS) == "TOROS CAD."
    assert (
        postal_address.findtext("cbc:BuildingName", namespaces=NS)
        == "ALBAYRAK APT"
    )
    assert postal_address.findtext("cbc:BuildingNumber", namespaces=NS) == "24 B"
    assert (
        postal_address.findtext("cbc:CitySubdivisionName", namespaces=NS)
        == "MALTEPE"
    )
    assert postal_address.findtext("cbc:CityName", namespaces=NS) == "İSTANBUL"


def test_postal_address_children_follow_ubl_sequence():
    address = {
        "street_name": "Toros Cad.",
        "building_name": "Albayrak Apt",
        "building_number": "24 A",
        "city_subdivision_name": "Maltepe",
        "city_name": "İstanbul",
        "postal_zone": "34840",
        "district": "Cevizli Mah.",
        "address_lines": ["B Blok, 3. Kat"],
        "country_code": "TR",
        "country_name": "Türkiye",
    }

    party = _customer_party(build_ubl_invoice(_invoice(address=address)))
    postal_address = party.find("cac:PostalAddress", NS)
    assert postal_address is not None

    assert _local_names(postal_address) == [
        "StreetName",
        "BuildingName",
        "BuildingNumber",
        "CitySubdivisionName",
        "CityName",
        "PostalZone",
        "District",
        "AddressLine",
        "Country",
    ]


def test_vkn_party_orders_name_before_postal_address():
    party = _customer_party(
        build_ubl_invoice(
            _invoice(
                tax_id="1234567890",
                address={"street_name": "Toros Cad.", "city_name": "İstanbul"},
            )
        )
    )

    assert _local_names(party) == [
        "PartyIdentification",
        "PartyName",
        "PostalAddress",
    ]


def test_tckn_party_orders_postal_address_before_person():
    invoice = _invoice(
        tax_id="12345678901",
        address={"street_name": "Toros Cad.", "city_name": "İstanbul"},
    )
    invoice["customer_name"] = "Ayşe Yılmaz"

    party = _customer_party(build_ubl_invoice(invoice))

    assert _local_names(party) == [
        "PartyIdentification",
        "PostalAddress",
        "Person",
    ]
    assert party.findtext("cac:Person/cbc:FirstName", namespaces=NS) == "Ayşe"
    assert party.findtext("cac:Person/cbc:FamilyName", namespaces=NS) == "Yılmaz"


def test_address_values_are_xml_escaped_and_round_trip_as_text():
    address = {
        "street_name": "A&B <Street>",
        "building_name": '"North" > South',
        "building_number": "5",
        "city_name": "Berlin",
        "district": "R&D",
        "address_lines": ["Floor <3> & rear"],
        "country_code": "DE",
        "country_name": "Deutschland",
    }

    xml = build_ubl_invoice(_invoice(address=address))
    party = _customer_party(xml)
    postal_address = party.find("cac:PostalAddress", NS)
    assert postal_address is not None

    assert "&amp;" in xml
    assert "&lt;Street&gt;" in xml
    assert postal_address.findtext("cbc:StreetName", namespaces=NS) == "A&B <Street>"
    assert (
        postal_address.findtext("cac:AddressLine/cbc:Line", namespaces=NS)
        == "Floor <3> & rear"
    )
