import re

with open('extractors/xml_extractor.py', 'r', encoding='utf-8') as f:
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

# Add DocumentCurrencyCode, PricingExchangeRate and Note extraction
meta_target = """        # 1. Invoice ID & Date
        data["invoice_no"] = find_text_agnostic(root, "ID")
        data["date"] = find_text_agnostic(root, "IssueDate")"""
meta_replacement = """        # 1. Invoice ID & Date
        data["invoice_no"] = find_text_agnostic(root, "ID")
        data["date"] = find_text_agnostic(root, "IssueDate")
        
        currency = find_text_agnostic(root, "DocumentCurrencyCode")
        if currency:
            data["currency"] = currency
            
        for elem in root.iter():
            if elem.tag.endswith("}PricingExchangeRate") or elem.tag == "PricingExchangeRate":
                calc_rate = find_text_agnostic(elem, "CalculationRate")
                if calc_rate:
                    data["exchange_rate"] = calc_rate
                break

        notes = []
        for elem in root.iter():
            if elem.tag.endswith("}Note") or elem.tag == "Note":
                if elem.text and elem.text.strip():
                    notes.append(elem.text.strip())
        if notes:
            data["notes"] = "\\n".join(notes)"""
content = content.replace(meta_target, meta_replacement)

# Add tax_rate extraction for items
items_target = """                data["items"].append({
                    "code": item_code,
                    "description": item_name or "Unknown Item",
                    "quantity": quantity.replace('.', ',') if quantity else None,
                    "unit_price": unit_price.replace('.', ',') if unit_price else None,
                    "total_price": total_price.replace('.', ',') if total_price else None
                })"""
items_replacement = """                tax_rate = None
                for sub in elem.iter():
                    if sub.tag.endswith("}TaxTotal") or sub.tag == "TaxTotal":
                        for t_sub in sub.iter():
                            if t_sub.tag.endswith("}Percent") or t_sub.tag == "Percent":
                                tax_rate = find_text_agnostic(sub, "Percent")
                                break
                        break

                data["items"].append({
                    "code": item_code,
                    "description": item_name or "Unknown Item",
                    "quantity": quantity.replace('.', ',') if quantity else None,
                    "unit_price": unit_price.replace('.', ',') if unit_price else None,
                    "total_price": total_price.replace('.', ',') if total_price else None,
                    "tax_rate": tax_rate.replace('.', ',') if tax_rate else "0"
                })"""
content = content.replace(items_target, items_replacement)

# Add discount_amount extraction from LegalMonetaryTotal
monetary_target = """                if val is not None:
                    data["tax_amount"] = val.replace('.', ',')"""
monetary_replacement = """                if val is not None:
                    data["tax_amount"] = val.replace('.', ',')
        
        if monetary_total is not None:
            val = find_text_agnostic(monetary_total, "AllowanceTotalAmount")
            if val is not None:
                data["discount_amount"] = val.replace('.', ',')"""
content = content.replace(monetary_target, monetary_replacement)


with open('extractors/xml_extractor.py', 'w', encoding='utf-8') as f:
    f.write(content)
