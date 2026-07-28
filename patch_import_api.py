import os

with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''
    from database import check_invoice_exists
    invoice_no = invoice_data.get("invoice_no")
    customer_tax_id = invoice_data.get("customer_tax_id")
    if invoice_no and customer_tax_id and check_invoice_exists(invoice_no, customer_tax_id):'''

original = '''
    invoice_no = invoice_data.get("invoice_no")
    customer_tax_id = invoice_data.get("customer_tax_id")
    if invoice_no and customer_tax_id and check_invoice_exists(invoice_no, customer_tax_id):'''

if original in text:
    text = text.replace(original, replacement)
else:
    print("Could not find the original block in api.py")

with open("api.py", "w", encoding="utf-8") as f:
    f.write(text)
