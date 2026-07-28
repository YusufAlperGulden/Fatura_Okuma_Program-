import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'def _apply_mode_b_usd_conversion.*?def parse_pdf_invoice', text, re.DOTALL)
if match:
    print(match.group(0)[:1000])
else:
    print("Could not find _apply_mode_b_usd_conversion")
