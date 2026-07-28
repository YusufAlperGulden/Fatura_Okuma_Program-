import os

with open('tests/test_ai_usd_currency.py', 'a', encoding='utf-8') as f:
    f.write('''
def test_normalize_ai_usd_with_explicit_try_settlement():
    from extractors.ai_extractor import _normalize_ai_usd_currency
    
    # Scenario: Gemini mistakenly flags the document as USD due to a footnote,
    # but the document contains a TRY settlement sentence.
    data = {
        "_raw_text": "İŞ BU FATURA BEDELİ 2.842,00 TL OLUP, BEDELİ TL OLARAK TAHSİL EDİLECEKTİR. VADESİ:Peşin ... ilgili mevzuat doğrultusunda USD olarak veya USD ye endeksli ...",
        "has_usd_mention": True,
        "currency": "USD",
        "document_currency": "USD",
        "settlement_currency": "USD",
        "accounting_currency": "USD",
        "total_amount": "2842.00"
    }
    
    result = _normalize_ai_usd_currency(data)
    
    assert result["has_usd_mention"] is False
    assert result["currency"] == "TRY"
    assert result["document_currency"] == "TRY"
    assert result["settlement_currency"] == "TRY"
    assert result["accounting_currency"] == "TRY"
''')
    print("Successfully added regression test to test_ai_usd_currency.py")
