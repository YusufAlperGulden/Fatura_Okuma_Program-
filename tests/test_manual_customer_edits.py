import asyncio
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from api import SendUyumsoftRequest, send_uyumsoft_api
from integrators.uyumsoft_api import build_invoice_info_body


OLD_CUSTOMER_NAME = "Katlan Yazılım Elektronik Ve Pazarlama"
EDITED_CUSTOMER_NAME = "ALPER2004"


def _valid_invoice():
    return {
        "invoice_no": "10",
        "date": "10.04.2026",
        "time": "17:22",
        "customer_tax_id": "16811884906",
        "customer_name": EDITED_CUSTOMER_NAME,
        "customer_title": OLD_CUSTOMER_NAME,
        "items": [
            {
                "code": "1390.151",
                "description": "Elektronik Barkod Kodlayıcı / Yazıcı",
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
    }


def _texts_for_local_name(xml_text, local_name):
    root = ET.fromstring(xml_text)
    return [
        element.text
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == local_name
    ]


class ManualCustomerEditTests(unittest.TestCase):
    def test_serializer_prefers_edited_name_over_stale_customer_title(self):
        body = build_invoice_info_body("SaveAsDraft", _valid_invoice())

        self.assertIn(EDITED_CUSTOMER_NAME, body)
        self.assertNotIn(OLD_CUSTOMER_NAME, body)
        self.assertIn(f'Title="{EDITED_CUSTOMER_NAME}"', body)
        self.assertEqual(
            _texts_for_local_name(body, "FirstName"), [EDITED_CUSTOMER_NAME]
        )
        self.assertEqual(_texts_for_local_name(body, "FamilyName"), [])

    def test_multi_word_tckn_name_is_split_without_repetition(self):
        invoice = _valid_invoice()
        invoice["customer_name"] = "  Yusuf   Alper   Gülden  "
        invoice["customer_title"] = "Yusuf Alper Gülden"

        body = build_invoice_info_body("SaveAsDraft", invoice)

        self.assertEqual(_texts_for_local_name(body, "FirstName"), ["Yusuf Alper"])
        self.assertEqual(_texts_for_local_name(body, "FamilyName"), ["Gülden"])
        self.assertEqual(body.count('Title="Yusuf Alper Gülden"'), 1)

    def test_vkn_company_name_remains_a_single_party_name(self):
        invoice = _valid_invoice()
        invoice["customer_tax_id"] = "1234567890"
        invoice["customer_name"] = "Örnek Şirket A.Ş."
        invoice["customer_title"] = "Örnek Şirket A.Ş."

        body = build_invoice_info_body("SaveAsDraft", invoice)

        self.assertIn(
            "<cac:PartyName><cbc:Name>Örnek Şirket A.Ş.</cbc:Name></cac:PartyName>",
            body,
        )
        self.assertEqual(_texts_for_local_name(body, "Person"), [])

    def test_send_endpoint_preserves_user_reviewed_customer_name(self):
        request = SendUyumsoftRequest(invoice_data=_valid_invoice(), action="draft")
        success = {
            "success": True,
            "message": "Taslak oluşturuldu.",
            "response_code": 200,
        }

        with (
            patch(
                "api.enrich_invoice_customer_from_uyumsoft",
                side_effect=AssertionError(
                    "Final user data must not be enriched again during send."
                ),
            ) as enrich,
            patch("api.send_invoice_to_uyumsoft", return_value=success) as send,
        ):
            result = asyncio.run(send_uyumsoft_api(request))

        enrich.assert_not_called()
        send.assert_called_once()
        sent_invoice = send.call_args.args[0]
        self.assertEqual(send.call_args.kwargs["action"], "draft")
        self.assertEqual(sent_invoice["customer_name"], EDITED_CUSTOMER_NAME)
        self.assertEqual(sent_invoice["customer_title"], EDITED_CUSTOMER_NAME)
        self.assertEqual(result, success)


if __name__ == "__main__":
    unittest.main()
