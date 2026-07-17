from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from extractors.excel_extractor import parse_excel_invoice
from extractors.xml_extractor import parse_xml_invoice


def _write_xml(tmp_path, body: str):
    path = tmp_path / "invoice.xml"
    path.write_text(body, encoding="utf-8")
    return path


def test_xml_reads_tckn_customer_person_name(tmp_path):
    path = _write_xml(
        tmp_path,
        """<?xml version="1.0" encoding="UTF-8"?>
        <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
          <cbc:ID>INV-1</cbc:ID><cbc:IssueDate>2026-07-17</cbc:IssueDate>
          <cac:AccountingCustomerParty><cac:Party>
            <cac:PartyIdentification><cbc:ID schemeID="TCKN">12345678901</cbc:ID></cac:PartyIdentification>
            <cac:Person><cbc:FirstName>Yusuf Alper</cbc:FirstName><cbc:FamilyName>Gülden</cbc:FamilyName></cac:Person>
          </cac:Party></cac:AccountingCustomerParty>
        </Invoice>""",
    )

    result = parse_xml_invoice(str(path))

    assert result["customer_name"] == "Yusuf Alper Gülden"
    assert result["customer_title"] == "Yusuf Alper Gülden"


def test_xml_does_not_fabricate_product_code_from_invoice_line_id(tmp_path):
    path = _write_xml(
        tmp_path,
        """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
          <cbc:ID>INV-1</cbc:ID><cbc:IssueDate>2026-07-17</cbc:IssueDate>
          <cac:InvoiceLine><cbc:ID>7</cbc:ID><cbc:InvoicedQuantity>1</cbc:InvoicedQuantity>
            <cbc:LineExtensionAmount>100</cbc:LineExtensionAmount>
            <cac:Item><cbc:Description>Bakım hizmeti</cbc:Description></cac:Item>
            <cac:Price><cbc:PriceAmount>100</cbc:PriceAmount></cac:Price>
          </cac:InvoiceLine>
        </Invoice>""",
    )

    item = parse_xml_invoice(str(path))["items"][0]

    assert item["code"] is None
    assert item["description"] == "Bakım hizmeti"


def test_xml_missing_item_name_and_description_stays_missing(tmp_path):
    path = _write_xml(
        tmp_path,
        """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
          <cbc:ID>INV-1</cbc:ID><cbc:IssueDate>2026-07-17</cbc:IssueDate>
          <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity>1</cbc:InvoicedQuantity>
            <cbc:LineExtensionAmount>100</cbc:LineExtensionAmount><cac:Item/>
            <cac:Price><cbc:PriceAmount>100</cbc:PriceAmount></cac:Price>
          </cac:InvoiceLine>
        </Invoice>""",
    )

    item = parse_xml_invoice(str(path))["items"][0]

    assert item["description"] is None
    assert item["code"] is None


def test_xml_tax_fallback_accounts_for_document_discount(tmp_path):
    path = _write_xml(
        tmp_path,
        """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
          <cbc:ID>INV-1</cbc:ID><cbc:IssueDate>2026-07-17</cbc:IssueDate>
          <cac:LegalMonetaryTotal>
            <cbc:LineExtensionAmount>100.00</cbc:LineExtensionAmount>
            <cbc:AllowanceTotalAmount>10.00</cbc:AllowanceTotalAmount>
            <cbc:TaxExclusiveAmount>90.00</cbc:TaxExclusiveAmount>
            <cbc:TaxInclusiveAmount>108.00</cbc:TaxInclusiveAmount>
            <cbc:PayableAmount>108.00</cbc:PayableAmount>
          </cac:LegalMonetaryTotal>
        </Invoice>""",
    )

    result = parse_xml_invoice(str(path))

    assert Decimal(result["tax_amount"].replace(",", ".")) == Decimal("18.00")


@pytest.mark.parametrize(
    "raw_date",
    [pd.Timestamp("2026-07-17 00:00:00"), datetime(2026, 7, 17, 14, 30), date(2026, 7, 17)],
)
def test_excel_normalizes_date_like_cells_to_date_only(monkeypatch, raw_date):
    frame = pd.DataFrame(
        [{"Fatura No": "INV-1", "Fatura Tarihi": raw_date, "Açıklama": "Hizmet", "Miktar": 1, "Birim Fiyat": 10, "Satır Toplamı": 10}]
    )
    monkeypatch.setattr("extractors.excel_extractor._read_table", lambda _: frame)

    result = parse_excel_invoice("invoice.xlsx")

    assert result["date"] == "2026-07-17"


def test_turkish_semicolon_csv_is_auto_detected(tmp_path):
    path = tmp_path / "invoice.csv"
    path.write_text(
        "Fatura No;Fatura Tarihi;Müşteri Adı;Açıklama;Miktar;Birim Fiyat;Satır Toplamı\n"
        "INV-1;17.07.2026;Örnek A.Ş.;Danışmanlık;2;75,00;150,00\n",
        encoding="utf-8-sig",
    )

    result = parse_excel_invoice(str(path))

    assert result["invoice_no"] == "INV-1"
    assert result["customer_name"] == "Örnek A.Ş."
    assert result["items"][0]["description"] == "Danışmanlık"
    assert result["items"][0]["unit_price"] == "75,00"


def test_excel_missing_description_is_not_replaced_with_unknown(monkeypatch):
    frame = pd.DataFrame(
        [{"Fatura No": "INV-1", "Miktar": 1, "Birim Fiyat": 10, "Satır Toplamı": 10}]
    )
    monkeypatch.setattr("extractors.excel_extractor._read_table", lambda _: frame)

    result = parse_excel_invoice("invoice.xlsx")

    assert result["items"][0]["description"] is None
