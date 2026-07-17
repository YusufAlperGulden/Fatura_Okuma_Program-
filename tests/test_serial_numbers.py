import os
import sys
import tempfile
import types
import unittest
from xml.etree import ElementTree as ET

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
from integrators.uyumsoft_api import build_invoice_info_body, build_ubl_invoice
from integrators.uyumsoft_excel import export_to_uyumsoft_excel
from utils.serial_numbers import (
    merge_invoice_serial_numbers,
    normalize_invoice_serial_numbers,
    normalize_serial_numbers,
)


def _ubl_invoice(items):
    subtotal = sum(float(item.get("total_price") or 0) for item in items)
    tax_amount = subtotal * 0.20
    return {
        "invoice_no": "INV-SERIAL-OUT",
        "date": "17.07.2026",
        "customer_tax_id": "1234567890",
        "customer_name": "Test Musteri",
        "items": items,
        "subtotal": str(subtotal),
        "tax_amount": str(tax_amount),
        "total_amount": str(subtotal + tax_amount),
        "currency": "TRY",
    }


def _local_name(element):
    return element.tag.rsplit("}", 1)[-1]


class SerialNumberTests(unittest.TestCase):
    def test_normalizer_splits_preserves_order_and_removes_duplicates(self):
        self.assertEqual(
            normalize_serial_numbers("(00123~DBJ-2, DBJ-3;\nDBJ-2)"),
            ["00123", "DBJ-2", "DBJ-3"],
        )
        self.assertEqual(normalize_serial_numbers(None), [])
        self.assertEqual(normalize_serial_numbers([123.0, "ABC"]), ["123", "ABC"])

    def test_uyumsoft_ubl_emits_one_item_instance_per_normalized_serial(self):
        invoice = _ubl_invoice(
            [
                {
                    "code": "SKU-1",
                    "description": "Device",
                    "serial_numbers": "(00123~SER&2;SER&2~A<B)",
                    "quantity": "3",
                    "unit_price": "100",
                    "total_price": "300",
                    "tax_rate": "20",
                }
            ]
        )

        root = ET.fromstring(build_ubl_invoice(invoice))
        instances = [node for node in root.iter() if _local_name(node) == "ItemInstance"]
        serials = [node.text for node in root.iter() if _local_name(node) == "SerialID"]

        self.assertEqual(len(instances), 3)
        self.assertEqual(serials, ["00123", "SER&2", "A<B"])

        item_node = next(node for node in root.iter() if _local_name(node) == "Item")
        self.assertEqual(
            [_local_name(child) for child in item_node],
            [
                "Name",
                "SellersItemIdentification",
                "ItemInstance",
                "ItemInstance",
                "ItemInstance",
            ],
        )

    def test_uyumsoft_ubl_omits_item_instances_when_serials_are_empty(self):
        items = []
        for index, serial_numbers in enumerate((None, [], ["  "]), start=1):
            items.append(
                {
                    "code": f"SKU-{index}",
                    "description": f"Device {index}",
                    "serial_numbers": serial_numbers,
                    "quantity": "1",
                    "unit_price": "25",
                    "total_price": "25",
                    "tax_rate": "20",
                }
            )
        items.append(
            {
                "code": "SKU-NO-KEY",
                "description": "Device without serial key",
                "quantity": "1",
                "unit_price": "25",
                "total_price": "25",
                "tax_rate": "20",
            }
        )

        root = ET.fromstring(build_ubl_invoice(_ubl_invoice(items)))

        self.assertFalse(any(_local_name(node) == "ItemInstance" for node in root.iter()))
        self.assertFalse(any(_local_name(node) == "SerialID" for node in root.iter()))

    def test_uyumsoft_ubl_keeps_serials_on_their_own_invoice_line(self):
        items = [
            {
                "code": "SKU-A",
                "description": "Device A",
                "serial_numbers": ["A-1", "A-2"],
                "quantity": "2",
                "unit_price": "50",
                "total_price": "100",
                "tax_rate": "20",
            },
            {
                "code": "SKU-B",
                "description": "Device B",
                "serial_numbers": ["B-1"],
                "quantity": "1",
                "unit_price": "50",
                "total_price": "50",
                "tax_rate": "20",
            },
            {
                "code": "SKU-C",
                "description": "Service",
                "serial_numbers": [],
                "quantity": "1",
                "unit_price": "50",
                "total_price": "50",
                "tax_rate": "20",
            },
        ]

        root = ET.fromstring(build_ubl_invoice(_ubl_invoice(items)))
        lines = [node for node in root.iter() if _local_name(node) == "InvoiceLine"]
        serials_by_line = []
        for line in lines:
            serials_by_line.append(
                [node.text for node in line.iter() if _local_name(node) == "SerialID"]
            )

        self.assertEqual(serials_by_line, [["A-1", "A-2"], ["B-1"], []])

    def test_uyumsoft_ubl_serials_round_trip_through_xml_extractor(self):
        invoice = _ubl_invoice(
            [
                {
                    "code": "SKU-ROUNDTRIP",
                    "description": "Round-trip device",
                    "serial_numbers": ["00123", "SER-2"],
                    "quantity": "2",
                    "unit_price": "100",
                    "total_price": "200",
                    "tax_rate": "20",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "uyumsoft-serials.xml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(build_ubl_invoice(invoice))
            parsed = parse_xml_invoice(path)

        self.assertEqual(parsed["items"][0]["serial_numbers"], ["00123", "SER-2"])

    def test_uyumsoft_draft_body_preserves_only_present_serial_numbers(self):
        invoice = _ubl_invoice(
            [
                {
                    "code": "SKU-WITH-SERIAL",
                    "description": "Serialized device",
                    "serial_numbers": ["SER-001", "SER-002"],
                    "quantity": "2",
                    "unit_price": "100",
                    "total_price": "200",
                    "tax_rate": "20",
                },
                {
                    "code": "SKU-WITHOUT-SERIAL",
                    "description": "Unserialized service",
                    "quantity": "1",
                    "unit_price": "100",
                    "total_price": "100",
                    "tax_rate": "20",
                },
            ]
        )

        root = ET.fromstring(build_invoice_info_body("SaveAsDraft", invoice))
        lines = [node for node in root.iter() if _local_name(node) == "InvoiceLine"]
        serials_by_line = [
            [node.text for node in line.iter() if _local_name(node) == "SerialID"]
            for line in lines
        ]

        self.assertEqual(serials_by_line, [["SER-001", "SER-002"], []])
        self.assertEqual(
            sum(1 for node in root.iter() if _local_name(node) == "ItemInstance"),
            2,
        )

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
