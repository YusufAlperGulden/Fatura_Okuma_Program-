import sys
import json
from extractors.ai_extractor import extract_invoice_with_ai

pdf_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1785232493621.pdf"

print("\n--- Testing AI Extractor ---")
try:
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
    data_ai = extract_invoice_with_ai(file_bytes, "application/pdf")
    print("AI Extractor Currency:", data_ai.get("currency"), data_ai.get("document_currency"), data_ai.get("settlement_currency"), data_ai.get("accounting_currency"))
except Exception as e:
    print("AI Extractor Error:", e)

