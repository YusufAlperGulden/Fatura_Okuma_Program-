import json
import types
from unittest.mock import patch

from extractors import ai_extractor
from utils.serial_numbers import safe_merge_ai_data


class _FakePart:
    @staticmethod
    def from_bytes(*, data, mime_type):
        return {"data": data, "mime_type": mime_type}


class _FakeClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _mufemu_ai_payload():
    return {
        "invoice_no": "TEST-USD-1",
        "currency": "TRY",
        "has_usd_mention": True,
        "currency_evidence": (
            "İŞ BU FATURA BEDELİ 4.608,00 USD OLUP, "
            "BEDELİ USD OLARAK TAHSİL EDİLECEKTİR."
        ),
        "exchange_rate": 47.0517,
        "subtotal": 180678.53,
        "discount_amount": 0,
        "tax_amount": 36135.71,
        "total_amount": 216814.23,
        "foreign_total": 4608,
        "items": [
            {
                "code": "4100.0382",
                "description": "NXP Mifare Desfire",
                "quantity": 2000,
                "unit_price": 90.34,
                "total_price": 180678.53,
                "tax_rate": 20,
                "serial_numbers": [],
            }
        ],
    }


def test_usd_settlement_sentence_converts_tl_amounts_deterministically():
    result = ai_extractor._stringify_amount_fields(_mufemu_ai_payload())

    assert result["currency"] == "USD"
    assert result["document_currency"] == "USD"
    assert result["settlement_currency"] == "USD"
    assert result["accounting_currency"] == "TRY"
    assert result["exchange_rate"] == "47.0517"
    assert result["subtotal"] == "3840.00"
    assert result["tax_amount"] == "768.00"
    assert result["total_amount"] == "4608.00"
    assert result["foreign_total"] == "4608.00"
    assert result["local_subtotal"] == "180678.53"
    assert result["local_tax_amount"] == "36135.71"
    assert result["local_total"] == "216814.23"
    assert result["fx_math_is_valid"] is True

    item = result["items"][0]
    assert item["unit_price"] == "1.92"
    assert item["total_price"] == "3840.00"
    assert item["local_unit_price"] == "90.34"
    assert item["local_total_price"] == "180678.53"
    assert item["amount_currency"] == "USD"
    assert item["local_amount_currency"] == "TRY"


def test_usd_token_in_returned_invoice_text_is_enough_even_without_boolean_flag():
    payload = _mufemu_ai_payload()
    payload.pop("has_usd_mention")
    payload["notes"] = "BEDELİ USD OLARAK TAHSİL EDİLECEKTİR."

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["has_usd_mention"] is True
    assert result["currency"] == "USD"
    assert result["total_amount"] == "4608.00"


def test_non_usd_invoice_is_not_relabelled_or_converted():
    payload = {
        "currency": "TRY",
        "has_usd_mention": False,
        "subtotal": 100,
        "tax_amount": 20,
        "total_amount": 120,
        "items": [],
    }

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["currency"] == "TRY"
    assert result["total_amount"] == "120"
    assert "document_currency" not in result
    assert "local_total" not in result


def test_missing_rate_preserves_try_sources_without_mislabeling_them_as_usd():
    payload = _mufemu_ai_payload()
    payload["exchange_rate"] = None
    payload["foreign_total"] = None

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["currency"] == "USD"
    assert result["fx_conversion_required"] is True
    assert result["local_subtotal"] == "180678.53"
    assert result["local_tax_amount"] == "36135.71"
    assert result["local_total"] == "216814.23"
    assert result["subtotal"] is None
    assert result["tax_amount"] is None
    assert result["total_amount"] is None
    assert result["items"][0]["local_unit_price"] == "90.34"
    assert result["items"][0]["unit_price"] is None


def test_ai_usd_label_with_try_accounting_values_is_still_converted():
    payload = _mufemu_ai_payload()
    payload["currency"] = "USD"
    payload["document_currency"] = "USD"
    payload["settlement_currency"] = "USD"
    payload["accounting_currency"] = "TRY"
    payload["local_subtotal"] = payload["subtotal"]
    payload["local_tax_amount"] = payload["tax_amount"]
    payload["local_total"] = payload["total_amount"]
    payload["items"][0]["local_unit_price"] = payload["items"][0]["unit_price"]
    payload["items"][0]["local_total_price"] = payload["items"][0]["total_price"]

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["subtotal"] == "3840.00"
    assert result["tax_amount"] == "768.00"
    assert result["total_amount"] == "4608.00"
    assert result["items"][0]["unit_price"] == "1.92"
    assert result["items"][0]["total_price"] == "3840.00"


def test_ai_try_accounting_converts_even_when_local_fields_are_omitted():
    payload = {
        "currency": "USD",
        "document_currency": "USD",
        "settlement_currency": "USD",
        "accounting_currency": "TRY",
        "has_usd_mention": True,
        "exchange_rate": 40,
        "subtotal": 1000,
        "tax_amount": 200,
        "total_amount": 1200,
        "items": [
            {
                "quantity": 1,
                "unit_price": 1000,
                "total_price": 1000,
                "tax_rate": 20,
            }
        ],
    }

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["subtotal"] == "25.00"
    assert result["tax_amount"] == "5.00"
    assert result["total_amount"] == "30.00"
    assert result["local_total"] == "1200"
    assert result["items"][0]["unit_price"] == "25.00"
    assert result["items"][0]["total_price"] == "25.00"


def test_already_converted_ai_usd_values_are_not_divided_twice():
    payload = _mufemu_ai_payload()
    payload.update(
        {
            "currency": "USD",
            "document_currency": "USD",
            "settlement_currency": "USD",
            "accounting_currency": "TRY",
            "subtotal": 3840,
            "tax_amount": 768,
            "total_amount": 4608,
            "local_subtotal": 180678.53,
            "local_tax_amount": 36135.71,
            "local_total": 216814.23,
        }
    )
    payload["items"][0].update(
        {
            "unit_price": 1.92,
            "total_price": 3840,
            "local_unit_price": 90.34,
            "local_total_price": 180678.53,
        }
    )

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["subtotal"] == "3840"
    assert result["tax_amount"] == "768"
    assert result["total_amount"] == "4608.00"
    assert result["items"][0]["unit_price"] == "1.92"
    assert result["items"][0]["total_price"] == "3840"


def test_ai_can_derive_printed_rate_from_local_and_foreign_totals():
    payload = _mufemu_ai_payload()
    payload["currency"] = "USD"
    payload["accounting_currency"] = "TRY"
    payload["exchange_rate"] = None
    payload["local_subtotal"] = payload["subtotal"]
    payload["local_tax_amount"] = payload["tax_amount"]
    payload["local_total"] = payload["total_amount"]

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["exchange_rate"] == "47.051699"
    assert result["subtotal"] == "3840.00"
    assert result["tax_amount"] == "768.00"
    assert result["total_amount"] == "4608.00"
    assert result["fx_conversion_required"] is False


def test_ai_conversion_keeps_unit_price_precision_needed_by_ubl():
    payload = _mufemu_ai_payload()
    payload["exchange_rate"] = 40
    payload["subtotal"] = 1000
    payload["tax_amount"] = 200
    payload["total_amount"] = 1200
    payload["foreign_total"] = 30
    payload["items"][0].update(
        quantity=1000,
        unit_price=1,
        total_price=1000,
    )

    result = ai_extractor._stringify_amount_fields(payload)

    assert result["items"][0]["unit_price"] == "0.025"
    assert result["items"][0]["total_price"] == "25.00"


def test_actual_gemini_request_contains_usd_rules_and_extended_schema_without_network():
    payload = _mufemu_ai_payload()
    captured = {}
    client = _FakeClient()

    def fake_generate(_client, input_data):
        captured["prompt"] = input_data[1]
        return json.dumps(payload)

    fake_types = types.SimpleNamespace(Part=_FakePart)
    with (
        patch.object(ai_extractor, "_require_genai_sdk"),
        patch.object(ai_extractor, "_create_client", return_value=client),
        patch.object(
            ai_extractor,
            "_generate_content_with_available_model",
            side_effect=fake_generate,
        ),
        patch.object(ai_extractor, "genai_types", fake_types),
    ):
        result = ai_extractor.extract_invoice_with_ai(
            b"fake invoice", mime_type="application/pdf"
        )

    assert client.closed is True
    prompt = captured["prompt"]
    assert "HERHANGI BIR YERINDE" in prompt
    assert "BEDELI USD OLARAK TAHSIL" in prompt
    assert '"has_usd_mention"' in prompt
    assert '"document_currency"' in prompt
    assert '"settlement_currency"' in prompt
    assert '"foreign_total"' in prompt
    assert '"local_total"' in prompt
    assert result["currency"] == "USD"


def test_local_try_fallback_does_not_overwrite_ai_usd_currency_decision():
    ai_result = ai_extractor._stringify_amount_fields(_mufemu_ai_payload())
    local_result = {
        "invoice_no": "LOCAL-INV-1",
        "customer_tax_id": "1234567890",
        "currency": "TRY",
        "exchange_rate": "47.0517",
        "items": [],
    }

    merged = safe_merge_ai_data(ai_result, local_result)

    assert merged["invoice_no"] == "LOCAL-INV-1"
    assert merged["customer_tax_id"] == "1234567890"
    assert merged["currency"] == "USD"
    assert merged["document_currency"] == "USD"
    assert merged["settlement_currency"] == "USD"


def test_local_exchange_rate_fills_only_when_ai_omits_it():
    ai_result = {
        "currency": "USD",
        "document_currency": "USD",
        "settlement_currency": "USD",
        "has_usd_mention": True,
        "exchange_rate": None,
        "items": [],
    }
    local_result = {
        "currency": "TRY",
        "exchange_rate": "47,0517",
        "items": [],
    }

    merged = safe_merge_ai_data(ai_result, local_result)

    assert merged["currency"] == "USD"
    assert merged["exchange_rate"] == "47,0517"


def test_local_usd_evidence_recovers_ai_try_result_during_fallback():
    ai_result = {
        "currency": "TRY",
        "subtotal": "180678.53",
        "tax_amount": "36135.71",
        "total_amount": "216814.23",
        "items": [
            {
                "code": "4100.0382",
                "quantity": "2000",
                "unit_price": "90.34",
                "total_price": "180678.53",
                "tax_rate": "20",
            }
        ],
    }
    local_result = _mufemu_ai_payload()
    local_result.update(
        {
            "currency": "USD",
            "document_currency": "USD",
            "settlement_currency": "USD",
            "accounting_currency": "TRY",
            "local_subtotal": "180678.53",
            "local_tax_amount": "36135.71",
            "local_total": "216814.23",
        }
    )
    local_result["items"][0].update(
        {
            "local_unit_price": "90.34",
            "local_total_price": "180678.53",
            "local_amount_currency": "TRY",
        }
    )

    merged = safe_merge_ai_data(ai_result, local_result)
    normalized = ai_extractor._stringify_amount_fields(merged)

    assert normalized["currency"] == "USD"
    assert normalized["subtotal"] == "3840.00"
    assert normalized["tax_amount"] == "768.00"
    assert normalized["total_amount"] == "4608.00"
    assert normalized["items"][0]["unit_price"] == "1.92"
    assert normalized["items"][0]["total_price"] == "3840.00"
