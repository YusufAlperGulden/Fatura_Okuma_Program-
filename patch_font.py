import re

with open('ui/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Remove Google fonts link
html = re.sub(r'<link href="https://fonts.googleapis.com/css2\?family=Inter[^>]*>\s*', '', html)

# Bump versions to 83 to clear cache
html = re.sub(r'style\.css\?v=[0-9]+', 'style.css?v=83', html)
html = re.sub(r'helpers\.js\?v=[0-9]+', 'helpers.js?v=83', html)
html = re.sub(r'app\.js\?v=[0-9]+', 'app.js?v=83', html)

# Update title
html = re.sub(r'<title>.*?</title>', '<title>Fatura Veri Otomasyonu v83</title>', html)

with open('ui/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
