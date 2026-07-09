def parse_amount(amount_str):
    if not amount_str:
        return 0.0
    if isinstance(amount_str, (int, float)):
        return float(amount_str)

    # Remove currency symbols and text
    amount_str = str(amount_str).strip().upper()
    for currency in ["₺", "TL", "TRY", "$", "USD", "DOLAR", "€", "EUR", "EURO", "£", "GBP"]:
        amount_str = amount_str.replace(currency, "")
    amount_str = amount_str.strip()

    if not amount_str:
        return 0.0

    # Handle decimal and thousand separators intelligently
    if "," in amount_str and "." in amount_str:
        # Example: 1.250,00 (TR) -> last separator is ,
        # Example: 1,250.00 (US) -> last separator is .
        if amount_str.rfind(",") > amount_str.rfind("."):
            amount_str = amount_str.replace(".", "").replace(",", ".")
        else:
            amount_str = amount_str.replace(",", "")
    elif "," in amount_str:
        # Check if comma is used as thousand separator without decimal (e.g., 1,250) or as decimal (1250,00)
        parts = amount_str.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            # It's a decimal separator like 1250,50
            amount_str = amount_str.replace(",", ".")
        elif len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            # It's a thousand separator like 1,250
            amount_str = amount_str.replace(",", "")
        else:
            # Default to decimal replacement if ambiguous
            amount_str = amount_str.replace(",", ".")
    elif "." in amount_str:
        # Check if dot is used as thousand separator without decimal (e.g., 1.250) or as decimal (1250.00)
        parts = amount_str.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            amount_str = amount_str.replace(".", "")

    try:
        return float(amount_str)
    except ValueError:
        return 0.0

def validate_invoice(data):
    """
    Validates the mathematical correctness of an extracted invoice.
    Returns (is_valid, list_of_errors)
    """
    errors = []
    
    # Check mandatory fields
    if not data.get("date"):
        errors.append("Missing date.")
    if not data.get("customer_tax_id"):
        errors.append("Missing customer_tax_id.")
    if not data.get("items"):
        errors.append("No items found.")
        
    # Mathematical validation
    calculated_subtotal = 0.0
    
    for item in data.get("items", []):
        quantity = parse_amount(item.get("quantity"))
        unit_price = parse_amount(item.get("unit_price"))
        total_price = parse_amount(item.get("total_price"))
        
        calculated_subtotal += total_price
        
        # Check item math (Quantity * Unit Price == Total Price)
        # Using a small epsilon for floating point errors
        if abs((quantity * unit_price) - total_price) > 0.05:
            # Auto-correction heuristic: PDF extraction often reads Product Codes as Unit Price due to column misalignment.
            # If quantity and total_price are > 0, we can safely derive the true unit_price.
            if quantity > 0 and total_price > 0:
                corrected_unit_price = round(total_price / quantity, 6)
                item["unit_price"] = str(corrected_unit_price) # Auto-fix the data
            else:
                errors.append(f"Item math error: {item.get('description')} ({quantity} * {unit_price} != {total_price})")

    subtotal = parse_amount(data.get("subtotal"))
    tax_amount = parse_amount(data.get("tax_amount"))
    total_amount = parse_amount(data.get("total_amount"))
    
    # Check subtotal against item totals
    if abs(calculated_subtotal - subtotal) > 0.05:
         errors.append(f"Subtotal mismatch: Items sum ({calculated_subtotal}) != Subtotal ({subtotal})")
         
    # Check total == subtotal + tax
    if abs((subtotal + tax_amount) - total_amount) > 0.05:
         errors.append(f"Total mismatch: {subtotal} + {tax_amount} != {total_amount}")
         
    is_valid = len(errors) == 0

    # NORMALIZE FORMATTING FOR UI CONSISTENCY
    # Ensure date is always DD.MM.YYYY
    raw_date = data.get("date", "").strip()
    if raw_date:
        import datetime
        for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.datetime.strptime(raw_date, fmt)
                data["date"] = parsed.strftime("%d.%m.%Y")
                break
            except ValueError:
                pass
                
    # Function to format float to TR currency string (400.0 -> "400,00")
    def format_tr_money(val: float) -> str:
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    if is_valid or not is_valid: # Apply formatting even if invalid
        if data.get("subtotal"): data["subtotal"] = format_tr_money(subtotal)
        if data.get("tax_amount"): data["tax_amount"] = format_tr_money(tax_amount)
        if data.get("total_amount"): data["total_amount"] = format_tr_money(total_amount)
        
        for item in data.get("items", []):
            q = parse_amount(item.get("quantity"))
            up = parse_amount(item.get("unit_price"))
            tp = parse_amount(item.get("total_price"))
            item["quantity"] = str(q).replace(".", ",") if str(q).endswith(".0") else str(q).replace(".", ",")
            item["unit_price"] = format_tr_money(up)
            item["total_price"] = format_tr_money(tp)

    return is_valid, errors
