import os
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from extractors.pdf_extractor import (
    _merge_table_items_with_text_items,
    parse_invoice_text,
    parse_pdf_invoice,
)
from extractors.excel_extractor import parse_excel_invoice
from extractors.xml_extractor import parse_xml_invoice
from integrators.uyumsoft_api import (
    UyumsoftResult,
    _best_uyumsoft_user_match,
    build_invoice_info_body,
    build_ubl_invoice,
    get_tcmb_rate,
    send_invoice_to_uyumsoft,
)
from integrators.uyumsoft_excel import export_to_uyumsoft_excel
from validators.invoice_validator import validate_invoice
from validators.invoice_validator import parse_amount


ROOT = os.path.dirname(os.path.dirname(__file__))


class PipelineTests(unittest.TestCase):
    def test_parse_pdf_invoice_series(self):
        from extractors.pdf_extractor import parse_invoice_text

        text_valid_1 = "Fatura Tarihi: 12.04.2026 Seri No: A123\nFatura No: A123\nÜrün Seri: DEVICE42"
        data = parse_invoice_text(text_valid_1)
        self.assertEqual(data["invoice_series"], "A123")

        text_valid_2 = "Fatura Tarihi: 12.04.2026  Fatura Seri No: A/2026\nSeri: ABC"
        data = parse_invoice_text(text_valid_2)
        self.assertEqual(data["invoice_series"], "A/2026")

        text_invalid_1 = "Seri bir üretim yaklaşımıdır.\nSeri Model ABC"
        data = parse_invoice_text(text_invalid_1)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_2 = "Fatura No: A123\nÜrünler\nSeri No: A123\nBirim Fiyat: 100"
        data = parse_invoice_text(text_invalid_2, top_text=text_invalid_2)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_3 = "Fatura Tarihi: 12.04.2026 Ürün açıklaması: Yazıcı   Seri No: DEVICE42"
        data = parse_invoice_text(text_invalid_3)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_5 = "Urunler\nSeri No: A123"
        data = parse_invoice_text(text_invalid_5, top_text=text_invalid_5)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_6 = "Stoklar\nSeri No: A123"
        data = parse_invoice_text(text_invalid_6, top_text=text_invalid_6)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_7 = "Mal Hizmet\nSeri No: A123"
        data = parse_invoice_text(text_invalid_7, top_text=text_invalid_7)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_8 = "Parça Listesi\nSeri No: A123\nFiyat: 100"
        data = parse_invoice_text(text_invalid_8, top_text=text_invalid_8)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_9 = "Parca Listesi\nSeri No: A123\nFiyat: 100"
        data = parse_invoice_text(text_invalid_9, top_text=text_invalid_9)
        self.assertIsNone(data.get("invoice_series"))

        text_invalid_10 = "1234.567 Parça Seri No: DEVICE42 1 Adet 100.00 20% 120.00"
        data = parse_invoice_text(text_invalid_10, top_text=text_invalid_10)
        self.assertIsNone(data.get("invoice_series"))

        text_valid_6 = "Referans: 1234.567\nFatura Seri No: A123\nMal Hizmet\n1234.567 Test Ürün 1 Adet 100,00 20% 120,00"
        data = parse_invoice_text(text_valid_6)
        self.assertEqual(data.get("invoice_series"), "A123")

        text_valid_7 = "Referans: 1234.567 Test Ürün kataloğu\nFatura Seri No: A123\nMal Hizmet\n1234.567 Test Ürün kataloğu 1 Adet 100,00 20% 120,00"
        data = parse_invoice_text(text_valid_7)
        self.assertEqual(data.get("invoice_series"), "A123")

        text_valid_8 = "Yedek Parça: Filtre\nFatura Seri No: A123"
        data = parse_invoice_text(text_valid_8)
        self.assertEqual(data.get("invoice_series"), "A123")

        text_valid_9 = "Referans: 1234.567 Hizmet 100,00\nFatura Seri No: A123\nMal Hizmet\n1234.567 Hizmet 1 Adet 100,00 20% 100,00"
        data = parse_invoice_text(text_valid_9)
        self.assertEqual(data.get("invoice_series"), "A123")

        text_valid_10 = "Referans: Test Hizmet 1 Adet 100,00 20% 120,00\nFatura Seri No: A123"
        data = parse_invoice_text(text_valid_10)
        self.assertEqual(data.get("invoice_series"), "A123")
        
        text_valid_11 = "Fatura Seri No: A123 14.07.2026 100,00 120,00"
        data = parse_invoice_text(text_valid_11)
        self.assertEqual(data.get("invoice_series"), "A123")

        text_valid_5 = "Açıklama: Genel bilgi\nSeri No: A123"
        data = parse_invoice_text(text_valid_5)
        self.assertEqual(data.get("invoice_series"), "A123")

        # Regression test: Ensure broad words followed by prices aren't parsed as items
        text_regression_product = "Ödeme: Plan 1 Ay 100,00 20% 120,00"
        data = parse_invoice_text(text_regression_product)
        self.assertEqual(len(data.get("items", [])), 0)

        text_valid_3 = "Seri No: XYZ789"
        data = parse_invoice_text(text_valid_3)
        self.assertEqual(data.get("invoice_series"), "XYZ789")

        text_valid_4 = "Seri No: A123."
        data = parse_invoice_text(text_valid_4)
        self.assertEqual(data.get("invoice_series"), "A123")

    def test_parse_sample_pdf(self):
        data = parse_pdf_invoice(os.path.join(ROOT, "ornek.pdf"))

        self.assertEqual(data["date"], "7.07.2026")
        self.assertEqual(data["customer_tax_id"], "11111111111")
        self.assertEqual(data["subtotal"], "400,00")
        self.assertEqual(data["tax_amount"], "80,00")
        self.assertEqual(data["total_amount"], "480,00")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["description"], "NFC Silver Kart")
        self.assertEqual(data["items"][0]["serial_numbers"], [])
        data["customer_name"] = "Mock Customer"
        data["customer_tax_id"] = "9000068418"
        data["invoice_no"] = "INV-123"
        self.assertEqual(validate_invoice(data), (True, []))

    def test_parse_wrapped_katlan_product_serial_numbers(self):
        text = """
        Elektronik Barkod Kodlayıcı / Yazıcı
        1390.151 (DBJ251703926~DBJ251703864~DBJ251703909~DBJ251703825~DBJ 6,00 ₺43.703,98 ₺262.223,89
        251703866~DBJ254618071)
        1984.001 Kargo Ücreti 1,00 ₺445,96 ₺445,96
        Ara Toplam ₺262.669,85
        KDV 18(%20) ₺52.533,97
        Yekün ₺315.203,82
        """

        data = parse_invoice_text(text)

        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["description"], "Elektronik Barkod Kodlayıcı / Yazıcı")
        self.assertEqual(
            data["items"][0]["serial_numbers"],
            [
                "DBJ251703926",
                "DBJ251703864",
                "DBJ251703909",
                "DBJ251703825",
                "DBJ251703866",
                "DBJ254618071",
            ],
        )
        self.assertEqual(data["items"][0]["quantity"], "6,00")
        self.assertEqual(data["items"][1]["serial_numbers"], [])

    def test_table_candidate_keeps_serial_numbers_from_text_candidate(self):
        table_items = [
            {
                "code": "1390.151",
                "description": "Elektronik Barkod Kodlayıcı / Yazıcı",
                "serial_numbers": [],
                "quantity": "6,00",
                "unit_price": "43703,98",
                "tax_rate": None,
                "total_price": "262223,89",
            }
        ]
        text_items = [
            {
                "code": "1390.151",
                "description": "Elektronik Barkod Kodlayıcı / Yazıcı",
                "serial_numbers": ["DBJ251703926", "DBJ251703864"],
                "quantity": "6,00",
                "unit_price": "43703,98",
                "tax_rate": None,
                "total_price": "262223,89",
            }
        ]

        merged = _merge_table_items_with_text_items(table_items, text_items)

        self.assertEqual(merged[0]["serial_numbers"], ["DBJ251703926", "DBJ251703864"])

    def test_parse_pdf_buyer_name_and_tax_id_from_buyer_section(self):
        text = """
        Satıcı Fatura Bilgileri
        DEMO SATICI TEKNOLOJI LTD. STI. Fatura No: TEST-USD-2026-0031
        Vergi No: 0000000000
        Alıcı Ödeme / Açıklama
        DEMO ALICI LTD. ŞTİ. Ödeme şekli: Havale/EFT veya SWIFT
        Barbaros Mah. Test Bulvarı No:10 Ataşehir / İstanbul Vade: Peşin
        TC/VKN: 3333333333 Tahsilat para birimi: DOLAR
        Kodu Açıklama Miktar Birim Birim Fiyatı KDV Toplam Fiyat
        3100.121 Kart Okuyucu USB 2 Adet $600,25 %20 $1.200,50
        Ara Toplam $1.200,50
        KDV %20 $240,10
        Yekün $1.440,60
        """

        data = parse_invoice_text(text)

        self.assertEqual(data["customer_tax_id"], "3333333333")
        self.assertEqual(data["customer_name"], "DEMO ALICI LTD. ŞTİ.")
        self.assertEqual(data["customer_title"], "DEMO ALICI LTD. ŞTİ.")

    def test_parse_pdf_explicit_exchange_rate(self):
        text = """
        Fatura Tarihi: 10.07.2026
        Döviz Kuru: 53,5844
        """

        data = parse_invoice_text(text)

        self.assertEqual(data["exchange_rate"], "53.5844")

    def test_parse_pdf_invoice_notes(self):
        text = """
        Fatura No: TEST-2026-1
        Kodu Açıklama Miktar Birim Fiyat Toplam
        1000.001 Test Ürün 1 Adet 100,00 100,00
        AÇIKLAMALAR:
        Sipariş No: 12345
        Teslimat hafta içi yapılsın.
        """

        data = parse_invoice_text(text)

        self.assertEqual(
            data["notes"],
            "Sipariş No: 12345 Teslimat hafta içi yapılsın.",
        )

        data["customer_tax_id"] = "1111111111"
        ubl_root = ET.fromstring(build_ubl_invoice(data))
        note = next(node for node in ubl_root.iter() if node.tag.endswith("}Note"))
        self.assertEqual(note.text, data["notes"])

    def test_parse_pdf_invoice_note_is_deduplicated(self):
        text = """
        AÇIKLAMA: Şu hesaba yatırınız.
        AÇIKLAMA: Şu hesaba yatırınız.
        """

        data = parse_invoice_text(text)

        self.assertEqual(data["notes"], "Şu hesaba yatırınız.")

    def test_pdf_item_description_header_is_not_an_invoice_note(self):
        data = parse_invoice_text("Kodu Açıklama Miktar Birim Fiyat Toplam")

        self.assertEqual(data["notes"], "")

    def test_tcmb_rate_uses_forex_buying(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b"""<Tarih_Date><Currency CurrencyCode="USD"><ForexBuying>42.1234</ForexBuying><ForexSelling>99.9999</ForexSelling></Currency></Tarih_Date>"""

        with patch("integrators.uyumsoft_api.urllib.request.urlopen", return_value=FakeResponse()):
            rate = get_tcmb_rate("USD", "2026-07-10")

        self.assertEqual(rate, "42.1234")

    def test_ubl_prefers_pdf_exchange_rate_over_tcmb(self):
        data = {
            "invoice_no": "TEST-USD-RATE",
            "date": "10.07.2026",
            "customer_tax_id": "1111111111",
            "currency": "USD",
            "exchange_rate": "53.5844",
            "subtotal": "100,00",
            "tax_amount": "20,00",
            "total_amount": "120,00",
            "items": [
                {
                    "description": "Test",
                    "quantity": "1",
                    "unit_price": "100,00",
                    "total_price": "100,00",
                    "tax_rate": "20",
                }
            ],
        }

        with patch("integrators.uyumsoft_api.get_tcmb_rate") as tcmb_lookup:
            ubl = build_ubl_invoice(data)

        tcmb_lookup.assert_not_called()
        self.assertIn("<cbc:CalculationRate>53.5844</cbc:CalculationRate>", ubl)

    def test_parse_fixture_pdf_for_series(self):
        fixture_path = os.path.join(os.path.dirname(__file__), "..", "test_invoice_fixture.pdf")
        if not os.path.exists(fixture_path):
            self.fail("PDF fixture not generated. Run python generate_pdf_fixture.py to create it.")

        data = parse_pdf_invoice(fixture_path)
        self.assertEqual(data.get("invoice_series"), "TOPRIGHT99")

    def test_parse_sample_xml(self):
        data = parse_xml_invoice(os.path.join(ROOT, "ornek.xml"))

        self.assertEqual(data["invoice_no"], "GIB2026000000001")
        self.assertEqual(data["date"], "2026-07-08")
        self.assertEqual(data["customer_tax_id"], "12345678901")
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["subtotal"], "120,00")
        self.assertEqual(data["tax_amount"], "24,00")
        self.assertEqual(data["total_amount"], "144,00")
        data["customer_name"] = "Mock Customer"
        data["customer_tax_id"] = "9000068418"
        data["invoice_no"] = "INV-123"
        self.assertEqual(validate_invoice(data), (True, []))

    def test_export_to_excel_creates_file(self):
        data = parse_xml_invoice(os.path.join(ROOT, "ornek.xml"))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "uyumsoft.xlsx")
            result = export_to_uyumsoft_excel([data], output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(os.path.exists(output_path))
            self.assertGreater(os.path.getsize(output_path), 0)

    def test_parse_exported_excel_invoice(self):
        source = parse_pdf_invoice(os.path.join(ROOT, "ornek.pdf"))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "uyumsoft.xlsx")
            export_to_uyumsoft_excel([source], output_path)
            data = parse_excel_invoice(output_path)

        self.assertEqual(data["date"], "7.07.2026")
        self.assertEqual(data["customer_tax_id"], "11111111111")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["description"], "NFC Silver Kart")
        data["customer_name"] = "Mock Customer"
        data["customer_tax_id"] = "9000068418"
        data["invoice_no"] = "INV-123"
        self.assertEqual(validate_invoice(data), (True, []))

    def test_parse_numeric_amounts_from_excel(self):
        self.assertEqual(parse_amount(10.0), 10.0)
        self.assertEqual(parse_amount("10.0"), 10.0)
        self.assertEqual(parse_amount("1.234,56"), 1234.56)

    def test_validator_rejects_invalid_date_and_handles_none_items(self):
        invalid_date = {
            "date": "NOT-A-DATE",
            "customer_tax_id": "1111111111",
            "subtotal": "100,00",
            "tax_amount": "20,00",
            "total_amount": "120,00",
            "items": [
                {
                    "description": "Test",
                    "quantity": "1",
                    "unit_price": "100,00",
                    "total_price": "100,00",
                }
            ],
        }

        is_valid, errors = validate_invoice(invalid_date)
        self.assertFalse(is_valid)
        self.assertTrue(any("Fatura tarihi geçersiz" in error for error in errors))

        is_valid, errors = validate_invoice(
            {
                "date": "10.07.2026",
                "customer_tax_id": "1111111111",
                "items": None,
                "total_amount": "1,00",
            }
        )
        self.assertFalse(is_valid)
        self.assertTrue(any("kalem" in error for error in errors))

    def test_excel_extracts_currency_rate_discount_notes_and_tax_rate(self):
        import pandas as pd

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "invoice.xlsx")
            pd.DataFrame(
                [
                    {
                        "Invoice No": "INV-EXCEL-1",
                        "Date": "10.07.2026",
                        "Customer Tax ID": "1111111111",
                        "Description": "Test",
                        "Quantity": 1,
                        "Unit Price": 100,
                        "Line Total": 100,
                        "Subtotal": 100,
                        "Tax Amount": 18,
                        "Total Amount": 108,
                        "Currency": "USD",
                        "Exchange Rate": 53.5,
                        "Discount Amount": 10,
                        "Invoice Note": "Test note",
                        "Tax Rate": 20,
                    }
                ]
            ).to_excel(path, index=False)

            data = parse_excel_invoice(path)

        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["exchange_rate"], "53.5")
        self.assertEqual(data["discount_amount"], "10")
        self.assertEqual(data["notes"], "Test note")
        self.assertEqual(data["items"][0]["tax_rate"], "20")

    def test_xml_extracts_discount_and_seller_item_code(self):
        xml = """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
          xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
          xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
          <cbc:ID>INV-XML-1</cbc:ID><cbc:IssueDate>2026-07-10</cbc:IssueDate>
          <cbc:DocumentCurrencyCode>USD</cbc:DocumentCurrencyCode><cbc:Note>Test note</cbc:Note>
          <cac:AccountingCustomerParty><cac:Party><cac:PartyIdentification>
          <cbc:ID>1111111111</cbc:ID></cac:PartyIdentification></cac:Party></cac:AccountingCustomerParty>
          <cac:PricingExchangeRate><cbc:CalculationRate>53.5</cbc:CalculationRate></cac:PricingExchangeRate>
          <cac:TaxTotal><cbc:TaxAmount currencyID="USD">18</cbc:TaxAmount></cac:TaxTotal>
          <cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="USD">100</cbc:LineExtensionAmount>
          <cbc:TaxInclusiveAmount currencyID="USD">108</cbc:TaxInclusiveAmount>
          <cbc:AllowanceTotalAmount currencyID="USD">10</cbc:AllowanceTotalAmount>
          <cbc:PayableAmount currencyID="USD">108</cbc:PayableAmount></cac:LegalMonetaryTotal>
          <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity>1</cbc:InvoicedQuantity>
          <cbc:LineExtensionAmount currencyID="USD">100</cbc:LineExtensionAmount>
          <cac:TaxTotal><cbc:TaxAmount currencyID="USD">18</cbc:TaxAmount><cac:TaxSubtotal>
          <cbc:Percent>20</cbc:Percent></cac:TaxSubtotal></cac:TaxTotal>
          <cac:Item><cbc:Name>Test</cbc:Name><cac:SellersItemIdentification>
          <cbc:ID>SKU-42</cbc:ID></cac:SellersItemIdentification></cac:Item>
          <cac:Price><cbc:PriceAmount currencyID="USD">100</cbc:PriceAmount></cac:Price></cac:InvoiceLine>
          </Invoice>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "invoice.xml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(xml)
            data = parse_xml_invoice(path)

        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["exchange_rate"], "53.5")
        self.assertEqual(data["discount_amount"], "10")
        self.assertEqual(data["notes"], "Test note")
        self.assertEqual(data["items"][0]["code"], "SKU-42")
        self.assertEqual(data["items"][0]["tax_rate"], "20")

    def test_ubl_rejects_invalid_customer_tax_id(self):
        with self.assertRaises(ValueError):
            build_ubl_invoice(
                {
                    "date": "10.07.2026",
                    "customer_tax_id": "invalid",
                    "items": [],
                }
            )

    def test_build_ubl_invoice_is_valid_xml(self):
        data = parse_xml_invoice(os.path.join(ROOT, "ornek.xml"))
        data["customer_tax_id"] = "9000068418"

        ubl = build_ubl_invoice(data)
        root = ET.fromstring(ubl)

        self.assertTrue(root.tag.endswith("Invoice"))
        self.assertIn("GIB2026000000001", ubl)
        self.assertIn("9000068418", ubl)
        self.assertIn("144.00", ubl)

    def test_ubl_discount_is_not_subtracted_twice(self):
        for reported_subtotal in ("100,00", "90,00"):
            with self.subTest(reported_subtotal=reported_subtotal):
                data = {
                    "invoice_no": "TEST-DISCOUNT-1",
                    "date": "10.07.2026",
                    "customer_tax_id": "9000068418",
                    "currency": "TRY",
                    "subtotal": reported_subtotal,
                    "discount_amount": "10,00",
                    "tax_amount": "18,00",
                    "total_amount": "108,00",
                    "items": [
                        {
                            "description": "Test",
                            "quantity": "1",
                            "unit_price": "100,00",
                            "total_price": "100,00",
                            "tax_rate": "20",
                        }
                    ],
                }

                data["customer_name"] = "Mock Customer"
                data["invoice_no"] = "INV-123"
                self.assertEqual(validate_invoice(data), (True, []))

                root = ET.fromstring(build_ubl_invoice(data))
                legal_total = next(
                    node for node in root.iter() if node.tag.endswith("}LegalMonetaryTotal")
                )
                values = {
                    node.tag.rsplit("}", 1)[-1]: node.text for node in legal_total
                }

                self.assertEqual(values["LineExtensionAmount"], "100.00")
                self.assertEqual(values["TaxExclusiveAmount"], "90.00")
                self.assertEqual(values["AllowanceTotalAmount"], "10.00")
                self.assertEqual(values["TaxInclusiveAmount"], "108.00")
                self.assertEqual(values["PayableAmount"], "108.00")

    def test_ubl_exchange_rate_and_allowance_follow_schema_order(self):
        data = {
            "invoice_no": "TEST-USD-ORDER",
            "date": "10.07.2026",
            "customer_tax_id": "1111111111",
            "currency": "USD",
            "exchange_rate": "53.5844",
            "subtotal": "100,00",
            "discount_amount": "10,00",
            "tax_amount": "18,00",
            "total_amount": "108,00",
            "items": [
                {
                    "description": "Test",
                    "quantity": "1",
                    "unit_price": "100,00",
                    "total_price": "100,00",
                    "tax_rate": "20",
                }
            ],
        }

        root = ET.fromstring(build_ubl_invoice(data))
        top_level = [node.tag.rsplit("}", 1)[-1] for node in root]

        self.assertLess(
            top_level.index("AccountingSupplierParty"),
            top_level.index("AccountingCustomerParty"),
        )
        self.assertLess(
            top_level.index("AccountingCustomerParty"),
            top_level.index("AllowanceCharge"),
        )
        self.assertLess(
            top_level.index("AllowanceCharge"),
            top_level.index("PricingExchangeRate"),
        )
        self.assertLess(
            top_level.index("PricingExchangeRate"),
            top_level.index("TaxTotal"),
        )

        legal_total = next(
            node for node in root.iter() if node.tag.endswith("}LegalMonetaryTotal")
        )
        legal_order = [node.tag.rsplit("}", 1)[-1] for node in legal_total]
        self.assertLess(
            legal_order.index("TaxInclusiveAmount"),
            legal_order.index("AllowanceTotalAmount"),
        )
        self.assertLess(
            legal_order.index("AllowanceTotalAmount"),
            legal_order.index("PayableAmount"),
        )

    def test_uyumsoft_wrapper_safe_default_uses_connection_test(self):
        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def test_connection(self):
                from integrators.uyumsoft_api import UyumsoftResult

                return UyumsoftResult(True, "OK", 200, "TestConnection", [], "<ok />")

        with patch("integrators.uyumsoft_api.UyumsoftSoapClient", FakeClient):
            result = send_invoice_to_uyumsoft({})

        self.assertTrue(result["success"])
        self.assertEqual(result["operation"], "TestConnection")
        self.assertEqual(result["response_code"], 200)

    def test_uyumsoft_dry_run_builds_invoice_info_without_network(self):
        data = parse_pdf_invoice(os.path.join(ROOT, "ornek.pdf"))

        result = send_invoice_to_uyumsoft(data, action="dry_run")
        body = build_invoice_info_body("SaveAsDraft", data)

        self.assertTrue(result["success"])
        self.assertEqual(result["operation"], "DryRun")
        self.assertIn("<SaveAsDraft", result["details"])
        self.assertIn("<InvoiceInfo", body)
        self.assertIn("<TargetCustomer", body)
        self.assertNotIn("UNKNOWN CUSTOMER", body)
        ET.fromstring(body)

    def test_uyumsoft_target_customer_never_uses_unknown_customer(self):
        data = {
            "customer_tax_id": "9000068418",
            "items": [{"description": "Test", "quantity": "1", "unit_price": "1", "total_price": "1"}],
            "subtotal": "1",
            "tax_amount": "0",
            "total_amount": "1",
        }

        body = build_invoice_info_body("SaveAsDraft", data)

        self.assertNotIn("UNKNOWN CUSTOMER", body)
        self.assertIn('Title="MUSTERI 9000068418"', body)

    def test_uyumsoft_taxpayer_lookup_matches_identifier(self):
        raw_xml = """
        <Envelope>
          <Body>
            <Value>
              <Items
                Identifier="1111113262"
                Title="OTO ISMAIL OTOMOTIV SAN. VE TIC. LTD. STI. Test Kullanicisi"
                PostboxAlias="urn:mail:defaultpk@otoismail.com.tr" />
            </Value>
          </Body>
        </Envelope>
        """

        match = _best_uyumsoft_user_match(
            UyumsoftResult(True, "OK", 200, "FilterEInvoiceUsers", [], raw_xml),
            "1111113262",
        )

        self.assertIsNotNone(match)
        self.assertEqual(match["Title"], "OTO ISMAIL OTOMOTIV SAN. VE TIC. LTD. STI. Test Kullanicisi")
        self.assertEqual(match["PostboxAlias"], "urn:mail:defaultpk@otoismail.com.tr")

    def test_katlan_golden_regression(self):
        text = """
        Elektronik Barkod Kodlayıcı / Yazıcı
        1390.151 (DBJ251703926~DBJ251703864~DBJ251703909~DBJ251703825~DBJ 6,00 ₺43.703,98 ₺262.223,89
        251703866~DBJ254618071)
        1984.001 Kargo Ücreti 1,00 ₺445,96 ₺445,96
        Ara Toplam ₺262.669,85
        KDV 18(%20) ₺52.533,97
        Yekün ₺315.203,82
        """
        data = parse_invoice_text(text)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["code"], "1390.151")
        self.assertEqual(data["items"][0]["description"], "Elektronik Barkod Kodlayıcı / Yazıcı")
        self.assertEqual(
            data["items"][0]["serial_numbers"],
            [
                "DBJ251703926",
                "DBJ251703864",
                "DBJ251703909",
                "DBJ251703825",
                "DBJ251703866",
                "DBJ254618071",
            ],
        )
        self.assertTrue(
            all(s not in data["items"][0]["description"] for s in data["items"][0]["serial_numbers"])
        )
        self.assertEqual(data["items"][1]["code"], "1984.001")
        self.assertEqual(data["items"][1]["description"], "Kargo Ücreti")

    def test_asyaport_golden_regression_if_file_exists(self):
        import os, glob
        from extractors.pdf_extractor import parse_pdf_invoice
        pdfs = glob.glob('*asyaport*.pdf') + glob.glob('../*asyaport*.pdf') + glob.glob('uploads/*asyaport*.pdf') + glob.glob('C:/Users/stajyer/Downloads/*asyaport*.pdf')
        if pdfs and os.path.exists(pdfs[0]):
            res = parse_pdf_invoice(pdfs[0])
            items = res.get("items", [])
            self.assertGreaterEqual(len(items), 1)
            self.assertEqual(items[0]["code"], "0219.001")
            expected_desc = (
                "Standart Pvc, 2K Bit (256Byte) Hafızalı, 2 Uygulama Alanlı, "
                "Programlanmamış, Parlak Beyaz Ön Ve Arka Yüzey, "
                "Mürekkeple Basılmış Dış Numara, Kart Delgeç işaretli "
                "Temassız Akıllı Kart"
            )
            self.assertEqual(items[0]["description"], expected_desc)
            self.assertNotIn("Ara Toplam", items[0]["description"])
            self.assertNotIn("KDV", items[0]["description"])

    def test_desan_golden_regression_if_file_exists(self):
        import os, glob
        from extractors.pdf_extractor import parse_pdf_invoice
        pdfs = glob.glob('*DESAN*.pdf') + glob.glob('../*DESAN*.pdf') + glob.glob('uploads/*DESAN*.pdf') + glob.glob('C:/Users/stajyer/Downloads/*DESAN*.pdf')
        if pdfs and os.path.exists(pdfs[0]):
            res = parse_pdf_invoice(pdfs[0])
            items = res.get("items", [])
            self.assertEqual(len(items), 7)
            
            expected_items = [
                ("0655.009", "9 Mt. K06 Sert Anten Kablosu"),
                ("0789.082", "CN0106.2 Anten Tarafı Konnektör Takımı - K06 Kablosu İçin v2"),
                ("0789.415", "CN2006.2 Okuyucu Tarafı Konnektör Takımı - K06 Anten Kablosu İçin - Sma Male"),
                ("2245.001", "Endüstriyel Radyo Frekans Anteni"),
                ("0215.030", "Hibrit Kart - HID 26 Bit + H9 PVC Kart"),
                ("3190.024", "Merkezi Kontrol Ünitesi"),
                ("0001.009", "UHF PVC Kart - Düz Beyaz (H47)"),
            ]
            
            for idx, (exp_code, exp_desc) in enumerate(expected_items):
                self.assertEqual(items[idx]["code"], exp_code)
                self.assertEqual(items[idx]["description"], exp_desc)
                
            self.assertNotIn("İŞ BU FATURA", items[6]["description"])
            self.assertNotIn("2.601,60 USD", items[6]["description"])
            self.assertNotIn("BEDELİ USD", items[6]["description"])

    def test_anpa_gross_golden_regression_if_file_exists(self):
        import os, glob
        from extractors.pdf_extractor import parse_pdf_invoice
        pdfs = glob.glob('*ANPA*.pdf') + glob.glob('../*ANPA*.pdf') + glob.glob('uploads/*ANPA*.pdf') + glob.glob('C:/Users/stajyer/Downloads/*ANPA*.pdf')
        if pdfs and os.path.exists(pdfs[0]):
            res = parse_pdf_invoice(pdfs[0])
            items = res.get("items", [])
            self.assertEqual(len(items), 7)
            
            target_item = next((it for it in items if it.get("code") == "4210.058"), None)
            self.assertIsNotNone(target_item)
            
            self.assertEqual(
                target_item["description"],
                "Dış Ortam (Outdoor)Yönlü GSM&GPS Gateway USB + Anten 45"
            )
            
            expected_serials = [
                "1919.0230001",
                "1919.0230002",
                "868018076846834",
                "868018076691636",
                "868018076802324",
                "868018076858193",
                "868018076805806"
            ]
            self.assertEqual(target_item["serial_numbers"], expected_serials)
            self.assertEqual(target_item["quantity"], "7,00")
            self.assertEqual(target_item["unit_price"], "18803,92")
            self.assertEqual(target_item["total_price"], "131627,44")
            
            self.assertNotIn("1919.0230001", target_item["description"])
            self.assertNotIn("868018076846834", target_item["description"])
            self.assertNotIn("~", target_item["description"])

    def test_erdem_cevik_golden_regression_if_file_exists(self):
        import os, glob
        from extractors.pdf_extractor import parse_pdf_invoice
        pdfs = glob.glob('*ERDEM*.pdf') + glob.glob('../*ERDEM*.pdf') + glob.glob('uploads/*ERDEM*.pdf') + glob.glob('C:/Users/stajyer/Downloads/*ERDEM*.pdf') + glob.glob('erdem_cevik.pdf')
        if pdfs and os.path.exists(pdfs[0]):
            res = parse_pdf_invoice(pdfs[0])
            items = res.get("items", [])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["code"], "0213.215")
            self.assertEqual(items[0]["description"], "NFC Black Kart")
            self.assertEqual(items[0]["quantity"], "1,00")
            self.assertEqual(items[0]["unit_price"], "187,42")
            self.assertEqual(items[0]["total_price"], "187,42")
            
            self.assertNotIn("TC", items[0]["description"])
            self.assertNotIn("11111111111", items[0]["description"])
            self.assertNotIn("22.04.2025", items[0]["description"])
            self.assertNotIn("10:54", items[0]["description"])

    def test_nurol_golden_regression_if_file_exists(self):
        import os, glob
        from extractors.pdf_extractor import parse_pdf_invoice
        pdfs = glob.glob('*NUROL*.pdf') + glob.glob('../*NUROL*.pdf') + glob.glob('uploads/*NUROL*.pdf') + glob.glob('C:/Users/stajyer/Downloads/*NUROL*.pdf') + glob.glob('nurol.pdf')
        if pdfs and os.path.exists(pdfs[0]):
            res = parse_pdf_invoice(pdfs[0])
            items = res.get("items", [])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["code"], "3745.012")
            self.assertEqual(items[0]["description"], "NFC Etiket")
            self.assertEqual(items[0]["quantity"], "28.000,00")
            self.assertEqual(items[0]["unit_price"], "12,22")
            self.assertEqual(items[0]["total_price"], "342135,25")
            
            self.assertNotIn("₺12,22", items[0]["description"])
            self.assertNotIn("342.135,25", items[0]["description"])
            self.assertEqual(items[0]["description"].count("NFC Etiket"), 1)


if __name__ == "__main__":
    unittest.main()
