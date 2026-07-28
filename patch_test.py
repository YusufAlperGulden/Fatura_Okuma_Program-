import os

with open("tests/test_manual_customer_edits.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace("result = asyncio.run(send_uyumsoft_api(request))", "result = asyncio.run(send_uyumsoft_api(request))\n        print('RESULT WAS:', result.body if hasattr(result, 'body') else result)")

with open("tests/test_manual_customer_edits.py", "w", encoding="utf-8") as f:
    f.write(text)
