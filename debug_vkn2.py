import sys
import os

# Add the project directory to path so we can import extractors
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from extractors.pdf_extractor import parse_pdf_invoice

file_path = r"C:\Users\tps\.gemini\antigravity\brain\54e8d961-b90a-49e2-8855-ecf3c45c0759\media__1783605515307.pdf"

print("--- FULL PIPELINE TEST ---")
data = parse_pdf_invoice(file_path)
print("VKN:", data.get("customer_tax_id"))
print("Name:", data.get("customer_name"))
