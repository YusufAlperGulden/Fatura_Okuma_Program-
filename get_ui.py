import re

with open('ui/app.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Let's search for how the Genel Toplam card is rendered.
match = re.search(r'function renderInvoice.*?Genel Toplam', text, re.DOTALL)
if match:
    print(text[match.end()-200:match.end()+1000])
else:
    # let's just grep for '$' or 'USD' or currency formatting
    pass
