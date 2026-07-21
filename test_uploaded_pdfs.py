import os
import sys

# Add the project directory to path so we can import integrators
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from extractors.pdf_extractor import parse_pdf_invoice
from integrators.uyumsoft_api import enrich_invoice_customer_from_uyumsoft

pdf_files = [
    r"C:\Users\tps\.gemini\antigravity\brain\54e8d961-b90a-49e2-8855-ecf3c45c0759\media__1783603983569.pdf",
    r"C:\Users\tps\.gemini\antigravity\brain\54e8d961-b90a-49e2-8855-ecf3c45c0759\media__1783603983462.pdf",
    r"C:\Users\tps\.gemini\antigravity\brain\54e8d961-b90a-49e2-8855-ecf3c45c0759\media__1783603983460.pdf",
    r"C:\Users\tps\.gemini\antigravity\brain\54e8d961-b90a-49e2-8855-ecf3c45c0759\media__1783603983459.pdf"
]

print("TESTING ChatGPT's FIX ON PROVIDED PDFS...\n")

for pdf in pdf_files:
    print(f"--- Processing: {os.path.basename(pdf)} ---")
    data = parse_pdf_invoice(pdf)
    vkn_extracted = data.get('customer_tax_id')
    name_extracted = data.get('customer_name')
    print(f"Original Extracted VKN: {vkn_extracted}")
    print(f"Original Extracted Name: {name_extracted}")
    
    enriched = enrich_invoice_customer_from_uyumsoft(data)
    final_name = enriched.get('customer_name')
    lookup_status = enriched.get('_uyumsoft_customer_lookup', 'N/A')
    
    print(f"Uyumsoft Lookup Status: {lookup_status}")
    print(f"Final Customer Name: {final_name}")
    
    # Also verify what _customer_display_name would return if we simulate what happens inside build_invoice_info_body
    from integrators.uyumsoft_api import _customer_display_name
    display_name = _customer_display_name(enriched, vkn_extracted)
    print(f"Display Name for Uyumsoft XML: {display_name}\n")
