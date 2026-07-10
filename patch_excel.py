with open('extractors/excel_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add new fields to the initial data dict
data_dict_target = """    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "customer_name": None,
        "customer_title": None,
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None
    }"""
data_dict_replacement = """    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "customer_name": None,
        "customer_title": None,
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None,
        "currency": "TRY",
        "exchange_rate": None,
        "discount_amount": None,
        "notes": ""
    }"""
content = content.replace(data_dict_target, data_dict_replacement)

# Extract discount amount, currency, exchange rate, and tax_rate from df
# For excel, we look for columns that might hold discount, currency, exchange rate.
mapping_target = """        total_price = _first_present(row, ["tutar", "tutar(tl)", "toplam", "satir toplami", "toplam tutar", "line total"])"""
mapping_replacement = """        total_price = _first_present(row, ["tutar", "tutar(tl)", "toplam", "satir toplami", "toplam tutar", "line total"])
        
        tax_rate = _first_present(row, ["kdv orani", "kdv %", "kdv", "tax rate"])
        currency_val = _first_present(row, ["para birimi", "doviz", "currency", "doviz cinsi"])
        exchange_rate_val = _first_present(row, ["doviz kuru", "kur", "exchange rate"])
        discount_val = _first_present(row, ["iskonto tutari", "iskonto", "indirim", "discount"])
        notes_val = _first_present(row, ["aciklama", "not", "fatura notu", "notes"])

        if currency_val and not data["currency"] != "TRY":
            data["currency"] = str(currency_val).upper().strip()
        if exchange_rate_val and not data["exchange_rate"]:
            data["exchange_rate"] = str(exchange_rate_val)
        if discount_val and not data["discount_amount"]:
            data["discount_amount"] = str(discount_val)
        if notes_val and not data["notes"]:
            data["notes"] = str(notes_val)"""
content = content.replace(mapping_target, mapping_replacement)

item_target = """        data["items"].append({
            "code": _as_text(code),
            "description": _as_text(desc) or "Unknown Item",
            "quantity": _as_text(qty),
            "unit_price": _as_text(unit_price),
            "total_price": _as_text(total_price)
        })"""
item_replacement = """        data["items"].append({
            "code": _as_text(code),
            "description": _as_text(desc) or "Unknown Item",
            "quantity": _as_text(qty),
            "unit_price": _as_text(unit_price),
            "total_price": _as_text(total_price),
            "tax_rate": _as_text(tax_rate) or "0"
        })"""
content = content.replace(item_target, item_replacement)


with open('extractors/excel_extractor.py', 'w', encoding='utf-8') as f:
    f.write(content)
