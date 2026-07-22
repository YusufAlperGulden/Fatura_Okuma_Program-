"""HTTP routes for the isolated, secure AI archive search feature."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from archive_ai_search import (
    AIInterpretRequest,
    AIResultsRequest,
    ArchiveAIConfigurationError,
    ArchiveAIProviderError,
    ArchiveAIResponseError,
    ArchiveAISearchTimeoutError,
    consume_ai_rate_limit,
    consume_ai_results_rate_limit,
    execute_archive_search,
    interpret_archive_query,
    serialize_query_spec,
)


router = APIRouter(prefix="/api/history/ai", tags=["AI archive search"])


@router.post("/interpret")
def api_history_ai_interpret(payload: AIInterpretRequest, request: Request):
    client_key = request.client.host if request.client else "unknown"
    retry_after = consume_ai_rate_limit(client_key)
    if retry_after:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "success": False,
                "message": "AI arama sınırına ulaşıldı. Lütfen kısa süre sonra tekrar deneyin.",
            },
        )

    try:
        spec, explanation = interpret_archive_query(payload.query)
    except ArchiveAIConfigurationError:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": "AI arama şu anda yapılandırılmamış.",
            },
        )
    except (ArchiveAIProviderError, ArchiveAIResponseError):
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "message": "AI arama isteği güvenli bir filtreye dönüştürülemedi.",
            },
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "AI arama sırasında hata oluştu."},
        )

    return {
        "success": True,
        "data": {
            "spec": serialize_query_spec(spec),
            "explanation": explanation,
        },
    }


@router.post("/results")
def api_history_ai_results(payload: AIResultsRequest, request: Request):
    client_key = request.client.host if request.client else "unknown"
    retry_after = consume_ai_results_rate_limit(client_key)
    if retry_after:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "success": False,
                "message": "Arşiv arama sınırına ulaşıldı. Lütfen kısa süre sonra tekrar deneyin.",
            },
        )

    try:
        data = execute_archive_search(
            payload.spec,
            page=payload.page,
            limit=payload.limit,
        )
    except ArchiveAISearchTimeoutError:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": "Arşiv sorgusu zaman sınırını aştı. Lütfen filtreyi daraltın.",
            },
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "AI arama sonuçları yüklenemedi.",
            },
        )
    return {"success": True, "data": data}
