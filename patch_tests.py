import os

# patch_test_manual_edit_forwarding.py
with open("tests/test_manual_edit_forwarding.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement2 = '''
    with (
        patch("api.send_invoice_to_uyumsoft", return_value=success) as sender,
        patch("api.check_invoice_exists", return_value=False)
    ):'''

original_single2 = '''
    with patch("api.send_invoice_to_uyumsoft", return_value=success) as sender:'''

text = text.replace(original_single2, replacement2)
with open("tests/test_manual_edit_forwarding.py", "w", encoding="utf-8") as f:
    f.write(text)


# patch_test_usd_uyumsoft_pipeline.py
with open("tests/test_usd_uyumsoft_pipeline.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement3 = '''
    with (
        patch("api.send_invoice_to_uyumsoft", return_value=result) as sender,
        patch("database.save_invoice"),
        patch("api.check_invoice_exists", return_value=False)
    ):'''

original3 = '''
    with (
        patch("api.send_invoice_to_uyumsoft", return_value=result) as sender,
        patch("database.save_invoice"),
    ):'''

text = text.replace(original3, replacement3)
with open("tests/test_usd_uyumsoft_pipeline.py", "w", encoding="utf-8") as f:
    f.write(text)
