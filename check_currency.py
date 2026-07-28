import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'def extract_invoice_data[^:]*:.*?try_matches = _currency_amount_match_count\([^)]*\).*?if _has_usd_marker\(text\):', text, re.DOTALL)
if match:
    print(match.group(0)[:1000])
else:
    print("Could not find the start of currency assignment")
