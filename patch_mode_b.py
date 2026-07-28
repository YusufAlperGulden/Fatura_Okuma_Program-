import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''
    text = str(data.get("_raw_text") or "")
    
    has_try_settlement = bool(TRY_SETTLEMENT_RE.search(text))
    if has_try_settlement:
        data["has_usd_mention"] = False
        return data

    has_usd_mention = _has_usd_marker(text)
'''

target = '''
    text = str(data.get("_raw_text") or "")
    has_usd_mention = _has_usd_marker(text)
'''

if target.strip() in text:
    new_text = text.replace(target.strip(), replacement.strip())
    with open('extractors/pdf_extractor.py', 'w', encoding='utf-8') as f:
        f.write(new_text)
    print("Successfully patched _apply_mode_b_usd_conversion.")
else:
    print("Could not find target block.")
