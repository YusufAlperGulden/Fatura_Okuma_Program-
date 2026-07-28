import re

with open('ui/app.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '.addEventListener(' in line and '?' not in line and 'document.' not in line and 'window.' not in line:
        print(f"Line {i+1}: {line.strip()}")
