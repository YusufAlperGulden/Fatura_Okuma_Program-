import re

with open('ui/app.js', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'function renderInvoice\([^)]*\)\s*{.*?(const tbody = document\.querySelector\([^)]*\)[^}]*)}', text, re.DOTALL)
if match:
    print(match.group(0)[:1500])
else:
    print("Not found")
