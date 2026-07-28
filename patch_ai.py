import re

with open('extractors/ai_extractor.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update the prompt string
old_instructions_start = 'KRITIK USD KURALI:'
old_instructions_match = re.search(r'USD_EXTRACTION_INSTRUCTIONS = """(.*?)"""', text, re.DOTALL)
if old_instructions_match:
    old_prompt = old_instructions_match.group(1)
    new_prompt = '''
  KRITIK PARA BİRİMİ VE USD KURALI (KESİN ÖNCELİK):
  - DİKKAT: Belgede "BEDELİ TL OLARAK TAHSİL EDİLECEKTİR", "TL OLUP" gibi bir cümle varsa 
    (başka yerlerde, alt notlarda veya dipnotlarda USD yazsa bile), para birimi kesinlikle 'TRY' olmalıdır.
    Bu durumda has_usd_mention=false, currency="TRY", document_currency="TRY" ve settlement_currency="TRY" döndür.
  - Eğer yukarıdaki "TL OLARAK TAHSİL" kuralı YOKSA ve belgenin HERHANGI BIR YERINDE bağımsız para birimi kodu olarak "USD" geçiyorsa (notlarda, dipnotta, satır açıklamasında veya toplamlar bölümünde):
    bu belgeyi USD tahsilatlı fatura kabul et. 
  - Özellikle "İŞ BU FATURA BEDELİ ... USD OLUP, BEDELİ USD OLARAK TAHSİL EDİLECEKTİR", "BEDELİ USD OLARAK TAHSİL EDİLECEKTİR" cümlesi kesin USD kanıtıdır.
  - Bu durumda has_usd_mention=true, currency="USD", document_currency="USD" ve settlement_currency="USD" döndür.
  - Belgede kalemler ve toplamlar TL olarak yazılmış, ancak tahsilat USD ise accounting_currency="TRY" döndür. TL değerlerin orijinallerini local_subtotal, local_discount_amount, local_tax_amount, local_total ve kalemlerde local_unit_price/local_total_price alanlarında koru.
  - Faturada açıkça yazan döviz kurunu exchange_rate alanına koy. Kur yazıyorsa TL tutarları bu kura bölerek USD subtotal, discount_amount, tax_amount, total_amount ve kalem fiyatlarını hesapla. Yuvarlamayı iki ondalıkla yap.
  - Cümlede açıkça yazan USD fatura bedelini foreign_total alanına koy ve total_amount ile aynı USD değeri kullan.
  - Kur belgede yoksa ASLA kur tahmin etme. exchange_rate=null döndür.
'''
    text = text.replace(old_prompt, new_prompt)

# 2. Add import for TRY_SETTLEMENT_RE
import_statement = "from utils.invoice_values import parse_localized_decimal, quantize_money\nfrom extractors.pdf_extractor import TRY_SETTLEMENT_RE\n"
text = text.replace("from utils.invoice_values import parse_localized_decimal, quantize_money\n", import_statement)

# 3. Modify _normalize_ai_usd_currency to check TRY_SETTLEMENT_RE
replacement = '''def _normalize_ai_usd_currency(data: dict) -> dict:
    """Make Gemini's USD evidence and monetary fields internally consistent."""

    if not isinstance(data, dict):
        return data
        
    text = str(data.get("_raw_text") or "")
    if TRY_SETTLEMENT_RE.search(text):
        data["has_usd_mention"] = False
        data["currency"] = "TRY"
        data["document_currency"] = "TRY"
        data["settlement_currency"] = "TRY"
        if data.get("accounting_currency") == "USD":
            data["accounting_currency"] = "TRY"
        return data

    has_usd_mention = _is_truthy_flag(data.get("has_usd_mention")) or _contains_usd_token(
'''

target = '''def _normalize_ai_usd_currency(data: dict) -> dict:
    """Make Gemini's USD evidence and monetary fields internally consistent."""

    if not isinstance(data, dict):
        return data

    has_usd_mention = _is_truthy_flag(data.get("has_usd_mention")) or _contains_usd_token('''

if target in text:
    text = text.replace(target, replacement)
    with open('extractors/ai_extractor.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Successfully patched ai_extractor.py")
else:
    print("Could not find target in ai_extractor")
