import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'def _extract_invoice_notes.*?return', text, re.DOTALL)
if match:
    print(match.group(0)[:1500])
else:
    print("Not found")
