import re

with open("ui/app.js", "r", encoding="utf-8") as f:
    text = f.read()

# Remove username and password from the send-uyumsoft payload in single invoice processing
replacement1 = '''            const response = await fetch('/send-uyumsoft', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    invoice_data: currentInvoiceData,
                    action: 'draft'
                })
            });'''

text = re.sub(r'const response = await fetch\(\'/send-uyumsoft\', \{\s*method: \'POST\',\s*headers: \{\s*\'Content-Type\': \'application/json\'\s*\},\s*body: JSON\.stringify\(\{ \s*invoice_data: currentInvoiceData,.*?\}\)\s*\}\);', replacement1, text, flags=re.DOTALL)

# Same for batch processing
replacement2 = '''                const response = await fetch('/send-uyumsoft', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        invoice_data: item.invoice_data,
                        action: 'draft'
                    })
                });'''

text = re.sub(r'const response = await fetch\(\'/send-uyumsoft\', \{\s*method: \'POST\',\s*headers: \{ \'Content-Type\': \'application/json\' \},\s*body: JSON\.stringify\(\{ \s*invoice_data: item\.invoice_data,.*?\}\)\s*\}\);', replacement2, text, flags=re.DOTALL)

with open("ui/app.js", "w", encoding="utf-8") as f:
    f.write(text)
