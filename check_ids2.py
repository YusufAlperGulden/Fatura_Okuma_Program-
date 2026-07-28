import re
import sys

with open('ui/app.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Find all document.getElementById('...')
dom_ids = re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", text)

with open('ui/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

missing = []
for id in set(dom_ids):
    if f'id="{id}"' not in html and f"id='{id}'" not in html:
        missing.append(id)

print('Missing IDs:', missing)
