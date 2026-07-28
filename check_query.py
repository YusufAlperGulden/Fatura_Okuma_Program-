import re
with open('ui/app.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'querySelector(' in line or 'querySelectorAll(' in line:
        print(f"Line {i+1}: {line.strip()}")
