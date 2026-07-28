import os

with open("tests/test_manual_customer_edits.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''
        with (
            patch(
                "api.enrich_invoice_customer_from_uyumsoft",
                side_effect=AssertionError(
                    "Final user data must not be enriched again during send."
                ),
            ) as enrich,
            patch("api.send_invoice_to_uyumsoft", return_value=success) as send,
            patch("api.check_invoice_exists", return_value=False)
        ):'''

original = '''
        with (
            patch(
                "api.enrich_invoice_customer_from_uyumsoft",
                side_effect=AssertionError(
                    "Final user data must not be enriched again during send."
                ),
            ) as enrich,
            patch("api.send_invoice_to_uyumsoft", return_value=success) as send,
        ):'''

text = text.replace(original, replacement)
text = text.replace("print('RESULT WAS:', result.body if hasattr(result, 'body') else result)", "")

with open("tests/test_manual_customer_edits.py", "w", encoding="utf-8") as f:
    f.write(text)
