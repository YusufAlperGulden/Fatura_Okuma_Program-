import datetime
import re
from decimal import Decimal, ROUND_HALF_UP

from utils.invoice_values import (
    DOCUMENT_AMOUNT_TOLERANCE,
    MONEY_QUANTUM,
    decimal_places,
    format_decimal,
    normalize_invoice_currency_fields,
    parse_localized_decimal,
    quantize_money,
)

_UNSAFE_ADDRESS_CONTROL_CHARS = re.compile(r"[\x00-\x1F\x7F-\x9F]")
_POSTAL_ADDRESS_SCALAR_LIMITS = {
    "street_name": 200,
    "building_name": 200,
    "building_number": 50,
    "city_subdivision_name": 100,
    "city_name": 100,
    "postal_zone": 20,
    "district": 100,
    "country_code": 2,
    "country_name": 100,
}
_POSTAL_ADDRESS_ALLOWED_KEYS = frozenset(
    list(_POSTAL_ADDRESS_SCALAR_LIMITS.keys()) + ["address_lines"]
)
_POSTAL_ADDRESS_MAX_LINES = 2
_POSTAL_ADDRESS_MAX_LINE_LENGTH = 100


def _parse_decimal(value):
    """Parse invoice numbers without changing their decimal precision."""
    return parse_localized_decimal(value)


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
    subtotal = quantize_money(sum(line_totals, Decimal("0.00")))
    tax_amount = _parse_decimal(data.get("tax_amount"))
    discount = _parse_decimal(data.get("discount_amount")) or Decimal("0.00")
    discount = quantize_money(discount)
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
        parsed_lines.append((quantize_money(line_total), tax_rate))

    discount = _parse_decimal(data.get("discount_amount"))
    if discount is None:
        discount = Decimal("0.00")
    discount = quantize_money(discount)

    subtotal = quantize_money(
        sum((line_total for line_total, _ in parsed_lines), Decimal("0.00"))
    )
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
    data["tax_amount"] = quantize_money(tax_amount)
    data["total_amount"] = quantize_money(subtotal - discount + tax_amount)
    return data


def validate_invoice(data):
    if not isinstance(data, dict):
        return False, ["Fatura verisi bir nesne olmalıdır."]

    _infer_uniform_missing_tax_rate(data)
    errors = []

    if data.get("fx_conversion_required") is True:
        errors.append(
            "USD was detected, but a valid exchange rate is required before "
            "the TRY amounts can be converted to USD."
        )

    try:
        document_currency = normalize_invoice_currency_fields(data)
    except ValueError:
        document_currency = None
        errors.append(
            f"Fatura para birimi desteklenmiyor. (Okunan: '{data.get('currency')}')"
        )

    exchange_rate = _parse_decimal(data.get("exchange_rate"))
    if data.get("exchange_rate") not in (None, ""):
        if exchange_rate is None or exchange_rate <= Decimal("0"):
            errors.append("Fatura döviz kuru sıfırdan büyük sayısal bir değer olmalıdır.")
        elif decimal_places(exchange_rate.normalize()) > 8:
            errors.append("Fatura döviz kuru en fazla 8 ondalık basamak içerebilir.")

    invoice_no = str(data.get("invoice_no") or "").strip()
    # Fatura numarası artık zorunlu değil, Uyumsoft (veya API) tarafında otomatik atanabilecek.
    
    if not data.get("date"):
        errors.append("Fatura tarihi bulunamadı.")
        
    tax_id = str(data.get("customer_tax_id") or "").strip()
    
    # Bypass validation for common accountant placeholders
    if tax_id in ("11111111111", "111111111111"):
        data["customer_tax_id"] = "11111111111"
        pass # valid placeholder
    elif not tax_id or not (len(tax_id) in (10, 11) and tax_id.isdigit()):
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
        elif tax_id and not tax_id.isdigit():
            errors.append(
                f"Alıcı VKN/TCKN bilgisi hatalı. Lütfen sadece sayı kullanarak yazınız. Harf kullanmayınız. (Okunan: '{tax_id}')"
            )
        else:
            errors.append(
                f"Alıcı VKN/TCKN bilgisi hatalı veya eksik. Lütfen 10 veya 11 haneli olacak şekilde faturayı düzenleyiniz. (Okunan: '{tax_id}')"
            )
    elif len(tax_id) == 10:
        digits = [int(d) for d in tax_id]
        
        sum_val = 0
        for i in range(9):
            tmp = (digits[i] + 10 - (i + 1)) % 10
            if tmp == 9:
                sum_val += tmp
            else:
                sum_val += (tmp * (2 ** (10 - (i + 1)))) % 9
                
        last_digit = (10 - (sum_val % 10)) % 10
        if digits[9] != last_digit:
            errors.append(f"VKN doğrulama algoritması hatası. Beklenen son hane: {last_digit}, Okunan: {digits[9]}. (Okunan VKN: '{tax_id}')")
    elif len(tax_id) == 11:
        if tax_id[0] == '0':
            errors.append(f"T.C. Kimlik Numarası hatalı. TCKN '0' ile başlayamaz. (Okunan: '{tax_id}')")
        else:
            digits = [int(d) for d in tax_id]
            sum_odd = sum(digits[0:9:2])
            sum_even = sum(digits[1:8:2])
            tenth = (sum_odd * 7 - sum_even) % 10
            eleventh = sum(digits[0:10]) % 10
            
            if digits[10] % 2 != 0:
                errors.append(
                    f"T.C. Kimlik Numarası hatalı. 11. hane (son rakam) her zaman çift sayı olmalıdır (Okunan son rakam: '{digits[10]}'). (Okunan TCKN: '{tax_id}')"
                )
            elif digits[9] != tenth:
                odd_digits_str = " + ".join(str(d) for d in digits[0:9:2])
                even_digits_str = " + ".join(str(d) for d in digits[1:8:2])
                calc_details = f"Tek haneler (1,3,5,7,9. sıralar): [{odd_digits_str}] = {sum_odd} | Çift haneler (2,4,6,8. sıralar): [{even_digits_str}] = {sum_even} | Formül: (({sum_odd} x 7) - {sum_even}) mod 10 = {tenth}"
                errors.append(
                    f"T.C. Kimlik Numarası hatalı. 10. rakam kuralı ihlali: (Tek haneler toplamı x 7 - Çift haneler toplamı) işleminin son basamağı {tenth} olmalıyken, faturada '{digits[9]}' okundu. Hesaplama Detayı: {calc_details}. (Okunan TCKN: '{tax_id}')"
                )
            elif digits[10] != eleventh:
                all_ten_str = " + ".join(str(d) for d in digits[0:10])
                calc_details = f"İlk 10 rakam: [{all_ten_str}] = {sum(digits[0:10])} | Formül: {sum(digits[0:10])} mod 10 = {eleventh}"
                errors.append(
                    f"T.C. Kimlik Numarası hatalı. 11. rakam kuralı ihlali: İlk 10 rakamın toplamının son basamağı {eleventh} olmalıyken, faturada '{digits[10]}' okundu. Hesaplama Detayı: {calc_details}. (Okunan TCKN: '{tax_id}')"
                )
        
    customer_name = str(
        data.get("customer_name") or data.get("customer_title") or ""
    ).strip()
    if not customer_name or customer_name == "-":
        errors.append("Alıcı ünvanı (müşteri adı) bulunamadı.")
    else:
        data["customer_name"] = customer_name
        data["customer_title"] = customer_name

    customer_postal_address = data.get("customer_postal_address")
    if customer_postal_address is not None:
        if not isinstance(customer_postal_address, dict):
            errors.append("Alıcı yapısal posta adresi (customer_postal_address) bir nesne (sözlük) olmalıdır.")
        else:
            unknown_keys = sorted(
                set(customer_postal_address) - _POSTAL_ADDRESS_ALLOWED_KEYS,
                key=str,
            )
            for key in unknown_keys:
                errors.append(
                    f"Geçersiz adres alanı (customer_postal_address): '{key}'"
                )

            for key, max_length in _POSTAL_ADDRESS_SCALAR_LIMITS.items():
                if key not in customer_postal_address:
                    continue
                value = customer_postal_address[key]
                if not isinstance(value, str):
                    errors.append(
                        f"Adres alanı '{key}' yalnızca metin olmalıdır."
                    )
                    continue

                normalized_value = value.strip()
                if len(normalized_value) > max_length:
                    errors.append(
                        f"Adres alanı '{key}' en fazla {max_length} karakter olabilir."
                    )
                if _UNSAFE_ADDRESS_CONTROL_CHARS.search(normalized_value):
                    errors.append(
                        f"Adres alanı '{key}' geçersiz kontrol karakterleri içeriyor."
                    )
                if key == "country_code" and normalized_value:
                    if not re.fullmatch(r"[A-Za-z]{2}", normalized_value):
                        errors.append(
                            "Adres alanı 'country_code' iki harfli ISO ülke kodu olmalıdır."
                        )
                    else:
                        normalized_value = normalized_value.upper()
                customer_postal_address[key] = normalized_value

            if "address_lines" in customer_postal_address:
                address_lines = customer_postal_address["address_lines"]
                if not isinstance(address_lines, list):
                    errors.append(
                        "Adres alanı 'address_lines' yalnızca metinlerden oluşan bir liste olmalıdır."
                    )
                else:
                    if len(address_lines) > _POSTAL_ADDRESS_MAX_LINES:
                        errors.append(
                            "Adres alanı 'address_lines' en fazla "
                            f"{_POSTAL_ADDRESS_MAX_LINES} satır içerebilir."
                        )
                    normalized_lines = []
                    for line_index, line in enumerate(address_lines, start=1):
                        if not isinstance(line, str):
                            errors.append(
                                "Adres alanı 'address_lines' içindeki "
                                f"{line_index}. değer yalnızca metin olmalıdır."
                            )
                            continue
                        normalized_line = line.strip()
                        if len(normalized_line) > _POSTAL_ADDRESS_MAX_LINE_LENGTH:
                            errors.append(
                                "Adres alanı 'address_lines' içindeki "
                                f"{line_index}. satır en fazla "
                                f"{_POSTAL_ADDRESS_MAX_LINE_LENGTH} karakter olabilir."
                            )
                        if _UNSAFE_ADDRESS_CONTROL_CHARS.search(normalized_line):
                            errors.append(
                                "Adres alanı 'address_lines' içindeki "
                                f"{line_index}. satır geçersiz kontrol karakterleri içeriyor."
                            )
                        normalized_lines.append(normalized_line)
                    customer_postal_address["address_lines"] = normalized_lines

    items_value = data.get("items")
    if not isinstance(items_value, list):
        errors.append("Fatura kalemleri bir liste olmalıdır.")
        items = []
    else:
        items = items_value

    if not items:
        errors.append("Fatura üzerinde herhangi bir kalem (ürün/hizmet) satırı bulunamadı.")
        
    calculated_subtotal = Decimal("0.00")
    
    parsed_tax_lines = []

    for index, item in enumerate(items, start=1):
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
        elif decimal_places(quantity.normalize()) > 6:
            errors.append(f"{index}. kalemin miktarı en fazla 6 ondalık basamak içerebilir.")
        if unit_price is None or unit_price < Decimal("0.00"):
            errors.append(f"{index}. kalemin birim fiyatı geçerli bir sayısal değer olmalıdır.")
        elif decimal_places(unit_price.normalize()) > 8:
            errors.append(f"{index}. kalemin birim fiyatı en fazla 8 ondalık basamak içerebilir.")
        if total_price is None or total_price < Decimal("0.00"):
            errors.append(f"{index}. kalemin satır toplamı geçerli bir sayısal değer olmalıdır.")
        elif total_price != quantize_money(total_price):
            errors.append(f"{index}. kalemin satır toplamı en fazla 2 ondalık basamak içerebilir.")
        if tax_rate is None or not (Decimal("0.00") <= tax_rate <= Decimal("100.00")):
            errors.append(f"{index}. kalemin KDV oranı 0 ile 100 arasında sayısal bir değer olmalıdır.")
        elif decimal_places(tax_rate.normalize()) > 4:
            errors.append(f"{index}. kalemin KDV oranı en fazla 4 ondalık basamak içerebilir.")

        if total_price is not None:
            calculated_subtotal += quantize_money(total_price)
        if total_price is not None and tax_rate is not None:
            parsed_tax_lines.append((quantize_money(total_price), tax_rate))

        if (
            quantity is not None
            and unit_price is not None
            and total_price is not None
        ):
            # Calculate a dynamic tolerance that scales with quantity to allow for small unit price rounding differences
            dynamic_tolerance = max(Decimal("0.05"), quantize_money(quantity * Decimal("0.005")))
            if abs(quantize_money(quantity * unit_price) - quantize_money(total_price)) > dynamic_tolerance:
                errors.append(f"Kalem Matematik Hatası: '{item.get('description')}' satırında (Miktar: {quantity} x Fiyat: {unit_price} = {total_price}) tutmuyor.")

    subtotal_raw = _parse_decimal(data.get("subtotal"))
    discount_raw = _parse_decimal(data.get("discount_amount"))
    tax_raw = _parse_decimal(data.get("tax_amount"))
    total_raw = _parse_decimal(data.get("total_amount"))
    foreign_total_raw = _parse_decimal(data.get("foreign_total"))
    local_subtotal_raw = _parse_decimal(data.get("local_subtotal"))
    local_discount_raw = _parse_decimal(data.get("local_discount_amount"))
    local_tax_raw = _parse_decimal(data.get("local_tax_amount"))
    local_total_raw = _parse_decimal(data.get("local_total"))

    subtotal = quantize_money(subtotal_raw) if subtotal_raw is not None else Decimal("0.00")
    discount_amount = quantize_money(discount_raw) if discount_raw is not None else Decimal("0.00")
    tax_amount = quantize_money(tax_raw) if tax_raw is not None else Decimal("0.00")
    total_amount = quantize_money(total_raw) if total_raw is not None else Decimal("0.00")
    calculated_subtotal = quantize_money(calculated_subtotal)

    if subtotal_raw is None:
        errors.append("Fatura ara toplamı geçerli bir sayısal değer olmalıdır.")
    elif subtotal_raw != subtotal:
        errors.append("Fatura ara toplamı en fazla 2 ondalık basamak içerebilir.")
    if data.get("discount_amount") not in (None, "") and discount_raw is None:
        errors.append("Fatura indirim tutarı geçerli bir sayısal değer olmalıdır.")
    elif discount_raw is not None and discount_raw != discount_amount:
        errors.append("Fatura indirim tutarı en fazla 2 ondalık basamak içerebilir.")
    if tax_raw is None:
        errors.append("Fatura KDV toplamı geçerli bir sayısal değer olmalıdır.")
    elif tax_raw != tax_amount:
        errors.append("Fatura KDV toplamı en fazla 2 ondalık basamak içerebilir.")
    if total_raw is None:
        errors.append("Fatura genel toplamı geçerli bir sayısal değer olmalıdır.")
    elif total_raw != total_amount:
        errors.append("Fatura genel toplamı en fazla 2 ondalık basamak içerebilir.")
    if discount_amount < Decimal("0.00") or discount_amount > calculated_subtotal:
        errors.append("Fatura indirim tutarı sıfırdan küçük veya ara toplamdan büyük olamaz.")
    
    if total_amount <= Decimal("0.00"):
        errors.append(f"Fatura Genel Toplamı sıfır veya geçersiz. (Okunan: {total_amount})")

    if document_currency and document_currency != "TRY":
        if data.get("foreign_total") not in (None, ""):
            if foreign_total_raw is None:
                errors.append(
                    "Döviz toplamı (foreign_total) geçerli bir sayısal değer olmalıdır."
                )
            elif (
                total_raw is not None
                and abs(quantize_money(foreign_total_raw) - total_amount)
                > DOCUMENT_AMOUNT_TOLERANCE
            ):
                errors.append(
                    "Döviz toplamı (foreign_total), faturanın döviz genel "
                    "toplamı (total_amount) ile uyuşmuyor."
                )

        for (
            local_field,
            local_value,
            document_value,
            document_value_is_available,
        ) in (
            (
                "local_subtotal",
                local_subtotal_raw,
                subtotal,
                subtotal_raw is not None,
            ),
            (
                "local_discount_amount",
                local_discount_raw,
                discount_amount,
                True,
            ),
            (
                "local_tax_amount",
                local_tax_raw,
                tax_amount,
                tax_raw is not None,
            ),
        ):
            if data.get(local_field) in (None, ""):
                continue
            if local_value is None:
                errors.append(f"{local_field} must be a valid numeric amount.")
                continue
            if exchange_rate is None or exchange_rate <= Decimal("0"):
                errors.append(
                    f"A positive exchange rate is required to validate {local_field}."
                )
                continue
            if not document_value_is_available:
                continue
            expected_local_value = quantize_money(
                document_value * exchange_rate
            )
            if (
                abs(expected_local_value - quantize_money(local_value))
                > DOCUMENT_AMOUNT_TOLERANCE
            ):
                errors.append(
                    f"{local_field} does not match its document-currency "
                    "amount multiplied by the exchange rate."
                )

        if data.get("local_total") not in (None, ""):
            if local_total_raw is None:
                errors.append(
                    "Yerel para toplamı (local_total) geçerli bir sayısal değer olmalıdır."
                )
            elif exchange_rate is None or exchange_rate <= Decimal("0"):
                errors.append(
                    "Yerel para toplamını doğrulamak için pozitif döviz kuru gereklidir."
                )
            elif total_raw is not None:
                expected_local_total = quantize_money(total_amount * exchange_rate)
                if (
                    abs(expected_local_total - quantize_money(local_total_raw))
                    > DOCUMENT_AMOUNT_TOLERANCE
                ):
                    errors.append(
                        "Döviz dönüşüm hatası: döviz genel toplamı ile "
                        "TL/yerel genel toplamı kur üzerinden uyuşmuyor."
                    )

    if (
        calculated_subtotal != subtotal
        and quantize_money(calculated_subtotal - discount_amount) != subtotal
    ):
        errors.append(f"Matematik Hatası: Kalemlerin tutar toplamı ({calculated_subtotal}) ile faturanın Ara Toplamı ({subtotal}) uyuşmuyor.")

    expected_total = quantize_money(calculated_subtotal - discount_amount + tax_amount)
    if abs(expected_total - total_amount) > Decimal("1.00"):
        errors.append(f"Matematik Hatası: KDV ve İndirim hesaplaması sonucu Genel Toplam ile uyuşmuyor. (Hesaplanan: {(calculated_subtotal - discount_amount + tax_amount)}, Faturada Yazan: {total_amount})")

    if parsed_tax_lines and len(parsed_tax_lines) == len(items):
        expected_tax = Decimal("0.00")
        discount_shares = _allocate_discount_shares(
            [line_total for line_total, _ in parsed_tax_lines],
            discount_amount,
        )
        for (line_total, tax_rate), discount_share in zip(parsed_tax_lines, discount_shares):
            expected_tax += (
                (line_total - discount_share) * tax_rate / Decimal("100")
            ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        expected_tax = quantize_money(expected_tax)
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
        return f"{quantize_money(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def format_number(value: Decimal, max_places: int, min_places: int = 0):
        return format_decimal(
            value,
            max_places=max_places,
            min_places=min_places,
        ).replace(".", ",")

    if subtotal_raw is not None:
        data["subtotal"] = format_tr_money(subtotal_raw)
    if discount_raw is not None:
        data["discount_amount"] = format_tr_money(discount_raw)
    if tax_raw is not None:
        data["tax_amount"] = format_tr_money(tax_raw)
    if total_raw is not None:
        data["total_amount"] = format_tr_money(total_raw)
    if exchange_rate is not None and exchange_rate > Decimal("0"):
        data["exchange_rate"] = format_number(exchange_rate, 8, min_places=4)

    for item in items:
        if not isinstance(item, dict):
            continue
        quantity = _parse_decimal(item.get("quantity"))
        unit_price = _parse_decimal(item.get("unit_price"))
        total_price = _parse_decimal(item.get("total_price"))
        tax_rate = _parse_decimal(item.get("tax_rate"))
        if quantity is not None and decimal_places(quantity.normalize()) <= 6:
            item["quantity"] = format_number(quantity, 6)
        if unit_price is not None and decimal_places(unit_price.normalize()) <= 8:
            item["unit_price"] = format_number(unit_price, 8, min_places=2)
        if total_price is not None and total_price == quantize_money(total_price):
            item["total_price"] = format_tr_money(total_price)
        if tax_rate is not None and decimal_places(tax_rate.normalize()) <= 4:
            item["tax_rate"] = format_number(tax_rate, 4)

        serial_numbers = item.get("serial_numbers")
        if isinstance(serial_numbers, list) and len(serial_numbers) > 0:
            if quantity is not None:
                if quantity != quantity.to_integral_value():
                    errors.append(f"Seri numarası olan kalemlerde miktar tam sayı olmalıdır.")
                elif len(serial_numbers) != int(quantity):
                    errors.append(f"Faturada belirtilen seri numarası adedi ({len(serial_numbers)}) ile miktar ({int(quantity)}) uyuşmuyor.")

    is_valid = len(errors) == 0
    return is_valid, errors
