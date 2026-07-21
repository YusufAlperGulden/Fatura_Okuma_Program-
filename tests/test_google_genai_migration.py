import json
import types
import unittest
from unittest.mock import patch

from extractors import ai_extractor


class _FakeGenerateContentConfig:
    def __init__(self, **kwargs):
        self.response_mime_type = kwargs.get("response_mime_type")
        self.temperature = kwargs.get("temperature")


class _FakePart:
    @staticmethod
    def from_bytes(*, data, mime_type):
        return {"data": data, "mime_type": mime_type}


FAKE_TYPES = types.SimpleNamespace(
    GenerateContentConfig=_FakeGenerateContentConfig,
    Part=_FakePart,
)


class _FakeModels:
    def __init__(self, listed_models=(), responses=None):
        self.listed_models = list(listed_models)
        self.responses = responses or {}
        self.generate_calls = []

    def list(self):
        return iter(self.listed_models)

    def generate_content(self, **kwargs):
        self.generate_calls.append(kwargs)
        result = self.responses[kwargs["model"]]
        if isinstance(result, Exception):
            raise result
        return types.SimpleNamespace(text=result)


class _FakeClient:
    def __init__(self, models):
        self.models = models
        self.closed = False

    def close(self):
        self.closed = True


class GoogleGenAiMigrationTests(unittest.TestCase):
    def test_candidate_models_use_new_sdk_model_listing_contract(self):
        listed = [
            types.SimpleNamespace(
                name="models/gemini-listed",
                supported_actions=["generateContent"],
            ),
            types.SimpleNamespace(
                name="models/not-generative",
                supported_actions=["embedContent"],
            ),
        ]
        client = _FakeClient(_FakeModels(listed_models=listed))

        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-custom"}):
            candidates = ai_extractor._candidate_model_names(client)

        self.assertEqual(candidates[0], "gemini-custom")
        self.assertIn("gemini-listed", candidates)
        self.assertNotIn("not-generative", candidates)

    def test_generation_retries_only_model_selection_errors(self):
        models = _FakeModels(
            responses={
                "gemini-missing": RuntimeError("404 model not found"),
                ai_extractor.DEFAULT_GEMINI_MODEL: '{"items": []}',
            }
        )
        client = _FakeClient(models)

        with (
            patch.dict("os.environ", {"GEMINI_MODEL": "gemini-missing"}),
            patch.object(ai_extractor, "genai_types", FAKE_TYPES),
        ):
            result = ai_extractor._generate_content_with_available_model(
                client, ["invoice", "prompt"]
            )

        self.assertEqual(result, '{"items": []}')
        self.assertEqual(
            [call["model"] for call in models.generate_calls],
            ["gemini-missing", ai_extractor.DEFAULT_GEMINI_MODEL],
        )
        config = models.generate_calls[-1]["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.temperature, 0.0)

    def test_extraction_uses_client_inline_bytes_and_closes_client(self):
        response_data = {
            "invoice_no": "INV-1",
            "subtotal": 100,
            "tax_amount": 20,
            "total_amount": 120,
            "items": [
                {
                    "description": "Device",
                    "quantity": 1,
                    "unit_price": 100,
                    "total_price": 100,
                    "tax_rate": 20,
                    "serial_numbers": "SER-1~SER-2",
                }
            ],
        }
        models = _FakeModels(
            responses={ai_extractor.DEFAULT_GEMINI_MODEL: json.dumps(response_data)}
        )
        client = _FakeClient(models)
        fake_genai = types.SimpleNamespace(Client=lambda **_kwargs: client)

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
            patch.object(ai_extractor, "genai", fake_genai),
            patch.object(ai_extractor, "genai_types", FAKE_TYPES),
        ):
            result = ai_extractor.extract_invoice_with_ai(
                b"fake-pdf", mime_type="application/pdf"
            )

        self.assertTrue(client.closed)
        request = models.generate_calls[0]
        self.assertEqual(
            request["contents"][0],
            {"data": b"fake-pdf", "mime_type": "application/pdf"},
        )
        self.assertIn("invoice_no", request["contents"][1])
        self.assertEqual(result["subtotal"], "100")
        self.assertEqual(result["items"][0]["quantity"], "1")
        self.assertEqual(
            result["items"][0]["serial_numbers"], ["SER-1", "SER-2"]
        )

    def test_missing_new_sdk_has_a_deterministic_error(self):
        with (
            patch.object(ai_extractor, "genai", None),
            patch.object(ai_extractor, "genai_types", None),
        ):
            with self.assertRaisesRegex(RuntimeError, "google-genai"):
                ai_extractor.extract_invoice_with_ai(b"pdf")


if __name__ == "__main__":
    unittest.main()
