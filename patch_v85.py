import re

with open('ui/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Update title
html = re.sub(r'<title>Fatura Veri Otomasyonu v84</title>', '<title>Fatura Veri Otomasyonu v85</title>', html)

# Bump versions to 85 to clear cache
html = re.sub(r'style\.css\?v=[0-9]+', 'style.css?v=85', html)
html = re.sub(r'helpers\.js\?v=[0-9]+', 'helpers.js?v=85', html)
html = re.sub(r'app\.js\?v=[0-9]+', 'app.js?v=85', html)

with open('ui/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
