import sys
import json
from extractors.pdf_extractor import parse_pdf_invoice

# I will test the exact hypothesis.
# But since the bug is ALREADY FIXED on main (it correctly outputs TRY), I will just confirm it.
pdf_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1785232493621.pdf"

data = parse_pdf_invoice(pdf_path)
print("With current fix, currency is:", data.get("currency"))
print("Does it extract notes?", "notes" in data and bool(data["notes"]))
