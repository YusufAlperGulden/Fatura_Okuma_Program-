import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

match = re.search(r'try_matches = ', text)
if match:
    print(text[match.end()-200:match.end()+1500])
else:
    print("Could not find try_matches = ")
