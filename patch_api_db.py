import os

with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''            invoice_data, 
            is_valid=True, 
            uyumsoft_document_id=document_id,
            uyumsoft_environment=normalize_uyumsoft_environment(),
            uyumsoft_status="Draft"
        )'''

original = '''            invoice_data, 
            is_valid=True, 
            uyumsoft_document_id=document_id,
            uyumsoft_environment=request.environment,
            uyumsoft_status="Draft"
        )'''

if original in text:
    text = text.replace(original, replacement)
else:
    print("Could not find the original block in api.py")

with open("api.py", "w", encoding="utf-8") as f:
    f.write(text)
