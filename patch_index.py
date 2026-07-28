import re

with open('ui/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Remove the commented out ai-history-search
html = re.sub(r'<!--\s*<script src="ai-history-search.js\?v=1"></script>\s*-->\s*', '', html)

# Add fx-card after res-notes
notes_pattern = r'(<div id="res-notes"[^>]*>-</div>\s*</div>)'
fx_card = '''
                    <div id="fx-card" class="card wide-card hidden" style="grid-column: 1 / -1; background: color-mix(in srgb, var(--accent-color) 5%, transparent); border-color: color-mix(in srgb, var(--accent-color) 20%, transparent);">
                        <span class="card-label" style="color: var(--accent-color);">TL ARA TOPLAM / KDV / YEKÜN</span>
                        <div id="res-fx-info" style="font-size: 1.1rem; font-weight: 600; color: var(--text-primary); line-height: 1.5; display: flex; gap: 2rem;"></div>
                    </div>'''
if 'id="fx-card"' not in html:
    html = re.sub(notes_pattern, r'\\1' + fx_card, html)

# Apply textarea address change from ea7ed55
address_pattern = r'(<span class="card-label">FATURA ADRESİ</span>\s*)<input type="text" id="res-customer-address"[^>]*>'
textarea = r'\\1<textarea id="res-customer-address" class="edit-input-top" placeholder="Tam Açık Adres" style="margin-top: 10px; width: 100%; min-height: 60px; resize: vertical; padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 6px; background: var(--input-bg); color: var(--text-primary); font-family: inherit; font-size: 0.95rem; line-height: 1.5;"></textarea>'
html = re.sub(address_pattern, textarea, html)

# Add version v83 to scripts/css to clear cache
html = re.sub(r'style\.css\?v=[0-9]+', 'style.css?v=83', html)
html = re.sub(r'app\.js\?v=[0-9]+', 'app.js?v=83', html)
html = html.replace('<title>Fatura Veri Otomasyonu v77</title>', '<title>Fatura Veri Otomasyonu v83</title>')

with open('ui/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
