import os

with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

# Make sure check_invoice_exists is imported
if "from database import" in text:
    if "check_invoice_exists" not in text:
        text = text.replace("from database import (", "from database import (\n    check_invoice_exists,")
        text = text.replace("from database import save_invoice", "from database import save_invoice, check_invoice_exists")

idemp_check = '''
    invoice_no = invoice_data.get("invoice_no")
    customer_tax_id = invoice_data.get("customer_tax_id")
    if invoice_no and customer_tax_id and check_invoice_exists(invoice_no, customer_tax_id):
        return {
            "success": False,
            "message": "Bu fatura daha önce sisteme aktarılmış.",
            "details": f"Fatura No: {invoice_no} mükerrer gönderim engellendi."
        }

    result = send_invoice_to_uyumsoft(
'''

original_call = '''    result = send_invoice_to_uyumsoft('''

if idemp_check not in text and original_call in text:
    text = text.replace(original_call, idemp_check)
else:
    print("Could not find the send_invoice_to_uyumsoft call to insert idempotency check")

with open("api.py", "w", encoding="utf-8") as f:
    f.write(text)
