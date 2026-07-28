import pdfplumber
import re

TRY_SETTLEMENT_RE = re.compile(
    r"\bBEDEL[İI]\s+(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\b(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\bFATURA\s+BEDEL[İI]\b[^\r\n]{0,80}\b(?:TL|TRY)\s+OLUP\b",
    re.IGNORECASE,
)

pdf_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1785232493621.pdf"
with pdfplumber.open(pdf_path) as pdf:
    text = ""
    for page in pdf.pages:
        text += page.extract_text() + "\n"

    print("Does TRY_SETTLEMENT_RE match?", bool(TRY_SETTLEMENT_RE.search(text)))
    print("Does 'FATURA BEDELİ' exist in text?", 'FATURA BEDELİ' in text)
    print("Does '403,35' exist in text?", '403,35' in text)
    
    # print context around 403,35
    idx = text.find('403,35')
    if idx != -1:
        snippet = text[max(0, idx-100):min(len(text), idx+100)]
        print(snippet.encode('utf-8'))
