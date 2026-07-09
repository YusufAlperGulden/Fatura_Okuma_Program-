import os
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import shutil
import uuid

# Import our pipeline modules
from extractors.excel_extractor import parse_excel_invoice
from extractors.pdf_extractor import parse_pdf_invoice
from extractors.xml_extractor import parse_xml_invoice
from validators.invoice_validator import validate_invoice
from integrators.mikro_v16_bridge import (
    MikroBridgeError,
    MikroV16SqlClient,
    build_mikro_v16_invoice_package,
)
from integrators.uyumsoft_excel import export_to_uyumsoft_excel
from integrators.uyumsoft_api import send_invoice_to_uyumsoft

app = FastAPI(title="Invoice Pipeline API")

# Serve the static UI files
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class SendMikroV16Request(BaseModel):
    invoice_data: dict | None = None
    action: str | None = "export_package"


def _is_image_extension(ext: str) -> bool:
    return ext in [".jpg", ".jpeg", ".png", ".webp"]


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
    # Save the file temporarily
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    temp_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    file_path = temp_path
    data = {}
    local_error = False
    
    # STAGE 1: Process based on extension (LOCAL EXTRACTION)
    try:
        if ext in ['.xlsx', '.xls', '.csv']:
            data = parse_excel_invoice(file_path)
        elif ext == '.pdf':
            data = parse_pdf_invoice(file_path)
        elif ext == '.xml':
            data = parse_xml_invoice(file_path)
        elif _is_image_extension(ext):
            from extractors.ocr_extractor import parse_image_invoice_ocr
            data = parse_image_invoice_ocr(file_path)
        else:
            os.remove(file_path)
            return ProcessResponse(filename=file.filename, is_valid=False, data=None, errors=[f"Unsupported format: {ext}"])
            
        if not data or not data.get("items"):
            local_error = True
        else:
            # Eger extraction verisi geldiyse, matematigi dogru mu diye kontrol et!
            is_valid_local, local_errors = validate_invoice(data)
            if not is_valid_local:
                local_error = True
            
    except Exception as e:
        local_error = True

    errors = []
    is_valid = False

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
            
            data = extract_invoice_with_ai(file_bytes, mime_type)
            data["_extraction_method"] = "gemini"
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

    # If valid, export to Uyumsoft Master Excel
    if is_valid:
        export_to_uyumsoft_excel([data], "Uyumsoft_Aktarim_Taslagi.xlsx")
        
    # Clean up file asynchronously or let OS handle temp folder
    try:
        os.remove(file_path)
    except:
        pass
        
    return ProcessResponse(
        filename=file.filename,
        is_valid=is_valid,
        data=data,
        errors=errors
    )

@app.post("/send-uyumsoft")
async def send_uyumsoft_api(request: SendUyumsoftRequest):
    """
    Receives invoice data from the UI and forwards it to the Uyumsoft API.
    """
    is_valid, errors = validate_invoice(request.invoice_data or {})
    if not is_valid:
        return {
            "success": False,
            "message": "Invoice data failed local validation.",
            "details": errors,
            "response_code": 400,
        }

    result = send_invoice_to_uyumsoft(request.invoice_data, action=request.action)
    return result

@app.get("/mikro-v16/status")
async def mikro_v16_status():
    return {
        "success": True,
        "connection_configured": bool(os.getenv("MIKRO_V16_ODBC_CONNECTION")),
        "mode": "file_import_first",
        "message": "MikroV16 uses API-key-free package export by default; ODBC is read-only when configured.",
    }

@app.post("/send-mikro-v16")
async def send_mikro_v16(request: SendMikroV16Request):
    action = (request.action or "export_package").lower()

    if action == "test_connection":
        try:
            return MikroV16SqlClient().test_connection()
        except MikroBridgeError as exc:
            return {"success": False, "message": str(exc), "response_code": 400}

    invoice_data = request.invoice_data or {}
    is_valid, errors = validate_invoice(invoice_data)
    if not is_valid:
        return {
            "success": False,
            "message": "Invoice data failed local validation.",
            "details": errors,
            "response_code": 400,
        }

    try:
        result = build_mikro_v16_invoice_package(invoice_data, output_dir=os.path.join("scratch", "mikro_v16"))
    except MikroBridgeError as exc:
        return {"success": False, "message": str(exc), "response_code": 400}

    return {
        "success": True,
        "message": result.message,
        "operation": "MikroV16ImportPackage",
        "response_code": 200,
        "package_id": result.package_id,
        "package_dir": result.package_dir,
        "files": result.files,
        "details": result.manifest,
    }

@app.get("/download_excel")
async def download_excel():
    excel_path = "Uyumsoft_Aktarim_Taslagi.xlsx"
    if os.path.exists(excel_path):
         return FileResponse(path=excel_path, filename="Uyumsoft_Aktarim_Taslagi.xlsx")
    return {"error": "Excel file not generated yet."}
