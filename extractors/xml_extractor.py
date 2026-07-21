import defusedxml.ElementTree as ET
from decimal import Decimal, InvalidOperation

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


def _clean_text(value):
    if value is None:
        return None
    value = value.strip()
    return value or None


def _decimal_or_none(value):
    value = _clean_text(value)
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _local_name(element):
    return element.tag.rsplit("}", 1)[-1]


def _money_text(value):
    if value is None:
        return None
    return f"{value.quantize(Decimal('0.01')):.2f}".replace(".", ",")


def _unit_price_text(value):
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.00000001"))
    text = format(rounded, "f").rstrip("0").rstrip(".")
    if "." not in text:
        text += ".00"
    elif len(text.rsplit(".", 1)[1]) == 1:
        text += "0"
    return text.replace(".", ",")


def _customer_tax_identifier(customer_party):
    """Choose a tax identifier, never an unrelated MERSIS/registry ID."""
    preferred = {}
    fallback = []
    for identification in customer_party.iter():
        if _local_name(identification) != "PartyIdentification":
            continue
        identifier = next(
            (
                child
                for child in list(identification)
                if _local_name(child) == "ID" and _clean_text(child.text)
            ),
            None,
        )
        if identifier is None:
            continue

        value = identifier.text.strip()
        scheme = str(
            identifier.attrib.get("schemeID")
            or identification.attrib.get("schemeID")
            or ""
        ).upper().replace("-", "").replace("_", "")
        if scheme in {"VKN", "VERGINO", "VERGINUMARASI"}:
            preferred["VKN"] = value
        elif scheme in {"TCKN", "TC", "TCKIMLIKNO", "TCKIMLIKNUMARASI"}:
            preferred["TCKN"] = value
        elif "MERSIS" not in scheme and value.isdigit() and len(value) in {10, 11}:
            fallback.append(value)

    return preferred.get("VKN") or preferred.get("TCKN") or (
        fallback[0] if fallback else None
    )


def _direct_allowance_total(parent):
    total = Decimal("0")
    for allowance in list(parent):
        if _local_name(allowance) != "AllowanceCharge":
            continue
        charge_indicator = child_text_agnostic(allowance, "ChargeIndicator")
        if str(charge_indicator or "").strip().lower() not in {"false", "0"}:
            continue
        amount = _decimal_or_none(child_text_agnostic(allowance, "Amount"))
        if amount is not None:
            total += amount
    return total


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
            party_id = _customer_tax_identifier(customer_party)
            if party_id:
                data["customer_tax_id"] = party_id

            customer_name = find_text_agnostic(customer_party, "RegistrationName")
            if not customer_name:
                for elem in customer_party.iter():
                    if elem.tag.endswith("}PartyName") or elem.tag == "PartyName":
                        customer_name = find_text_agnostic(elem, "Name")
                        break
            if not customer_name:
                person = next(
                    (
                        elem
                        for elem in customer_party.iter()
                        if elem.tag.endswith("}Person") or elem.tag == "Person"
                    ),
                    None,
                )
                first_name = (
                    child_text_agnostic(person, "FirstName")
                    if person is not None
                    else None
                )
                family_name = (
                    child_text_agnostic(person, "FamilyName")
                    if person is not None
                    else None
                )
                customer_name = " ".join(
                    part.strip()
                    for part in (first_name, family_name)
                    if part and part.strip()
                ) or None
            if customer_name:
                customer_name = customer_name.strip()
                data["customer_name"] = customer_name
                data["customer_title"] = customer_name
                
        # 3. Invoice Lines
        has_line_allowance = False
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
                # InvoiceLine/ID is the line sequence number, not a product
                # code.  A missing item identification must stay missing.
                item_name = None
                item_element = None
                for sub in elem.iter():
                    if sub.tag.endswith("}Item") or sub.tag == "Item":
                        item_element = sub
                        item_name = (
                            child_text_agnostic(sub, "Name")
                            or child_text_agnostic(sub, "Description")
                        )
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
                line_discount = _direct_allowance_total(elem)
                if line_discount > 0:
                    has_line_allowance = True

                # UBL PriceAmount is commonly the gross unit price while
                # LineExtensionAmount is net of a line-level AllowanceCharge.
                # The validator's quantity x unit-price contract therefore
                # needs the effective net unit price; keep the gross value as
                # metadata so no source information is lost.
                gross_unit_price = _decimal_or_none(unit_price)
                quantity_value = _decimal_or_none(quantity)
                line_total_value = _decimal_or_none(total_price)
                effective_unit_price = gross_unit_price
                if (
                    line_discount > 0
                    and quantity_value is not None
                    and quantity_value != 0
                    and line_total_value is not None
                ):
                    effective_unit_price = line_total_value / quantity_value
                
                tax_rate = None
                for sub in elem.iter():
                    if sub.tag.endswith("}TaxTotal") or sub.tag == "TaxTotal":
                        for t_sub in sub.iter():
                            if t_sub.tag.endswith("}Percent") or t_sub.tag == "Percent":
                                tax_rate = find_text_agnostic(sub, "Percent")
                                break
                        break

                item_data = {
                    "code": item_code,
                    "description": _clean_text(item_name),
                    "serial_numbers": normalize_serial_numbers(serial_values),
                    "quantity": quantity.replace('.', ',') if quantity else None,
                    "unit_price": (
                        _unit_price_text(effective_unit_price)
                        if effective_unit_price is not None
                        else None
                    ),
                    "total_price": total_price.replace('.', ',') if total_price else None,
                    # None means the source XML did not provide a line-level
                    # rate.  It must not be confused with an explicit 0% KDV.
                    "tax_rate": tax_rate.replace('.', ',') if tax_rate else None
                }
                if line_discount > 0:
                    item_data["gross_unit_price"] = _unit_price_text(gross_unit_price)
                    item_data["discount_amount"] = _money_text(line_discount)
                data["items"].append(item_data)
                
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

            # Line allowances are already reflected in each
            # LineExtensionAmount and must not be subtracted from the document
            # subtotal a second time. When line allowances exist, only direct
            # Invoice/AllowanceCharge elements are document-level discounts.
            document_discount = _direct_allowance_total(root)
            if has_line_allowance:
                data["discount_amount"] = _money_text(document_discount)
            elif document_discount > 0:
                data["discount_amount"] = _money_text(document_discount)
            else:
                # Preserve the source representation for legacy XMLs that
                # expose only LegalMonetaryTotal/AllowanceTotalAmount.
                data["discount_amount"] = (
                    discount.replace(".", ",") if discount else None
                )

            tot = (
                child_text_agnostic(monetary_total, "PayableAmount")
                or child_text_agnostic(monetary_total, "TaxInclusiveAmount")
            )
            data["total_amount"] = tot.replace('.', ',') if tot else None

            tax_exclusive = child_text_agnostic(
                monetary_total, "TaxExclusiveAmount"
            )
            tax_inclusive = child_text_agnostic(
                monetary_total, "TaxInclusiveAmount"
            )
            charge = child_text_agnostic(monetary_total, "ChargeTotalAmount")
        else:
            tax_exclusive = None
            tax_inclusive = None
            charge = None
            discount = None

        tax_total = None
        for elem in root.iter():
            if elem.tag.endswith("}TaxTotal") or elem.tag == "TaxTotal":
                tax_total = elem
                break
        if tax_total is not None:
            tax_amt = child_text_agnostic(tax_total, "TaxAmount") or find_text_agnostic(tax_total, "TaxAmount")
            data["tax_amount"] = tax_amt.replace('.', ',') if tax_amt else data["tax_amount"]

        if not data["tax_amount"]:
            inclusive_value = _decimal_or_none(tax_inclusive)
            exclusive_value = _decimal_or_none(tax_exclusive)

            if inclusive_value is not None and exclusive_value is not None:
                calculated_tax = inclusive_value - exclusive_value
            else:
                total_value = _decimal_or_none(
                    data["total_amount"].replace(",", ".")
                    if data["total_amount"]
                    else None
                )
                subtotal_value = _decimal_or_none(
                    data["subtotal"].replace(",", ".")
                    if data["subtotal"]
                    else None
                )
                discount_value = _decimal_or_none(
                    str(data.get("discount_amount") or "0").replace(",", ".")
                ) or Decimal("0")
                charge_value = _decimal_or_none(charge) or Decimal("0")
                calculated_tax = (
                    total_value
                    - (subtotal_value - discount_value + charge_value)
                    if total_value is not None and subtotal_value is not None
                    else None
                )

            if calculated_tax is not None:
                data["tax_amount"] = f"{calculated_tax:.2f}".replace(".", ",")

        print("Successfully read XML file.")
        return data
        
    except Exception as e:
        print(f"Error parsing XML file {file_path}: {e}")
        return {}
