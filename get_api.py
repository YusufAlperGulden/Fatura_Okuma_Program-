import re

with open('api.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'def _process_upload.*?return', text, re.DOTALL)
if match:
    print(match.group(0)[:1500])
else:
    print("Not found")
