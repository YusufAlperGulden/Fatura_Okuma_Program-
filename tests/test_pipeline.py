import os
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from extractors.pdf_extractor import parse_invoice_text, parse_pdf_invoice
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
    def test_parse_sample_pdf(self):
        data = parse_pdf_invoice(os.path.join(ROOT, "ornek.pdf"))

        self.assertEqual(data["date"], "7.07.2026")
        self.assertEqual(data["customer_tax_id"], "11111111111")
        self.assertEqual(data["subtotal"], "400,00")
        self.assertEqual(data["tax_amount"], "80,00")
        self.assertEqual(data["total_amount"], "480,00")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["description"], "NFC Silver Kart")
        self.assertEqual(validate_invoice(data), (True, []))

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

    def test_parse_sample_xml(self):
        data = parse_xml_invoice(os.path.join(ROOT, "ornek.xml"))

        self.assertEqual(data["invoice_no"], "GIB2026000000001")
        self.assertEqual(data["date"], "2026-07-08")
        self.assertEqual(data["customer_tax_id"], "12345678901")
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["subtotal"], "120,00")
        self.assertEqual(data["tax_amount"], "24,00")
        self.assertEqual(data["total_amount"], "144,00")
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
        self.assertEqual(validate_invoice(data), (True, []))

    def test_parse_numeric_amounts_from_excel(self):
        self.assertEqual(parse_amount(10.0), 10.0)
        self.assertEqual(parse_amount("10.0"), 10.0)
        self.assertEqual(parse_amount("1.234,56"), 1234.56)

    def test_build_ubl_invoice_is_valid_xml(self):
        data = parse_xml_invoice(os.path.join(ROOT, "ornek.xml"))

        ubl = build_ubl_invoice(data)
        root = ET.fromstring(ubl)

        self.assertTrue(root.tag.endswith("Invoice"))
        self.assertIn("GIB2026000000001", ubl)
        self.assertIn("12345678901", ubl)
        self.assertIn("144.00", ubl)

    def test_ubl_discount_is_not_subtracted_twice(self):
        for reported_subtotal in ("100,00", "90,00"):
            with self.subTest(reported_subtotal=reported_subtotal):
                data = {
                    "invoice_no": "TEST-DISCOUNT-1",
                    "date": "10.07.2026",
                    "customer_tax_id": "1111111111",
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
            "customer_tax_id": "11111111111",
            "items": [{"description": "Test", "quantity": "1", "unit_price": "1", "total_price": "1"}],
            "subtotal": "1",
            "tax_amount": "0",
            "total_amount": "1",
        }

        body = build_invoice_info_body("SaveAsDraft", data)

        self.assertNotIn("UNKNOWN CUSTOMER", body)
        self.assertIn('Title="MUSTERI 11111111111"', body)

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


if __name__ == "__main__":
    unittest.main()
