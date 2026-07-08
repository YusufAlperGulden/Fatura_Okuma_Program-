import os
import argparse
import json
from extractors.excel_extractor import parse_excel_invoice
from extractors.pdf_extractor import parse_pdf_invoice
from extractors.xml_extractor import parse_xml_invoice

from validators.invoice_validator import validate_invoice
from integrators.uyumsoft_excel import export_to_uyumsoft_excel

def process_file(file_path: str):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ['.xlsx', '.xls', '.csv']:
        data = parse_excel_invoice(file_path)
    elif ext == '.pdf':
        data = parse_pdf_invoice(file_path)
    elif ext == '.xml':
        data = parse_xml_invoice(file_path)
    else:
        print(f"Unsupported file format: {ext}")
        return
        
    print("\n--- Extracted Data ---")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("----------------------\n")
    
    is_valid, errors = validate_invoice(data)
    
    if is_valid:
        print("Validation PASSED. Data is mathematically consistent.")
        export_to_uyumsoft_excel([data], "Uyumsoft_Aktarim_Taslagi.xlsx")
    else:
        print("Validation FAILED. Errors found:")
        for error in errors:
            print(f" - {error}")
        
        # Log failed invoices (placeholder)
        with open("hatali_faturalar.log", "a", encoding="utf-8") as f:
            f.write(f"Failed Invoice {file_path}: {errors}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process an invoice file (PDF or Excel).")
    parser.add_argument("file_path", help="Path to the invoice file to process")
    args = parser.parse_args()
    
    process_file(args.file_path)
