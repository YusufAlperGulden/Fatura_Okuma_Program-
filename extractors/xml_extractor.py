import xml.etree.ElementTree as ET

from utils.serial_numbers import normalize_serial_numbers

def find_text_agnostic(root, tag_name):
    """
    Finds the first element whose tag ends with tag_name, ignoring XML namespaces.
    Returns its text content or None.
    """
    for elem in root.iter():
        if elem.tag.endswith(f"}}{tag_name}") or elem.tag == tag_name:
            return elem.text
    return None

def child_text_agnostic(root, tag_name):
    for elem in list(root):
        if elem.tag.endswith(f"}}{tag_name}") or elem.tag == tag_name:
            return elem.text
    return None

def parse_xml_invoice(file_path: str) -> dict:
    """
    Parses a UBL-TR formatted e-Fatura/e-Arşiv XML file.
    """
    print(f"Parsing XML invoice: {file_path}")
    
    data = {
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
    }
    
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # 1. Invoice ID & Date
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
        for elem in list(root):
            if elem.tag.endswith("}Note") or elem.tag == "Note":
                if elem.text and elem.text.strip():
                    notes.append(elem.text.strip())
        if notes:
            data["notes"] = "\n".join(notes)
        
        # 2. Customer Tax ID (Usually inside AccountingCustomerParty -> Party -> PartyIdentification -> ID)
        # To be precise, we find AccountingCustomerParty and search within it.
        customer_party = None
        for elem in root.iter():
            if elem.tag.endswith("}AccountingCustomerParty") or elem.tag == "AccountingCustomerParty":
                customer_party = elem
                break
                
        if customer_party is not None:
            party_id = find_text_agnostic(customer_party, "ID")
            if party_id:
                data["customer_tax_id"] = party_id

            customer_name = find_text_agnostic(customer_party, "RegistrationName")
            if not customer_name:
                for elem in customer_party.iter():
                    if elem.tag.endswith("}PartyName") or elem.tag == "PartyName":
                        customer_name = find_text_agnostic(elem, "Name")
                        break
            if customer_name:
                data["customer_name"] = customer_name
                data["customer_title"] = customer_name
                
        # 3. Invoice Lines
        for elem in root.iter():
            if elem.tag.endswith("}InvoiceLine") or elem.tag == "InvoiceLine":
                item_code = None
                for sub in elem.iter():
                    if (
                        sub.tag.endswith("}SellersItemIdentification")
                        or sub.tag.endswith("}BuyersItemIdentification")
                        or sub.tag.endswith("}StandardItemIdentification")
                        or sub.tag in {
                            "SellersItemIdentification",
                            "BuyersItemIdentification",
                            "StandardItemIdentification",
                        }
                    ):
                        item_code = find_text_agnostic(sub, "ID")
                        if item_code:
                            break
                if not item_code:
                    item_code = child_text_agnostic(elem, "ID")
                # Description usually in Item -> Name
                item_name = None
                item_element = None
                for sub in elem.iter():
                    if sub.tag.endswith("}Item") or sub.tag == "Item":
                        item_element = sub
                        item_name = find_text_agnostic(sub, "Name")
                        break

                serial_values = []
                if item_element is not None:
                    for sub in item_element.iter():
                        if not (
                            sub.tag.endswith("}ItemInstance")
                            or sub.tag == "ItemInstance"
                        ):
                            continue
                        for instance_child in sub.iter():
                            if (
                                instance_child.tag.endswith("}SerialID")
                                or instance_child.tag == "SerialID"
                            ) and instance_child.text:
                                serial_values.append(instance_child.text)
                        
                quantity = find_text_agnostic(elem, "InvoicedQuantity")
                
                # Unit Price usually in Price -> PriceAmount
                unit_price = None
                for sub in elem.iter():
                    if sub.tag.endswith("}Price") or sub.tag == "Price":
                        unit_price = find_text_agnostic(sub, "PriceAmount")
                        break
                        
                total_price = find_text_agnostic(elem, "LineExtensionAmount")
                
                tax_rate = None
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
                    "serial_numbers": normalize_serial_numbers(serial_values),
                    "quantity": quantity.replace('.', ',') if quantity else None,
                    "unit_price": unit_price.replace('.', ',') if unit_price else None,
                    "total_price": total_price.replace('.', ',') if total_price else None,
                    "tax_rate": tax_rate.replace('.', ',') if tax_rate else "0"
                })
                
        # 4. Totals (LegalMonetaryTotal)
        monetary_total = None
        for elem in root.iter():
            if elem.tag.endswith("}LegalMonetaryTotal") or elem.tag == "LegalMonetaryTotal":
                monetary_total = elem
                break
                
        if monetary_total is not None:
            subt = child_text_agnostic(monetary_total, "LineExtensionAmount")
            data["subtotal"] = subt.replace('.', ',') if subt else None

            discount = child_text_agnostic(monetary_total, "AllowanceTotalAmount")
            data["discount_amount"] = (
                discount.replace('.', ',') if discount else None
            )

            tot = (
                child_text_agnostic(monetary_total, "PayableAmount")
                or child_text_agnostic(monetary_total, "TaxInclusiveAmount")
            )
            data["total_amount"] = tot.replace('.', ',') if tot else None

        tax_total = None
        for elem in root.iter():
            if elem.tag.endswith("}TaxTotal") or elem.tag == "TaxTotal":
                tax_total = elem
                break
        if tax_total is not None:
            tax_amt = child_text_agnostic(tax_total, "TaxAmount") or find_text_agnostic(tax_total, "TaxAmount")
            data["tax_amount"] = tax_amt.replace('.', ',') if tax_amt else data["tax_amount"]

        if not data["tax_amount"] and data["subtotal"] and data["total_amount"]:
            subtotal = float(data["subtotal"].replace(".", "").replace(",", "."))
            total = float(data["total_amount"].replace(".", "").replace(",", "."))
            data["tax_amount"] = f"{total - subtotal:.2f}".replace(".", ",")

        print("Successfully read XML file.")
        return data
        
    except Exception as e:
        print(f"Error parsing XML file {file_path}: {e}")
        return {}
