import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'data\["notes"\] = .*?', text)
if match:
    print(text[match.start()-200:match.start()+500])
else:
    print("Not found")
