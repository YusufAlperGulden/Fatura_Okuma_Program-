import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import our pipeline modules
from extractors.excel_extractor import parse_excel_invoice
from extractors.pdf_extractor import parse_pdf_invoice
from extractors.xml_extractor import parse_xml_invoice
from validators.invoice_validator import recalculate_invoice_totals, validate_invoice
from integrators.uyumsoft_api import (
    enrich_invoice_customer_from_uyumsoft,
    normalize_uyumsoft_environment,
    send_invoice_to_uyumsoft,
)
from utils.serial_numbers import safe_merge_ai_data

app = FastAPI(title="Invoice Pipeline API")

# Ensure database is initialized (especially for ephemeral environments like Render)
from database import init_db
init_db()

# Serve the static UI files
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/runtime-config")
def runtime_config():
    """Expose only non-secret UI settings for the active Uyumsoft environment."""
    environment = normalize_uyumsoft_environment()

    default_portal_url = (
        "http://portal-test.uyumsoft.com.tr/Taslak"
        if environment == "test"
        else "https://www.uyumsoft.com/kullanici-girisi"
    )
    return {
        "uyumsoft_environment": environment,
        "uyumsoft_portal_url": (
            os.getenv("UYUMSOFT_PORTAL_URL", "").strip() or default_portal_url
        ),
    }

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class ProcessResponse(BaseModel):
    filename: str
    is_valid: bool
    data: dict | None
    errors: list[str]

class SendUyumsoftRequest(BaseModel):
    invoice_data: dict
    action: str | None = None
    environment: str | None = None
    username: str | None = None
    password: str | None = None


DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class _UploadTooLargeError(Exception):
    pass


class _LimitedUploadReader:
    def __init__(self, source, limit: int):
        self.source = source
        self.limit = limit
        self.total = 0

    def read(self, size=-1):
        chunk = self.source.read(size)
        self.total += len(chunk)
        if self.total > self.limit:
            raise _UploadTooLargeError
        return chunk


def _max_upload_bytes() -> int:
    raw_value = os.getenv("MAX_UPLOAD_BYTES", "").strip()
    if not raw_value:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else DEFAULT_MAX_UPLOAD_BYTES

def _is_image_extension(ext: str) -> bool:
    return ext in [".jpg", ".jpeg", ".png", ".webp"]


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}


def _is_gemini_quota_error(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text or "quota" in text or "rate-limit" in text or "rate limit" in text


def _validate_candidate(data: dict | None) -> tuple[bool, list[str]]:
    if not data:
        return False, ["Fatura verisi okunamadi."]
    return validate_invoice(data)


def _mime_type_for_extension(ext: str) -> str:
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "application/pdf"


def _try_gemini_extraction(file_path: str, ext: str) -> tuple[dict, bool, list[str]]:
    if not os.getenv("GEMINI_API_KEY"):
        return {}, False, ["GEMINI_API_KEY ayarlanmadigi icin Gemini devreye giremedi."]

    from extractors.ai_extractor import extract_invoice_with_ai

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    data = extract_invoice_with_ai(file_bytes, _mime_type_for_extension(ext))
    data["_extraction_method"] = "gemini"
    is_valid, errors = validate_invoice(data)
    return data, is_valid, errors


@app.post("/upload", response_model=ProcessResponse)
async def upload_invoice(file: UploadFile = File(...)):
    import traceback
    from fastapi.responses import JSONResponse

    temp_path = None
    try:
        # Save the file temporarily
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.pdf', '.xml', '.csv', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.webp']:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=415, content={"is_valid": False, "errors": [f"Unsupported format: {ext}"], "data": None, "filename": file.filename})
        temp_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
        
        try:
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(
                    _LimitedUploadReader(file.file, _max_upload_bytes()),
                    buffer,
                    length=1024 * 1024,
                )
        except _UploadTooLargeError:
            return JSONResponse(
                status_code=413,
                content={
                    "is_valid": False,
                    "errors": [
                        f"Dosya boyutu izin verilen {_max_upload_bytes()} bayt sınırını aşıyor."
                    ],
                    "data": None,
                    "filename": file.filename or "",
                },
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "is_valid": False,
                    "errors": [f"File write error: {str(e)}"],
                    "data": None,
                    "filename": file.filename or "",
                },
            )
            
        file_path = temp_path
        data = {}
        local_error = False
        local_errors = []
        
        # STAGE 1: Process based on extension (LOCAL EXTRACTION)
        try:
            if ext in ['.xlsx', '.xls', '.csv']:
                data = parse_excel_invoice(file_path)
                if data: data["_extraction_method"] = "Yerel Okuyucu (Excel)"
            elif ext == '.pdf':
                data = parse_pdf_invoice(file_path)
                if data: data["_extraction_method"] = "Yerel Okuyucu (PDF)"
            elif ext == '.xml':
                data = parse_xml_invoice(file_path)
                if data: data["_extraction_method"] = "Yerel Okuyucu (XML)"
            elif _is_image_extension(ext):
                from extractors.ocr_extractor import parse_image_invoice_ocr
                data = parse_image_invoice_ocr(file_path)
                if data: data["_extraction_method"] = "Yerel Okuyucu (OCR)"
            else:
                os.remove(file_path)
                return ProcessResponse(filename=file.filename, is_valid=False, data=None, errors=[f"Unsupported format: {ext}"])
                
            if not data or not data.get("items"):
                local_error = True
                local_errors = ["Yerel okuyucu fatura kalemlerini bulamadi."]
            else:
                # Eger extraction verisi geldiyse, matematigi dogru mu diye kontrol et!
                is_valid_local, local_errors = validate_invoice(data)
                if not is_valid_local:
                    local_error = True
                    if os.getenv("DEBUG_PDF_TEXT", "").lower() in {"1", "true", "yes"} and "_raw_text" in data:
                        local_errors.append(f"DEBUG RAW TEXT:\n{data['_raw_text']}")
                
        except Exception as e:
            local_error = True
            local_errors = [f"Yerel okuyucu hatasi: {str(e)}"]

        errors = []
        is_valid = False

        # STAGE 1B: Optional OCR fallback. Tesseract is slow on Render, so keep it off
        # unless scanned PDFs make it necessary.
        if local_error and ext == ".pdf" and _env_enabled("USE_TESSERACT_FALLBACK"):
            try:
                from extractors.ocr_extractor import parse_pdf_invoice_ocr

                ocr_data = parse_pdf_invoice_ocr(file_path)
                ocr_valid, ocr_errors = _validate_candidate(ocr_data)
                if ocr_valid:
                    data = ocr_data
                    data["_extraction_method"] = "Yerel Okuyucu (Tesseract OCR)"
                    local_error = False
                elif ocr_data and len(ocr_data.get("items", [])) > len(data.get("items", [])):
                    data = ocr_data
                    local_errors = ocr_errors
            except Exception as e:
                local_errors.append(f"Tesseract OCR hatasi: {str(e)}")

        # Preserve deterministic local serials if the AI fallback replaces the
        # rest of a partially extracted invoice.
        local_data_for_serials = data if isinstance(data, dict) else None

        # STAGE 2: FALLBACK TO AI (Only if local extraction failed)
        if local_error and os.getenv("GEMINI_API_KEY") and (ext == ".pdf" or _is_image_extension(ext)):
            try:
                from extractors.ai_extractor import extract_invoice_with_ai
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                mime_type = "application/pdf"
                if ext in ['.jpg', '.jpeg']: mime_type = "image/jpeg"
                elif ext == '.png': mime_type = "image/png"
                elif ext == '.webp': mime_type = "image/webp"
                
                ai_data = extract_invoice_with_ai(file_bytes, mime_type)
                data = safe_merge_ai_data(ai_data, local_data_for_serials)
                data["_extraction_method"] = "Google Gemini Yapay Zeka"
            except Exception as e:
                if _is_gemini_quota_error(e):
                    errors.append("Gemini limiti doldu; yerel okuyucu sonucu korundu.")
                else:
                    errors.append(f"AI Extraction Error: {str(e)}")
                
        elif local_error and (ext == ".pdf" or _is_image_extension(ext)) and not os.getenv("GEMINI_API_KEY"):
            errors.append("Gemini API anahtari olmadigi icin son yedek okuma adimi calistirilamadi.")
        elif local_error and not data and _is_image_extension(ext):
            errors.append("Resim formatı yüklendi ancak GEMINI_API_KEY ortam değişkeni ayarlanmadığı için Yapay Zeka devreye giremedi.")
        elif local_error and not data:
            errors.append("Fatura okunamadı ve GEMINI_API_KEY ayarlanmadığı için Yapay Zeka (Fallback) devreye giremedi.")
            
        if data:
            data = enrich_invoice_customer_from_uyumsoft(data)
            is_valid, validation_errors = validate_invoice(data)
            if is_valid:
                errors = []
            errors.extend(validation_errors)
        elif local_errors:
            errors.extend(local_errors)

        raw_text = data.pop("_raw_text", None) if isinstance(data, dict) else None

        if not is_valid:
            if raw_text and os.getenv("DEBUG_PDF_TEXT", "").lower() in {"1", "true", "yes"}:
                errors.append(f"DEBUG RAW TEXT:\n{raw_text}")
            
        # Database save removed
            
        return ProcessResponse(
            filename=file.filename,
            is_valid=is_valid,
            data=data,
            errors=errors
        )
    except Exception as e:
        print("UPLOAD_FATAL_ERROR")
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "filename": file.filename if file else "",
                "is_valid": False,
                "data": None,
                "errors": [
                    f"Sunucu hatası yakalandı: {type(e).__name__}: {str(e)}"
                ],
            },
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

@app.post("/validate")
async def api_validate(invoice_data: dict):
    import copy
    from fastapi.responses import JSONResponse
    
    try:
        data_copy = copy.deepcopy(invoice_data)
        recalculate_invoice_totals(data_copy)
        is_valid, errors = validate_invoice(data_copy)
    except Exception as e:
        return JSONResponse(status_code=422, content={"is_valid": False, "errors": [str(e)], "data": None})
    
    return {
        "is_valid": is_valid,
        "errors": errors,
        "data": data_copy
    }

@app.post("/send-uyumsoft")
async def send_uyumsoft_api(request: SendUyumsoftRequest):
    """
    Receives invoice data from the UI and forwards it to the Uyumsoft API.
    """
    import copy
    from fastapi.responses import JSONResponse

    # The payload reaching this endpoint is the user-reviewed final version.
    # Work on a copy and never run customer enrichment again here: doing so
    # used to overwrite manual edits with the registered Uyumsoft title.
    invoice_data = copy.deepcopy(request.invoice_data or {})
    
    try:
        is_valid, errors = validate_invoice(invoice_data)
    except Exception as e:
        return JSONResponse(
            status_code=422,
            content={"success": False, "message": str(e), "response_code": 422}
        )
        
    if not is_valid:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Invoice data failed local validation.",
                "details": errors,
                "response_code": 400,
            }
        )

    customer_name = str(invoice_data.get("customer_name") or "").strip()
    if customer_name:
        invoice_data["customer_name"] = customer_name
        invoice_data["customer_title"] = customer_name

    result = send_invoice_to_uyumsoft(
        invoice_data,
        action="draft",
        environment=request.environment,
        prod_username=request.username,
        prod_password=request.password,
    )
    
    if isinstance(result, dict) and not result.get("success", True):
        status = result.get("response_code") or 500
        if isinstance(status, int) and status >= 400:
            return JSONResponse(status_code=status, content=result)
            
    # Save to history if successful
    try:
        from database import save_invoice
        save_invoice(invoice_data, is_valid=True)
    except Exception as e:
        print(f"Error saving to history: {e}")
            
    return result

@app.get("/api/history/dashboard")
def api_history_dashboard():
    """Returns dashboard statistics (total revenue, invoice count, and trend data)."""
    from database import get_dashboard_stats
    try:
        stats = get_dashboard_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "message": "Failed to load dashboard stats", "details": str(e)})

@app.get("/api/history/invoices")
def api_history_invoices(page: int = 1, limit: int = 20):
    """Returns paginated history of invoices."""
    from database import get_paginated_invoices
    try:
        data = get_paginated_invoices(page=page, limit=limit)
        return {"success": True, "data": data}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "message": "Failed to load history", "details": str(e)})

