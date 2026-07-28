import sys
import json
from extractors.pdf_extractor import parse_pdf_invoice

# The latest uploaded PDF should be media__1785232493621.pdf
pdf_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1785232493621.pdf"

try:
    data = parse_pdf_invoice(pdf_path)
    print("Extracted Currency:", data.get("currency"))
    print("Has USD mention:", data.get("has_usd_mention"))
    print("Raw text match:", "BEDELİ" in data.get("_raw_text", ""))
except Exception as e:
    print("Error:", e)
