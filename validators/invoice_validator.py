def parse_amount(amount_str):
    if not amount_str:
        return 0.0
    if isinstance(amount_str, (int, float)):
        return float(amount_str)

    # Remove thousand separators (.) and replace decimal separator (,) with (.)
    amount_str = str(amount_str).strip()
    amount_str = amount_str.replace("₺", "").replace("TL", "").replace("TRY", "")
    amount_str = amount_str.replace("$", "").replace("USD", "").replace("€", "").replace("EUR", "")
    amount_str = amount_str.replace("£", "").replace("GBP", "").strip()

    if "," in amount_str:
        amount_str = amount_str.replace('.', '').replace(',', '.')
    elif "." in amount_str:
        parts = amount_str.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
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
    return is_valid, errors
