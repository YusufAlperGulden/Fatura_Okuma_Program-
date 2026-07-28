import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'def extract_invoice_data[^:]*:.*?try_matches = _currency_amount_match_count[^)]*\)', text, re.DOTALL)
if match:
    # Print the context around try_matches
    print(text[match.end()-200:match.end()+1500])
else:
    print("Could not find try_matches")
