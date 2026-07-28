import os

with open("database.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''
def check_invoice_exists(invoice_no: str, customer_tax_id: str) -> bool:
    if not invoice_no or not customer_tax_id:
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM invoices WHERE invoice_no = ? AND customer_tax_id = ? AND status != 'HATALI'", 
            (invoice_no, customer_tax_id)
        )
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception:
        return False
'''

import re
text = re.sub(r'\ndef check_invoice_exists.*?return exists\n', replacement, text, flags=re.DOTALL)

with open("database.py", "w", encoding="utf-8") as f:
    f.write(text)
