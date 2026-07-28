import re
with open('extractors/ai_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'USD_EXTRACTION_INSTRUCTIONS = """(.*?)"""', text, re.DOTALL)
if match:
    print(match.group(1))
else:
    print("Not found")
