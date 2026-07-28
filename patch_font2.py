import re

with open('ui/style.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Replace 'inherit' with 'system-ui, -apple-system, sans-serif'
css = re.sub(r'font-family:\s*inherit;', 'font-family: system-ui, -apple-system, sans-serif;', css)

with open('ui/style.css', 'w', encoding='utf-8') as f:
    f.write(css)

with open('ui/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = re.sub(r'style\.css\?v=[0-9]+', 'style.css?v=84', html)
html = html.replace('<title>Fatura Veri Otomasyonu v83</title>', '<title>Fatura Veri Otomasyonu v84</title>')

with open('ui/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
