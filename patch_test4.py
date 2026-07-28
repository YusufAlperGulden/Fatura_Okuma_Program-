import re

with open('tests/test_ai_usd_currency.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('assert "BEDELI USD OLARAK TAHSIL" in prompt', 'assert "BEDELİ USD OLARAK TAHSİL" in prompt')

with open('tests/test_ai_usd_currency.py', 'w', encoding='utf-8') as f:
    f.write(text)
    print("Patched test_ai_usd_currency")
