import re

with open('ui/style.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Replace Inter font with default sans-serif or inherit
css = re.sub(r"font-family:\s*['\"]Inter['\"],\s*sans-serif;", "font-family: inherit;", css)

with open('ui/style.css', 'w', encoding='utf-8') as f:
    f.write(css)
