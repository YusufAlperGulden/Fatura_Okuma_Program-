import asyncio
import json
from io import BytesIO
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

import api
from api import SendUyumsoftRequest


def _response_json(response: JSONResponse) -> dict:
    return json.loads(response.body.decode("utf-8"))


def _upload(filename: str = "invoice.pdf") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(b"test invoice"))


def _candidate_without_customer_name() -> dict:
    return {
        "invoice_no": "LOOKUP-1",
        "date": "17.07.2026",
        "customer_tax_id": "1234567890",
        "customer_name": "",
        "items": [
            {
                "description": "Test item",
                "quantity": "1",
                "unit_price": "100,00",
                "total_price": "100,00",
                "tax_rate": "20",
            }
        ],
        "subtotal": "100,00",
        "tax_amount": "20,00",
        "total_amount": "120,00",
        "currency": "TRY",
    }


def test_invalid_send_uses_real_http_400_and_never_calls_uyumsoft():
    request = SendUyumsoftRequest(invoice_data={"items": []}, action="draft")

    with (
        patch("api.validate_invoice", return_value=(False, ["invalid invoice"])),
        patch("api.send_invoice_to_uyumsoft") as sender,
    ):
        response = asyncio.run(api.send_uyumsoft_api(request))

    sender.assert_not_called()
    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert _response_json(response)["details"] == ["invalid invoice"]


def test_validation_exception_is_a_422_response_not_an_uncaught_500():
    request = SendUyumsoftRequest(
        invoice_data={"items": ["not-an-item-object"]}, action="draft"
    )

    with (
        patch("api.validate_invoice", side_effect=TypeError("item must be a dict")),
        patch("api.send_invoice_to_uyumsoft") as sender,
    ):
        response = asyncio.run(api.send_uyumsoft_api(request))

    sender.assert_not_called()
    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert _response_json(response)["success"] is False


def test_validate_endpoint_handles_malformed_structure_as_422():
    with patch("api.validate_invoice", side_effect=AttributeError("bad item")):
        response = asyncio.run(api.api_validate({"items": [17]}))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert _response_json(response)["is_valid"] is False


def test_failed_uyumsoft_result_sets_the_matching_http_error_status():
    request = SendUyumsoftRequest(invoice_data={"items": [{}]}, action="draft")
    failure = {
        "success": False,
        "message": "Uyumsoft unavailable",
        "response_code": 503,
    }

    with (
        patch("api.validate_invoice", return_value=(True, [])),
        patch("api.send_invoice_to_uyumsoft", return_value=failure),
    ):
        response = asyncio.run(api.send_uyumsoft_api(request))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert _response_json(response) == failure


def test_fatal_upload_returns_http_500_and_always_removes_partial_temp_file(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))

    with patch("api.shutil.copyfileobj", side_effect=RuntimeError("disk write failed")):
        response = asyncio.run(api.upload_invoice(_upload()))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert list(tmp_path.iterdir()) == []


def test_missing_customer_name_is_enriched_before_local_final_validation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    candidate = _candidate_without_customer_name()

    def fake_validate(data):
        if data.get("customer_name") == "Registered Customer A.S.":
            return True, []
        return False, ["Customer name is missing"]

    def fake_enrich(data):
        data["customer_name"] = "Registered Customer A.S."
        data["customer_title"] = "Registered Customer A.S."
        return data

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("api.parse_pdf_invoice", return_value=candidate),
        patch("api.validate_invoice", side_effect=fake_validate),
        patch(
            "api.enrich_invoice_customer_from_uyumsoft", side_effect=fake_enrich
        ) as enrich,
    ):
        response = asyncio.run(api.upload_invoice(_upload()))

    assert response.is_valid is True
    assert response.data["customer_name"] == "Registered Customer A.S."
    assert response.errors == []
    assert enrich.call_count >= 1
    assert list(tmp_path.iterdir()) == []


def test_unsupported_upload_format_uses_http_415_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))

    response = asyncio.run(api.upload_invoice(_upload("invoice.exe")))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 415
    assert list(tmp_path.iterdir()) == []
