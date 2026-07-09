import sys
import os

# Add the project directory to path so we can import extractors
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from extractors.pdf_extractor import parse_invoice_text
import pdfplumber

file_path = r"C:\Users\tps\.gemini\antigravity\brain\54e8d961-b90a-49e2-8855-ecf3c45c0759\media__1783605515307.pdf"

plain_text = ""
layout_text = ""
with pdfplumber.open(file_path) as pdf:
    for page in pdf.pages:
        plain_extracted = page.extract_text()
        layout_extracted = page.extract_text(layout=True)
        if plain_extracted: plain_text += plain_extracted + "\n"
        if layout_extracted: layout_text += layout_extracted + "\n"

print("--- PLAIN TEXT PARSED ---")
parsed_plain = parse_invoice_text(plain_text)
print("VKN:", parsed_plain.get("customer_tax_id"))
print("Name:", parsed_plain.get("customer_name"))

print("\n--- LAYOUT TEXT PARSED ---")
parsed_layout = parse_invoice_text(layout_text)
print("VKN:", parsed_layout.get("customer_tax_id"))
print("Name:", parsed_layout.get("customer_name"))
