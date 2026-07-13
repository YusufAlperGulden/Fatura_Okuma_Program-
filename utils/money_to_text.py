from decimal import Decimal

_ones = ["", "Bir", "İki", "Üç", "Dört", "Beş", "Altı", "Yedi", "Sekiz", "Dokuz"]
_tens = ["", "On", "Yirmi", "Otuz", "Kırk", "Elli", "Altmış", "Yetmiş", "Seksen", "Doksan"]
_scales = ["", "Bin", "Milyon", "Milyar", "Trilyon"]

_currencies = {
    "TRY": ("Türk Lirası", "Kuruş"),
    "USD": ("Dolar", "Sent"),
    "EUR": ("Euro", "Sent"),
    "GBP": ("Sterlin", "Peni"),
}

def _chunk_to_text(chunk: int) -> str:
    """Convert a 3-digit number to Turkish text."""
    if chunk == 0:
        return ""
    
    words = []
    hundreds = chunk // 100
    remainder = chunk % 100
    tens = remainder // 10
    ones = remainder % 10

    if hundreds == 1:
        words.append("Yüz")
    elif hundreds > 1:
        words.append(f"{_ones[hundreds]} Yüz")
        
    if tens > 0:
        words.append(_tens[tens])
        
    if ones > 0:
        words.append(_ones[ones])
        
    return " ".join(words)

def _int_to_text(number: int) -> str:
    if number == 0:
        return "Sıfır"
        
    chunks = []
    while number > 0:
        chunks.append(number % 1000)
        number //= 1000
        
    words = []
    for i, chunk in enumerate(chunks):
        if chunk == 0:
            continue
            
        chunk_text = _chunk_to_text(chunk)
        
        # Exception for "Bir Bin" -> "Bin"
        if i == 1 and chunk == 1:
            words.insert(0, "Bin")
        else:
            scale = _scales[i]
            if scale:
                words.insert(0, f"{chunk_text} {scale}".strip())
            else:
                words.insert(0, chunk_text)
                
    return " ".join(words)

def amount_to_turkish_text(amount: Decimal | str | float, currency: str = "TRY") -> str:
    """
    Convert monetary amount to Turkish text format.
    Example: 200.50 USD -> 'Yalnız #İki Yüz Dolar Elli Sent#'
    """
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    
    integer_part = int(amount)
    fractional_part = int((amount - integer_part) * 100)
    
    curr_main, curr_sub = _currencies.get(currency.upper(), (currency.upper(), ""))
    
    text_parts = ["Yalnız #"]
    
    if integer_part > 0 or fractional_part == 0:
        text_parts.append(f"{_int_to_text(integer_part)} {curr_main}")
        
    if fractional_part > 0:
        if integer_part > 0:
            text_parts.append(" ")
        text_parts.append(f"{_int_to_text(fractional_part)} {curr_sub}")
        
    text_parts.append("#")
    return "".join(text_parts)
