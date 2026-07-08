import pdfplumber
import re

MONEY_RE = r"(?:₺\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})(?:\s*(?:TL|TRY))?"


def _first_match(patterns, text, flags=0):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def parse_invoice_text(text: str) -> dict:
    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None
    }

    data["invoice_no"] = _first_match([
        r"(?:Fatura|Belge|Invoice)\s*(?:No|Numarası|Numarasi|Number)?\s*[:#-]\s*([A-Z0-9-]+)",
        r"\b([A-Z]{3}\d{13})\b",
    ], text, re.IGNORECASE)

    data["date"] = _first_match([r"\b(\d{1,2}\.\d{2}\.\d{4})\b"], text)

    data["customer_tax_id"] = _first_match([
        r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi\s*No)\s*[:#-]?\s*(\d{10,11})\b",
        r"\b(\d{10,11})\b",
    ], text, re.IGNORECASE)

    item_pattern = re.compile(
        rf"(?m)^(?!\d{{1,2}}\.\d{{2}}\.)(\w[\w.-]*)\s+(.+?)\s+"
        rf"(\d+(?:[.,]\d+)?)\s+{MONEY_RE}\s+{MONEY_RE}",
        re.IGNORECASE,
    )
    for match in item_pattern.finditer(text):
        item = {
            "code": match.group(1),
            "description": match.group(2).strip(),
            "quantity": match.group(3).replace(".", ","),
            "unit_price": match.group(4),
            "total_price": match.group(5)
        }
        if item not in data["items"]:
            data["items"].append(item)

    data["subtotal"] = _first_match([rf"Ara\s*Toplam\s+{MONEY_RE}"], text, re.IGNORECASE)
    data["tax_amount"] = _first_match([rf"\bKDV\b.*?{MONEY_RE}"], text, re.IGNORECASE)
    data["total_amount"] = _first_match([
        rf"Döviz\s*Toplam\s*:\s*{MONEY_RE}",
        rf"FATURA\s+BEDELİ\s+{MONEY_RE}",
        rf"Genel\s*Toplam\s+{MONEY_RE}",
        rf"Ödenecek\s*Tutar\s+{MONEY_RE}",
    ], text, re.IGNORECASE)

    return data


def parse_pdf_invoice(file_path: str) -> dict:
    """
    Parses a digital PDF invoice using pdfplumber and regex.
    """
    print(f"Parsing PDF invoice: {file_path}")
    
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"

            data = parse_invoice_text(text)

        # Fallback to OCR if no items were found (indicates a scanned PDF)
        if not data['items']:
            print("No text found via pdfplumber. Falling back to OCR...")
            from extractors.ocr_extractor import parse_pdf_invoice_ocr
            return parse_pdf_invoice_ocr(file_path)

        print("Successfully read PDF file.")
        return data
        
    except Exception as e:
        print(f"Error parsing PDF file {file_path}: {e}")
        return {}
