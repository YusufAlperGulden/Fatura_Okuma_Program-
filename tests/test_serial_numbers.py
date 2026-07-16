import os
import sys
import tempfile
import types
import unittest

import pandas as pd

# The tested AI post-processor does not call Gemini. Keep this unit test usable
# in lightweight local environments where the optional SDK is not installed.
try:
    import google.generativeai  # noqa: F401
except ModuleNotFoundError:
    google_package = sys.modules.get("google") or types.ModuleType("google")
    generativeai_module = types.ModuleType("google.generativeai")
    google_package.generativeai = generativeai_module
    sys.modules["google"] = google_package
    sys.modules["google.generativeai"] = generativeai_module

from extractors.ai_extractor import _stringify_amount_fields
from extractors.excel_extractor import parse_excel_invoice
from extractors.xml_extractor import parse_xml_invoice
from integrators.uyumsoft_excel import export_to_uyumsoft_excel
from utils.serial_numbers import (
    merge_invoice_serial_numbers,
    normalize_invoice_serial_numbers,
    normalize_serial_numbers,
)


class SerialNumberTests(unittest.TestCase):
    def test_normalizer_splits_preserves_order_and_removes_duplicates(self):
        self.assertEqual(
            normalize_serial_numbers("(00123~DBJ-2, DBJ-3;\nDBJ-2)"),
            ["00123", "DBJ-2", "DBJ-3"],
        )
        self.assertEqual(normalize_serial_numbers(None), [])
        self.assertEqual(normalize_serial_numbers([123.0, "ABC"]), ["123", "ABC"])

    def test_invoice_and_ai_outputs_are_canonical_and_backward_compatible(self):
        old_invoice = {"items": [{"description": "Old item"}]}
        normalize_invoice_serial_numbers(old_invoice)
        self.assertEqual(old_invoice["items"][0]["serial_numbers"], [])

        ai_result = _stringify_amount_fields(
            {
                "items": [
                    {
                        "description": "Device",
                        "quantity": 2,
                        "serial_numbers": "SER-1~SER-2~SER-1",
                    }
                ]
            }
        )
        self.assertEqual(ai_result["items"][0]["quantity"], "2")
        self.assertEqual(
            ai_result["items"][0]["serial_numbers"], ["SER-1", "SER-2"]
        )

    def test_merge_prefers_product_code_then_falls_back_to_line_index(self):
        target = {
            "items": [
                {"code": "SKU-B", "serial_numbers": ["AI-B"]},
                {"code": "SKU-A"},
                {"description": "No code"},
            ]
        }
        source = {
            "items": [
                {"code": "SKU-A", "serial_numbers": "LOCAL-A"},
                {"code": "sku-b", "serial_numbers": "AI-B~LOCAL-B"},
                {"serial_numbers": "LOCAL-INDEX"},
            ]
        }

        merged = merge_invoice_serial_numbers(target, source)

        self.assertIs(merged, target)
        self.assertEqual(
            merged["items"][0]["serial_numbers"], ["AI-B", "LOCAL-B"]
        )
        self.assertEqual(merged["items"][1]["serial_numbers"], ["LOCAL-A"])
        self.assertEqual(
            merged["items"][2]["serial_numbers"], ["LOCAL-INDEX"]
        )

    def test_xml_reads_all_item_instance_serial_ids_per_line(self):
        xml = """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
          xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
          xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
          <cbc:ID>INV-SERIAL-1</cbc:ID>
          <cbc:IssueDate>2026-07-16</cbc:IssueDate>
          <cac:InvoiceLine>
            <cbc:ID>1</cbc:ID>
            <cbc:InvoicedQuantity>3</cbc:InvoicedQuantity>
            <cbc:LineExtensionAmount currencyID="TRY">300</cbc:LineExtensionAmount>
            <cac:Item>
              <cbc:Name>Device</cbc:Name>
              <cac:ItemInstance><cbc:SerialID>00123</cbc:SerialID></cac:ItemInstance>
              <cac:ItemInstance><cbc:SerialID>SER-2~SER-3</cbc:SerialID></cac:ItemInstance>
            </cac:Item>
            <cac:Price><cbc:PriceAmount currencyID="TRY">100</cbc:PriceAmount></cac:Price>
          </cac:InvoiceLine>
          <cac:InvoiceLine>
            <cbc:ID>2</cbc:ID>
            <cbc:InvoicedQuantity>1</cbc:InvoicedQuantity>
            <cbc:LineExtensionAmount currencyID="TRY">50</cbc:LineExtensionAmount>
            <cac:Item>
              <cbc:Name>Other device</cbc:Name>
              <cac:ItemInstance><cbc:SerialID>OTHER-1</cbc:SerialID></cac:ItemInstance>
            </cac:Item>
            <cac:Price><cbc:PriceAmount currencyID="TRY">50</cbc:PriceAmount></cac:Price>
          </cac:InvoiceLine>
        </Invoice>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "serials.xml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(xml)
            data = parse_xml_invoice(path)

        self.assertEqual(
            data["items"][0]["serial_numbers"], ["00123", "SER-2", "SER-3"]
        )
        self.assertEqual(data["items"][1]["serial_numbers"], ["OTHER-1"])

    def test_excel_reads_serial_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "serials.xlsx")
            pd.DataFrame(
                [
                    {
                        "Ürün Açıklaması": "Device",
                        "Seri Numaraları": "00123~SER-2;SER-2",
                        "Miktar": 2,
                        "Birim Fiyat": 100,
                        "Satır Toplamı": 200,
                    }
                ]
            ).to_excel(path, index=False)
            data = parse_excel_invoice(path)

        self.assertEqual(data["items"][0]["serial_numbers"], ["00123", "SER-2"])

    def test_uyumsoft_excel_export_round_trip_preserves_serials(self):
        invoice = {
            "date": "16.07.2026",
            "customer_tax_id": "1111111111",
            "customer_name": "Customer",
            "items": [
                {
                    "code": "SKU-1",
                    "description": "Device",
                    "serial_numbers": ["00123", "SER-2"],
                    "quantity": "2",
                    "unit_price": "100,00",
                    "total_price": "200,00",
                }
            ],
            "subtotal": "200,00",
            "tax_amount": "40,00",
            "total_amount": "240,00",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "uyumsoft.xlsx")
            export_to_uyumsoft_excel([invoice], path)
            parsed = parse_excel_invoice(path)

        self.assertEqual(parsed["items"][0]["serial_numbers"], ["00123", "SER-2"])


if __name__ == "__main__":
    unittest.main()
