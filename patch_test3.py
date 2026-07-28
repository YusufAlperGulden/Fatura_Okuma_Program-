import re

with open('tests/test_pdf_usd_currency_detection.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''
def test_explicit_try_settlement_overrides_usd_footnote():
    # User's exact Suatcan OCR text pattern containing a USD footnote but a TRY settlement string
    ocr_text = """
    Ara Toplam ₺2.368,33
    KDV 18(%20) ₺473,67

    İŞ BU FATURA BEDELİ 2.842,00 TL OLUP, BEDELİ TL OLARAK TAHSİL EDİLECEKTİR. VADESİ:Peşin

    * Fatura üzerindeki iş bu döviz kuru ve TL tutarı sadece muhasebe kaydı için
    geçerli olup cari hesap ödemesi için değildir. Siparişe ilişkin ödeme
    yükümlülüğü, ilgili mevzuat doğrultusunda USD olarak veya USD ye endeksli
    şekilde ödeme günü hesaplanacak Türk Lirası cinsinden ifa edilebilir. Mevzuat
    gereğince ödemenin Türk Lirası cinsinden yapılması gerekiyor ise,
    """
    from extractors.pdf_extractor import parse_invoice_text
    
    result = parse_invoice_text(ocr_text)
    
    assert result["currency"] == "TRY"
    assert result["document_currency"] == "TRY"
    assert result["settlement_currency"] == "TRY"
    assert result["accounting_currency"] == "TRY"
'''

match = re.search(r'def test_explicit_try_settlement_overrides_usd_footnote\(\):.*', text, re.DOTALL)
if match:
    text = text[:match.start()] + replacement
    with open('tests/test_pdf_usd_currency_detection.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Patched test_pdf_usd_currency_detection")
