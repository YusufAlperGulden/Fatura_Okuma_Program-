import xml.etree.ElementTree as ET

def find_text_agnostic(root, tag_name):
    """
    Finds the first element whose tag ends with tag_name, ignoring XML namespaces.
    Returns its text content or None.
    """
    for elem in root.iter():
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
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None
    }
    
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # 1. Invoice ID & Date
        data["invoice_no"] = find_text_agnostic(root, "ID")
        data["date"] = find_text_agnostic(root, "IssueDate")
        
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
                
        # 3. Invoice Lines
        for elem in root.iter():
            if elem.tag.endswith("}InvoiceLine") or elem.tag == "InvoiceLine":
                item_code = find_text_agnostic(elem, "ID")
                # Description usually in Item -> Name
                item_name = None
                for sub in elem.iter():
                    if sub.tag.endswith("}Item") or sub.tag == "Item":
                        item_name = find_text_agnostic(sub, "Name")
                        break
                        
                quantity = find_text_agnostic(elem, "InvoicedQuantity")
                
                # Unit Price usually in Price -> PriceAmount
                unit_price = None
                for sub in elem.iter():
                    if sub.tag.endswith("}Price") or sub.tag == "Price":
                        unit_price = find_text_agnostic(sub, "PriceAmount")
                        break
                        
                total_price = find_text_agnostic(elem, "LineExtensionAmount")
                
                data["items"].append({
                    "code": item_code,
                    "description": item_name or "Unknown Item",
                    "quantity": quantity.replace('.', ',') if quantity else None,
                    "unit_price": unit_price.replace('.', ',') if unit_price else None,
                    "total_price": total_price.replace('.', ',') if total_price else None
                })
                
        # 4. Totals (LegalMonetaryTotal)
        monetary_total = None
        for elem in root.iter():
            if elem.tag.endswith("}LegalMonetaryTotal") or elem.tag == "LegalMonetaryTotal":
                monetary_total = elem
                break
                
        if monetary_total is not None:
            subt = find_text_agnostic(monetary_total, "LineExtensionAmount")
            data["subtotal"] = subt.replace('.', ',') if subt else None
            
            tax_amt = find_text_agnostic(monetary_total, "TaxExclusiveAmount") 
            data["tax_amount"] = tax_amt.replace('.', ',') if tax_amt else None
            
            # In some UBL structures, tax amount might just be calculated or inside TaxTotal
            tot = find_text_agnostic(monetary_total, "PayableAmount")
            data["total_amount"] = tot.replace('.', ',') if tot else None
            
        # Fallback for tax amount if not in LegalMonetaryTotal
        if not data["tax_amount"]:
            tax_total = None
            for elem in root.iter():
                if elem.tag.endswith("}TaxTotal") or elem.tag == "TaxTotal":
                    tax_total = elem
                    break
            if tax_total is not None:
                tax_amt2 = find_text_agnostic(tax_total, "TaxAmount")
                data["tax_amount"] = tax_amt2.replace('.', ',') if tax_amt2 else None

        print("Successfully read XML file.")
        return data
        
    except Exception as e:
        print(f"Error parsing XML file {file_path}: {e}")
        return {}
