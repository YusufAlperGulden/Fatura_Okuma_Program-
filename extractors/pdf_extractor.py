import pdfplumber
import re

def parse_pdf_invoice(file_path: str) -> dict:
    """
    Parses a digital PDF invoice using pdfplumber and regex.
    """
    print(f"Parsing PDF invoice: {file_path}")
    
    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None
    }
    
    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            
            # 1. Date (DD.MM.YYYY format)
            date_match = re.search(r'\d{1,2}\.\d{2}\.\d{4}', text)
            if date_match:
                data['date'] = date_match.group(0)
                
            # 2. Customer Tax ID / TC
            tc_match = re.search(r'TC\s+(\d{11})', text)
            if tc_match:
                data['customer_tax_id'] = tc_match.group(1)
                
            # 3. Items line
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
                    
            # 4. Ara Toplam (Subtotal)
            subtotal_match = re.search(r'Ara Toplam\s+₺?(\d+,\d{2})', text)
            if subtotal_match:
                data['subtotal'] = subtotal_match.group(1)
                
            # 5. KDV
            tax_match = re.search(r'KDV.*?\s+₺?(\d+,\d{2})', text)
            if tax_match:
                data['tax_amount'] = tax_match.group(1)
                
            # 6. Total Amount
            total_match = re.search(r'Döviz Toplam\s*:\s*₺?(\d+,\d{2})', text)
            if total_match:
                data['total_amount'] = total_match.group(1)

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
