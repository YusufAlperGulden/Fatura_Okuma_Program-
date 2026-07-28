import re

with open('ui/app.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Grep for 'genel-toplam' or 'total'
for line in text.splitlines():
    if 'total_amount' in line or 'genel' in line.lower() or 'Genel Toplam' in line:
        print(line.strip())

