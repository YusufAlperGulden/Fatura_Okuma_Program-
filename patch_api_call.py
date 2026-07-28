import os

with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''    result = send_invoice_to_uyumsoft(
        invoice_data,
        action="draft",
    )'''

original = '''    result = send_invoice_to_uyumsoft(
        invoice_data,
        action="draft",
        environment=request.environment,
        prod_username=request.username,
        prod_password=request.password,
    )'''

if original in text:
    text = text.replace(original, replacement)
else:
    print("Could not find the original block in api.py")

with open("api.py", "w", encoding="utf-8") as f:
    f.write(text)
