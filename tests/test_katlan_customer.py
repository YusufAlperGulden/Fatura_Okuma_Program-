import unittest

from extractors.pdf_extractor import parse_invoice_text
from validators.invoice_validator import validate_invoice


class KatlanCustomerExtractionTests(unittest.TestCase):
    def test_reads_customer_identity_from_unlabeled_katlan_header(self):
        text = """
        Katlan Yazılım Elektronik Ve Pazarlama
        Meydan Yeri No: 6 Merkez / YOZGAT
        10.04.2026 17:22
        10
        10.04.2026 17:22
        Yozgat 16811884906
        Elektronik Barkod Kodlayıcı / Yazıcı
        1390.151 (DBJ251703926~DBJ251703864~DBJ251703909~DBJ251703825~DBJ251703866~DBJ254618071) 6,00 ₺43.703,98 ₺262.223,89
        1984.001 Kargo Ücreti 1,00 ₺445,96 ₺445,96
        Ara Toplam ₺262.669,85
        KDV 18(%20) ₺52.533,97
        Yekün ₺315.203,82
        """

        data = parse_invoice_text(text)

        self.assertEqual(data["customer_tax_id"], "16811884906")
        self.assertEqual(
            data["customer_name"], "Katlan Yazılım Elektronik Ve Pazarlama"
        )
        self.assertEqual(data["customer_title"], data["customer_name"])
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
        is_valid, errors = validate_invoice(data)
        self.assertTrue(is_valid, errors)

    def test_collapses_exact_name_repetitions_from_pdf_columns(self):
        data = parse_invoice_text(
            "Khaled ALALI Khaled ALALI Khaled ALALI\nYozgat 11111111111"
        )

        self.assertEqual(data["customer_name"], "Khaled ALALI")

    def test_does_not_treat_explicit_seller_as_customer(self):
        data = parse_invoice_text(
            "Satıcı Bilgileri\nDEMO SATICI LTD. ŞTİ.\nVergi No: 1111111111"
        )

        self.assertIsNone(data["customer_name"])


if __name__ == "__main__":
    unittest.main()
