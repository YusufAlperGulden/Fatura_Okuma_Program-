import pytesseract
from pdf2image import convert_from_path
import re
import os

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
            pages = convert_from_path(file_path, poppler_path=POPPLER_PATH)
        else:
            pages = convert_from_path(file_path)
            
        full_text = ""
        for page in pages:
            # Extract text using Turkish language pack
            # Ensure 'tur' language pack is installed in Tesseract
            text = pytesseract.image_to_string(page, lang='tur')
            full_text += text + "\n"
            
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
        
    # Reuse the same regex logic from pdf_extractor
    date_match = re.search(r'\d{1,2}\.\d{2}\.\d{4}', text)
    if date_match:
        data['date'] = date_match.group(0)
        
    tc_match = re.search(r'TC\s+(\d{11})', text)
    if tc_match:
        data['customer_tax_id'] = tc_match.group(1)
        
    item_pattern = re.compile(r'(?m)^(?!\d{1,2}\.\d{2}\.)(\w[\w.-]*)\s+(.*?)\s+(\d+,\d{2})\s+₺(\d+,\d{2})\s+₺(\d+,\d{2})')
    for match in item_pattern.finditer(text):
        item = {
            "code": match.group(1),
            "description": match.group(2).strip(),
            "quantity": match.group(3),
            "unit_price": match.group(4),
            "total_price": match.group(5)
        }
        if item not in data['items']:
            data['items'].append(item)
            
    subtotal_match = re.search(r'Ara Toplam\s+₺?(\d+,\d{2})', text)
    if subtotal_match:
        data['subtotal'] = subtotal_match.group(1)
        
    tax_match = re.search(r'KDV.*?\s+₺?(\d+,\d{2})', text)
    if tax_match:
        data['tax_amount'] = tax_match.group(1)
        
    total_match = re.search(r'Döviz Toplam\s*:\s*₺?(\d+,\d{2})', text)
    if total_match:
        data['total_amount'] = total_match.group(1)
        
    return data
