import re

with open('extractors/ai_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'def _normalize_ai_usd_currency.*?return data', text, re.DOTALL)
if match:
    print(match.group(0))
else:
    print("Not found")
