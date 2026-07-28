import re

text = "BU FATURA BEDELİ 403,35 TL OLUP, BEDELİ TL OLARAK TAHSİL EDİLECEKTİR. VADESİ:Peşin"

TRY_SETTLEMENT_RE = re.compile(
    r"\bBEDEL[İI]\s+(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\b(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\bFATURA\s+BEDEL[İI]\b[^\r\n]{0,80}\b(?:TL|TRY)\s+OLUP\b",
    re.IGNORECASE,
)

print(bool(TRY_SETTLEMENT_RE.search(text)))
