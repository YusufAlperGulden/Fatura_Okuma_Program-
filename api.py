import os
import sys
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
from validators.invoice_validator import validate_invoice
from integrators.uyumsoft_api import enrich_invoice_customer_from_uyumsoft, send_invoice_to_uyumsoft
from utils.serial_numbers import merge_invoice_serial_numbers

app = FastAPI(title="Invoice Pipeline API")

# Serve the static UI files
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

@app.get("/health")
def health_check():
    return {"status": "ok"}

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
    
    try:
        # Save the file temporarily
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename)[1].lower()
        temp_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
        
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
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
                data = merge_invoice_serial_numbers(ai_data, local_data_for_serials)
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
            is_valid, validation_errors = validate_invoice(data)
            errors.extend(validation_errors)
            if is_valid:
                data = enrich_invoice_customer_from_uyumsoft(data)
        elif local_errors:
            errors.extend(local_errors)

        raw_text = data.pop("_raw_text", None) if isinstance(data, dict) else None

        if not is_valid:
            if raw_text and os.getenv("DEBUG_PDF_TEXT", "").lower() in {"1", "true", "yes"}:
                errors.append(f"DEBUG RAW TEXT:\n{raw_text}")
            
        # Clean up file asynchronously or let OS handle temp folder
        try:
            os.remove(file_path)
        except:
            pass

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
            status_code=200,
            content={
                "filename": file.filename if file else "",
                "is_valid": False,
                "data": None,
                "errors": [
                    f"Sunucu hatası yakalandı: {type(e).__name__}: {str(e)}"
                ],
            },
        )

@app.post("/validate")
async def api_validate(invoice_data: dict):
    from validators.invoice_validator import validate_invoice
    import copy
    
    data_copy = copy.deepcopy(invoice_data)
    is_valid, errors = validate_invoice(data_copy)
    
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

    # The payload reaching this endpoint is the user-reviewed final version.
    # Work on a copy and never run customer enrichment again here: doing so
    # used to overwrite manual edits with the registered Uyumsoft title.
    invoice_data = copy.deepcopy(request.invoice_data or {})
    is_valid, errors = validate_invoice(invoice_data)
    if not is_valid:
        return {
            "success": False,
            "message": "Invoice data failed local validation.",
            "details": errors,
            "response_code": 400,
        }

    customer_name = str(invoice_data.get("customer_name") or "").strip()
    if customer_name:
        invoice_data["customer_name"] = customer_name
        invoice_data["customer_title"] = customer_name

    result = send_invoice_to_uyumsoft(invoice_data, action="draft")
    return result
