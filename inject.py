import sys

with open('ui/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

script = '''<script>
window.onerror = function(message, source, lineno, colno, error) {
    fetch('http://localhost:8000/log_error', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: message, source: source, lineno: lineno, colno: colno})
    });
};
</script>'''

if '<script>window.onerror' not in html:
    html = html.replace('<head>', '<head>\\n' + script)
    with open('ui/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
