import datetime
from decimal import Decimal, InvalidOperation

def to_decimal(value):
    if not value:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal("0.01"))

    amount_str = str(value).strip().upper()
    for currency in ["₺", "TL", "TRY", "$", "USD", "DOLAR", "€", "EUR", "EURO", "£", "GBP", "%"]:
        amount_str = amount_str.replace(currency, "")
    amount_str = amount_str.strip()

    if not amount_str:
        return Decimal("0.00")

    if "," in amount_str and "." in amount_str:
        if amount_str.rfind(",") > amount_str.rfind("."):
            amount_str = amount_str.replace(".", "").replace(",", ".")
        else:
            amount_str = amount_str.replace(",", "")
    elif "," in amount_str:
        parts = amount_str.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            amount_str = amount_str.replace(",", ".")
        elif len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            amount_str = amount_str.replace(",", "")
        else:
            amount_str = amount_str.replace(",", ".")
    elif "." in amount_str:
        parts = amount_str.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            amount_str = amount_str.replace(".", "")

    try:
        return Decimal(amount_str).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def parse_amount(value):
    return float(to_decimal(value))


def validate_invoice(data):
    errors = []
    
    if not data.get("date"):
        errors.append("Fatura tarihi bulunamadı.")
        
    tax_id = str(data.get("customer_tax_id") or "").strip()
    if not tax_id or not (len(tax_id) in (10, 11) and tax_id.isdigit()):
        invoice_no = str(data.get("invoice_no") or "").strip()
        if (
            not tax_id
            and len(invoice_no) in (10, 11)
            and invoice_no.isdigit()
        ):
            errors.append(
                "Alıcı VKN/TCKN alanı boş. "
                f"'{invoice_no}' değeri Fatura No alanında görünüyor. "
                "Bu değer alıcının vergi/kimlik numarasıysa Müşteri VKN/TCKN "
                "alanında kalmalıdır."
            )
        else:
            errors.append(
                f"Alıcı VKN/TCKN bilgisi hatalı veya eksik. (Okunan: '{tax_id}')"
            )
        
    customer_name = str(data.get("customer_name") or "").strip()
    if not customer_name or customer_name == "-":
        errors.append("Alıcı ünvanı (müşteri adı) bulunamadı.")
        
    if not data.get("items"):
        errors.append("Fatura üzerinde herhangi bir kalem (ürün/hizmet) satırı bulunamadı.")
        
    calculated_subtotal = Decimal("0.00")
    
    for item in (data.get("items") or []):
        quantity = to_decimal(item.get("quantity"))
        unit_price = to_decimal(item.get("unit_price"))
        total_price = to_decimal(item.get("total_price"))
        
        calculated_subtotal += total_price
        
        if abs((quantity * unit_price) - total_price) > Decimal("0.05"):
            errors.append(f"Kalem Matematik Hatası: '{item.get('description')}' satırında (Miktar: {quantity} x Fiyat: {unit_price} = {total_price}) tutmuyor.")

    subtotal = to_decimal(data.get("subtotal"))
    discount_amount = to_decimal(data.get("discount_amount"))
    tax_amount = to_decimal(data.get("tax_amount"))
    total_amount = to_decimal(data.get("total_amount"))
    
    if total_amount <= Decimal("0.00"):
        errors.append(f"Fatura Genel Toplamı sıfır veya geçersiz. (Okunan: {total_amount})")

    if abs(calculated_subtotal - subtotal) > Decimal("1.00") and abs((calculated_subtotal - discount_amount) - subtotal) > Decimal("1.00"):
         errors.append(f"Matematik Hatası: Kalemlerin tutar toplamı ({calculated_subtotal}) ile faturanın Ara Toplamı ({subtotal}) uyuşmuyor.")
         
    if abs((calculated_subtotal - discount_amount + tax_amount) - total_amount) > Decimal("1.00"):
         errors.append(f"Matematik Hatası: KDV ve İndirim hesaplaması sonucu Genel Toplam ile uyuşmuyor. (Hesaplanan: {(calculated_subtotal - discount_amount + tax_amount)}, Faturada Yazan: {total_amount})")
         
    raw_date = str(data.get("date") or "").strip()
    if raw_date:
        parsed_successfully = False
        for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.datetime.strptime(raw_date, fmt)
                data["date"] = parsed.strftime("%d.%m.%Y")
                parsed_successfully = True
                break
            except ValueError:
                pass
        if not parsed_successfully:
            errors.append(f"Fatura tarihi geçersiz veya anlaşılamayan bir formatta (Okunan: '{raw_date}').")

    is_valid = len(errors) == 0
                
    def format_tr_money(val: Decimal) -> str:
        return f"{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def format_quantity(value):
        try:
            d = Decimal(str(to_decimal(value)))
        except (InvalidOperation, ValueError, TypeError):
            return str(value or "")

        text = format(d.normalize(), "f")

        if "." in text:
            text = text.rstrip("0").rstrip(".")

        return text.replace(".", ",")

    if is_valid or not is_valid:
        if data.get("subtotal"): data["subtotal"] = format_tr_money(subtotal)
        if data.get("discount_amount"): data["discount_amount"] = format_tr_money(discount_amount)
        if data.get("tax_amount"): data["tax_amount"] = format_tr_money(tax_amount)
        if data.get("total_amount"): data["total_amount"] = format_tr_money(total_amount)
        
        for item in (data.get("items") or []):
            q = to_decimal(item.get("quantity"))
            up = to_decimal(item.get("unit_price"))
            tp = to_decimal(item.get("total_price"))
            item["quantity"] = format_quantity(q)
            item["unit_price"] = format_tr_money(up)
            item["total_price"] = format_tr_money(tp)

    return is_valid, errors
