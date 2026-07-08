import pdfplumber
import re

MONEY_RE = r"(?:[₺$€£]\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})(?:\s*(?:TL|TRY|USD|EUR|GBP|DOLAR|EURO))?"


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
        "total_amount": None,
        "currency": "TRY"
    }

    usd_matches = len(re.findall(r'\$\s*\d|\d+(?:[.,]\d+)?\s*(?:USD|DOLAR)', text, re.IGNORECASE))
    eur_matches = len(re.findall(r'€\s*\d|\d+(?:[.,]\d+)?\s*(?:EUR|EURO)', text, re.IGNORECASE))
    gbp_matches = len(re.findall(r'£\s*\d|\d+(?:[.,]\d+)?\s*GBP', text, re.IGNORECASE))
    try_matches = len(re.findall(r'₺\s*\d|\d+(?:[.,]\d+)?\s*(?:TL|TRY)', text, re.IGNORECASE))

    if usd_matches > try_matches and usd_matches > eur_matches and usd_matches > gbp_matches:
        data["currency"] = "USD"
    elif eur_matches > try_matches and eur_matches > usd_matches and eur_matches > gbp_matches:
        data["currency"] = "EUR"
    elif gbp_matches > try_matches and gbp_matches > usd_matches and gbp_matches > eur_matches:
        data["currency"] = "GBP"
    else:
        data["currency"] = "TRY"

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

            text = text.strip()
            if not text:
                print("No selectable text found via pdfplumber. Falling back to OCR...")
                from extractors.ocr_extractor import parse_pdf_invoice_ocr
                return parse_pdf_invoice_ocr(file_path)

            data = parse_invoice_text(text)

        if not data['items']:
            print("PDF text was read, but line items were not matched. Skipping OCR for digital PDF.")

        print("Successfully read PDF file.")
        return data
        
    except Exception as e:
        print(f"Error parsing PDF file {file_path}: {e}")
        return {}
