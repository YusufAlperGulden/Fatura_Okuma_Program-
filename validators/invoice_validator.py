import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_QUANTUM = Decimal("0.01")

def _parse_decimal(value):
    """Parse invoice numbers without turning invalid text into a valid zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        try:
            if not value.is_finite():
                return None
            return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None
    if isinstance(value, (int, float)):
        try:
            parsed = Decimal(str(value))
            if not parsed.is_finite():
                return None
            return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return None

    amount_str = str(value).strip().upper()
    for currency in ["₺", "TL", "TRY", "$", "USD", "DOLAR", "€", "EUR", "EURO", "£", "GBP", "%"]:
        amount_str = amount_str.replace(currency, "")
    amount_str = amount_str.strip()

    if not amount_str:
        return None

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
        parsed = Decimal(amount_str)
        if not parsed.is_finite():
            return None
        return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def to_decimal(value):
    parsed = _parse_decimal(value)
    return parsed if parsed is not None else Decimal("0.00")


def parse_amount(value):
    return float(to_decimal(value))


def _allocate_discount_shares(line_totals, discount):
    """Distribute a discount without losing or creating a rounding cent."""
    if not line_totals:
        return []

    subtotal = sum(line_totals, Decimal("0.00"))
    if subtotal <= Decimal("0.00") or discount <= Decimal("0.00"):
        return [Decimal("0.00") for _ in line_totals]

    shares = []
    allocated = Decimal("0.00")
    for index, line_total in enumerate(line_totals):
        if index == len(line_totals) - 1:
            share = discount - allocated
        else:
            share = (discount * line_total / subtotal).quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            allocated += share
        shares.append(share)
    return shares


def _infer_uniform_missing_tax_rate(data):
    """Fill legacy parser gaps without treating an explicit blank as missing.

    Some source formats expose only the document-level KDV amount.  When every
    line contains ``None`` (not an edited empty string) and the aggregate amount
    yields a common Turkish KDV rate, make that rate explicit before validating.
    """
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return
    if any(not isinstance(item, dict) for item in items):
        return
    if not all(item.get("tax_rate") is None for item in items):
        return

    line_totals = [_parse_decimal(item.get("total_price")) for item in items]
    if any(line_total is None for line_total in line_totals):
        return
    subtotal = sum(line_totals, Decimal("0.00"))
    tax_amount = _parse_decimal(data.get("tax_amount"))
    discount = _parse_decimal(data.get("discount_amount")) or Decimal("0.00")
    if tax_amount is None:
        return

    taxable = subtotal - discount
    if taxable <= Decimal("0.00"):
        return
    inferred = (tax_amount / taxable * Decimal("100")).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    standard_rates = {
        Decimal("0.00"),
        Decimal("1.00"),
        Decimal("8.00"),
        Decimal("10.00"),
        Decimal("18.00"),
        Decimal("20.00"),
    }
    if inferred not in standard_rates:
        return
    for item in items:
        item["tax_rate"] = inferred


def recalculate_invoice_totals(data):
    """Canonicalize document totals from item totals and item KDV rates.

    This is used only for user-reviewed edit requests. Initial extraction still
    validates the totals printed on the source invoice without rewriting them.
    """
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return data

    parsed_lines = []
    for item in items:
        if not isinstance(item, dict):
            return data
        line_total = _parse_decimal(item.get("total_price"))
        tax_rate = _parse_decimal(item.get("tax_rate"))
        if line_total is None or tax_rate is None:
            return data
        parsed_lines.append((line_total, tax_rate))

    discount = _parse_decimal(data.get("discount_amount"))
    if discount is None:
        discount = Decimal("0.00")

    subtotal = sum((line_total for line_total, _ in parsed_lines), Decimal("0.00"))
    tax_amount = Decimal("0.00")
    discount_shares = _allocate_discount_shares(
        [line_total for line_total, _ in parsed_lines],
        discount,
    )
    for (line_total, tax_rate), discount_share in zip(parsed_lines, discount_shares):
        taxable = line_total - discount_share
        tax_amount += (taxable * tax_rate / Decimal("100")).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    data["subtotal"] = subtotal
    data["tax_amount"] = tax_amount
    data["total_amount"] = subtotal - discount + tax_amount
    return data


def validate_invoice(data):
    errors = []

    _infer_uniform_missing_tax_rate(data)

    invoice_no = str(data.get("invoice_no") or "").strip()
    if not invoice_no:
        errors.append("Fatura numarası boş bırakılamaz.")
    
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
    
    parsed_tax_lines = []

    for index, item in enumerate((data.get("items") or []), start=1):
        if not isinstance(item, dict):
            errors.append(f"{index}. fatura kalemi geçersiz.")
            continue

        description_value = item.get("description")
        if description_value is None:
            description_value = item.get("name")
        description = str(description_value or "").strip()
        if not description:
            errors.append(f"{index}. kalemin ürün/hizmet açıklaması boş bırakılamaz.")

        quantity = _parse_decimal(item.get("quantity"))
        unit_price = _parse_decimal(item.get("unit_price"))
        total_price = _parse_decimal(item.get("total_price"))
        tax_rate = _parse_decimal(item.get("tax_rate"))

        if quantity is None or quantity <= Decimal("0.00"):
            errors.append(f"{index}. kalemin miktarı sıfırdan büyük sayısal bir değer olmalıdır.")
        if unit_price is None or unit_price < Decimal("0.00"):
            errors.append(f"{index}. kalemin birim fiyatı geçerli bir sayısal değer olmalıdır.")
        if total_price is None or total_price < Decimal("0.00"):
            errors.append(f"{index}. kalemin satır toplamı geçerli bir sayısal değer olmalıdır.")
        if tax_rate is None or not (Decimal("0.00") <= tax_rate <= Decimal("100.00")):
            errors.append(f"{index}. kalemin KDV oranı 0 ile 100 arasında sayısal bir değer olmalıdır.")

        if total_price is not None:
            calculated_subtotal += total_price
        if total_price is not None and tax_rate is not None:
            parsed_tax_lines.append((total_price, tax_rate))

        if (
            quantity is not None
            and unit_price is not None
            and total_price is not None
            and abs((quantity * unit_price) - total_price) > Decimal("0.05")
        ):
            errors.append(f"Kalem Matematik Hatası: '{item.get('description')}' satırında (Miktar: {quantity} x Fiyat: {unit_price} = {total_price}) tutmuyor.")

    subtotal_raw = _parse_decimal(data.get("subtotal"))
    discount_raw = _parse_decimal(data.get("discount_amount"))
    tax_raw = _parse_decimal(data.get("tax_amount"))
    total_raw = _parse_decimal(data.get("total_amount"))

    subtotal = subtotal_raw if subtotal_raw is not None else Decimal("0.00")
    discount_amount = discount_raw if discount_raw is not None else Decimal("0.00")
    tax_amount = tax_raw if tax_raw is not None else Decimal("0.00")
    total_amount = total_raw if total_raw is not None else Decimal("0.00")

    if subtotal_raw is None:
        errors.append("Fatura ara toplamı geçerli bir sayısal değer olmalıdır.")
    if data.get("discount_amount") not in (None, "") and discount_raw is None:
        errors.append("Fatura indirim tutarı geçerli bir sayısal değer olmalıdır.")
    if tax_raw is None:
        errors.append("Fatura KDV toplamı geçerli bir sayısal değer olmalıdır.")
    if total_raw is None:
        errors.append("Fatura genel toplamı geçerli bir sayısal değer olmalıdır.")
    if discount_amount < Decimal("0.00") or discount_amount > calculated_subtotal:
        errors.append("Fatura indirim tutarı sıfırdan küçük veya ara toplamdan büyük olamaz.")
    
    if total_amount <= Decimal("0.00"):
        errors.append(f"Fatura Genel Toplamı sıfır veya geçersiz. (Okunan: {total_amount})")

    if abs(calculated_subtotal - subtotal) > Decimal("1.00") and abs((calculated_subtotal - discount_amount) - subtotal) > Decimal("1.00"):
         errors.append(f"Matematik Hatası: Kalemlerin tutar toplamı ({calculated_subtotal}) ile faturanın Ara Toplamı ({subtotal}) uyuşmuyor.")
         
    if abs((calculated_subtotal - discount_amount + tax_amount) - total_amount) > Decimal("1.00"):
         errors.append(f"Matematik Hatası: KDV ve İndirim hesaplaması sonucu Genel Toplam ile uyuşmuyor. (Hesaplanan: {(calculated_subtotal - discount_amount + tax_amount)}, Faturada Yazan: {total_amount})")

    if parsed_tax_lines and len(parsed_tax_lines) == len(data.get("items") or []):
        expected_tax = Decimal("0.00")
        discount_shares = _allocate_discount_shares(
            [line_total for line_total, _ in parsed_tax_lines],
            discount_amount,
        )
        for (line_total, tax_rate), discount_share in zip(parsed_tax_lines, discount_shares):
            expected_tax += (
                (line_total - discount_share) * tax_rate / Decimal("100")
            ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if abs(expected_tax - tax_amount) > Decimal("1.00"):
            errors.append(
                "Matematik Hatası: Kalem KDV oranlarından hesaplanan toplam KDV "
                f"({expected_tax}) ile faturanın KDV toplamı ({tax_amount}) uyuşmuyor."
            )
         
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

    raw_time = str(data.get("time") or "").strip()
    if raw_time:
        parsed_time = None
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                parsed_time = datetime.datetime.strptime(raw_time, fmt)
                break
            except ValueError:
                pass
        if parsed_time is None:
            errors.append(
                f"Fatura saati geçersiz. HH:MM veya HH:MM:SS biçiminde olmalıdır (Okunan: '{raw_time}')."
            )
        else:
            data["time"] = parsed_time.strftime("%H:%M:%S")

    is_valid = len(errors) == 0
                
    def format_tr_money(val: Decimal) -> str:
        return f"{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def format_quantity(value: Decimal):
        text = format(value.normalize(), "f")

        if "." in text:
            text = text.rstrip("0").rstrip(".")

        return text.replace(".", ",")

    if subtotal_raw is not None:
        data["subtotal"] = format_tr_money(subtotal_raw)
    if discount_raw is not None:
        data["discount_amount"] = format_tr_money(discount_raw)
    if tax_raw is not None:
        data["tax_amount"] = format_tr_money(tax_raw)
    if total_raw is not None:
        data["total_amount"] = format_tr_money(total_raw)

    for item in (data.get("items") or []):
        if not isinstance(item, dict):
            continue
        quantity = _parse_decimal(item.get("quantity"))
        unit_price = _parse_decimal(item.get("unit_price"))
        total_price = _parse_decimal(item.get("total_price"))
        tax_rate = _parse_decimal(item.get("tax_rate"))
        if quantity is not None:
            item["quantity"] = format_quantity(quantity)
        if unit_price is not None:
            item["unit_price"] = format_tr_money(unit_price)
        if total_price is not None:
            item["total_price"] = format_tr_money(total_price)
        if tax_rate is not None:
            item["tax_rate"] = format_quantity(tax_rate)

    return is_valid, errors
