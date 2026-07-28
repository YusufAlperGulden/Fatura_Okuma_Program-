import sys
import json
from extractors.pdf_extractor import parse_pdf_invoice
from extractors.ocr_extractor import parse_pdf_invoice_ocr
from extractors.ai_extractor import extract_invoice_with_ai

pdf_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1785232493621.pdf"

print("--- Testing PDF Extractor ---")
try:
    data_pdf = parse_pdf_invoice(pdf_path)
    print("PDF Extractor Currency:", data_pdf.get("currency"), data_pdf.get("document_currency"), data_pdf.get("settlement_currency"), data_pdf.get("accounting_currency"))
except Exception as e:
    print("PDF Extractor Error:", e)

print("\n--- Testing OCR Extractor ---")
try:
    data_ocr = parse_pdf_invoice_ocr(pdf_path)
    print("OCR Extractor Currency:", data_ocr.get("currency"), data_ocr.get("document_currency"), data_ocr.get("settlement_currency"), data_ocr.get("accounting_currency"))
except Exception as e:
    print("OCR Extractor Error:", e)

