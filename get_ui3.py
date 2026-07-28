import re

with open('ui/app.js', 'r', encoding='utf-8') as f:
    text = f.read()

for i, line in enumerate(text.splitlines()):
    if 'const sym =' in line or 'let sym =' in line:
        print(f"Line {i}: {line.strip()}")
        # print 5 lines before and after
        start = max(0, i-5)
        end = min(len(text.splitlines()), i+5)
        print("\n".join(text.splitlines()[start:end]))
