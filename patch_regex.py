import re

with open('extractors/pdf_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

usd_re_str = r'''USD_SETTLEMENT_RE = re.compile(
    r"\\bBEDEL[İI]\s+USD\s+OLARAK\s+TAHS[İI]L"
    r"|\\bUSD\s+OLARAK\s+TAHS[İI]L"
    r"|\\bFATURA\s+BEDEL[İI]\\b[^\r\n]{0,80}\\bUSD\s+OLUP\\b",
    re.IGNORECASE,
)'''

try_re_str = r'''TRY_SETTLEMENT_RE = re.compile(
    r"\bBEDEL[İI]\s+(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\b(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\bFATURA\s+BEDEL[İI]\b[^\r\n]{0,80}\b(?:TL|TRY)\s+OLUP\b",
    re.IGNORECASE,
)'''

# We need to find USD_SETTLEMENT_RE and insert TRY_SETTLEMENT_RE after it
match = re.search(r'USD_SETTLEMENT_RE = re\.compile\([^)]*\)', text, re.MULTILINE)
if match:
    new_text = text[:match.end()] + "\n" + try_re_str + text[match.end():]
    with open('extractors/pdf_extractor.py', 'w', encoding='utf-8') as f:
        f.write(new_text)
    print("Successfully added TRY_SETTLEMENT_RE")
else:
    print("Could not find USD_SETTLEMENT_RE")
