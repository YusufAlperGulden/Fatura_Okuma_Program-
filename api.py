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
from extractors.ai_extractor import extract_invoice_with_ai
from validators.invoice_validator import validate_invoice
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
    is_valid = False
    errors = []
    
    # STAGE 1: Process based on extension (LOCAL EXTRACTION)
    try:
        if ext in ['.xlsx', '.xls', '.csv']:
            data = parse_excel_invoice(file_path)
        elif ext == '.pdf':
            data = parse_pdf_invoice(file_path)
        elif ext == '.xml':
            data = parse_xml_invoice(file_path)
        elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
            from extractors.ocr_extractor import parse_image_invoice_ocr
            data = parse_image_invoice_ocr(file_path)
        else:
            os.remove(file_path)
            return ProcessResponse(filename=file.filename, is_valid=False, data=None, errors=[f"Unsupported format: {ext}"])
            
        if not data or not data.get("items"):
            local_error = True
        else:
            is_valid, errors = validate_invoice(data)
            if not is_valid:
                local_error = True
    except Exception as e:
        local_error = True
        errors = [f"Local Extraction Error: {str(e)}"]

    # STAGE 2: FALLBACK TO AI
    if local_error and os.getenv("GEMINI_API_KEY"):
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            mime_type = "application/pdf"
            if ext in ['.jpg', '.jpeg']: mime_type = "image/jpeg"
            elif ext == '.png': mime_type = "image/png"
            elif ext == '.webp': mime_type = "image/webp"
            
            data = extract_invoice_with_ai(file_bytes, mime_type)
            is_valid, errors = validate_invoice(data)
        except Exception as e:
            errors.append(f"AI Extraction Error: {str(e)}")
            is_valid = False
    elif local_error and not data and ext in ['.jpg', '.jpeg', '.png']:
        errors = ["Resim formatı yüklendi ancak GEMINI_API_KEY ortam değişkeni ayarlanmadığı için Yapay Zeka devreye giremedi."]
    elif local_error and not data:
        errors = ["Fatura okunamadı ve GEMINI_API_KEY ayarlanmadığı için Yapay Zeka (Fallback) devreye giremedi."]

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

@app.get("/download_excel")
async def download_excel():
    excel_path = "Uyumsoft_Aktarim_Taslagi.xlsx"
    if os.path.exists(excel_path):
         return FileResponse(path=excel_path, filename="Uyumsoft_Aktarim_Taslagi.xlsx")
    return {"error": "Excel file not generated yet."}
