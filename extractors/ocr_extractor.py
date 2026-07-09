import pytesseract
from pdf2image import convert_from_path
import os
from extractors.pdf_extractor import parse_invoice_text

# Set these if Tesseract/Poppler are not in PATH.
# Example for Windows:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# POPPLER_PATH = r'C:\poppler\bin'
POPPLER_PATH = None 

def extract_text_via_ocr(file_path: str) -> str:
    print(f"Applying OCR on {file_path}...")
    try:
        # Convert PDF to list of images
        if POPPLER_PATH and os.path.exists(POPPLER_PATH):
            pages = convert_from_path(file_path, dpi=150, poppler_path=POPPLER_PATH, thread_count=1)
        else:
            pages = convert_from_path(file_path, dpi=150, thread_count=1)
            
        full_text = ""
        for page in pages:
            # Sıkıştırma kaldırıldı, çünkü OCR için çözünürlük çok önemli (fatura kalemleri bulanıklaşıyordu)
            # Extract text using Turkish language pack
            # Ensure 'tur' language pack is installed in Tesseract
            text = pytesseract.image_to_string(page, lang='tur')
            full_text += text + "\n"
            page.close()
            
        return full_text
    except Exception as e:
        print(f"OCR failed: {e}")
        print("Note: Ensure Tesseract-OCR and Poppler are installed on your system.")
        return ""

def parse_pdf_invoice_ocr(file_path: str) -> dict:
    """
    Parses a scanned PDF invoice using OCR and regex.
    """
    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None
    }
    
    text = extract_text_via_ocr(file_path)
    if not text.strip():
        return data

    data = parse_invoice_text(text)
    data["_extraction_method"] = "ocr_pdf"
    data["_pdf_text_found"] = False
    return data

def extract_text_from_image_via_ocr(file_path: str) -> str:
    print(f"Applying OCR on image {file_path}...")
    try:
        from PIL import Image
        image = Image.open(file_path)
        
        # Sıkıştırma / Boyut Küçültme (Tesseract'ın çok yavaş çalışmasını önlemek için)
        max_size = 1600
        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            print("Image resized in memory for OCR.")
            
        text = pytesseract.image_to_string(image, lang='tur')
        image.close() # Explicitly free RAM to prevent Render 512MB OOM crash
        
        return text
    except Exception as e:
        print(f"Image OCR failed: {e}")
        return ""

def parse_image_invoice_ocr(file_path: str) -> dict:
    """
    Parses an image invoice using OCR and regex.
    """
    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None
    }
    
    text = extract_text_from_image_via_ocr(file_path)
    if not text.strip():
        return data

    data = parse_invoice_text(text)
    data["_extraction_method"] = "ocr_image"
    return data
