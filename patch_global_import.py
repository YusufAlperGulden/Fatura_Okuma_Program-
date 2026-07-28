import os
import re

with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

# Add to the top of the file
if "from database import check_invoice_exists" not in text[:500]:
    text = text.replace("from database import init_db", "from database import init_db, check_invoice_exists")

# Remove local imports
text = text.replace("from database import check_invoice_exists\n", "")
text = text.replace("from database import save_invoice, check_invoice_exists", "from database import save_invoice")

with open("api.py", "w", encoding="utf-8") as f:
    f.write(text)
