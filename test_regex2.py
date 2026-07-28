import re

text1 = "İŞ BU FATURA BEDELİ 403,35 TL OLUP, BEDELİ TL OLARAK TAHSİL EDİLECEKTİR. VADESİ:Peşin"
text2 = "İŞ BU FATURA BEDELI 403,35 TL OLUP, BEDELI TL OLARAK TAHSİL EDİLECEKTİR. VADESİ:Peşin"
text3 = "IS BU FATURA BEDELI 403,35 TL OLUP, BEDELI TL OLARAK TAHSIL EDILECEKTIR. VADESI:Pesin"

TRY_SETTLEMENT_RE = re.compile(
    r"\bBEDEL[İI]\s+(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\b(?:TL|TRY|TÜRK\s+LİRASI)\s+OLARAK\s+TAHS[İI]L"
    r"|\bFATURA\s+BEDEL[İI]\b[^\r\n]{0,80}\b(?:TL|TRY)\s+OLUP\b",
    re.IGNORECASE,
)

print("text1 matches:", bool(TRY_SETTLEMENT_RE.search(text1)))
print("text2 matches:", bool(TRY_SETTLEMENT_RE.search(text2)))
print("text3 matches:", bool(TRY_SETTLEMENT_RE.search(text3)))
