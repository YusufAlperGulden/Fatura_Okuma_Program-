import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''
    has_try_settlement = bool(TRY_SETTLEMENT_RE.search(text))
    has_usd_settlement = bool(USD_SETTLEMENT_RE.search(text))

    if has_try_settlement:
        data["currency"] = "TRY"
        data["document_currency"] = "TRY"
        data["settlement_currency"] = "TRY"
        data["accounting_currency"] = "TRY"
    elif has_usd_settlement:
        data["currency"] = "USD"
        data["document_currency"] = "USD"
        data["settlement_currency"] = "USD"
        data["accounting_currency"] = "TRY" if try_matches > usd_matches else "USD"
    elif _has_usd_marker(text):
        data["currency"] = "USD"
        data["document_currency"] = "USD"
        data["settlement_currency"] = "USD"
        data["accounting_currency"] = "TRY" if try_matches > usd_matches else "USD"
'''

target = '''
    # Product requirement: an explicit USD marker anywhere on the invoice is
    # authoritative, even when the visible accounting rows are mostly in TRY.
    if _has_usd_marker(text):
        data["currency"] = "USD"
        data["document_currency"] = "USD"
        data["settlement_currency"] = "USD"
        data["accounting_currency"] = "TRY" if try_matches > usd_matches else "USD"
'''

if target.strip() in text:
    new_text = text.replace(target, replacement)
    with open('extractors/pdf_extractor.py', 'w', encoding='utf-8') as f:
        f.write(new_text)
    print("Successfully patched currency logic.")
else:
    print("Could not find target block.")
