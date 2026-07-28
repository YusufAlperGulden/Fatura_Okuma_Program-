import sys
import json
from extractors.pdf_extractor import parse_pdf_invoice

file_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1785227803776.pdf"
try:
    data = parse_pdf_invoice(file_path)
    print("EXTRACTED ITEMS:")
    for item in data.get('items', []):
        print(json.dumps(item, indent=2, ensure_ascii=False))
except Exception as e:
    print("Error:", e)
