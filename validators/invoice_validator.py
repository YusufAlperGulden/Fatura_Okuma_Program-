def parse_amount(amount_str):
    if not amount_str:
        return 0.0
    # Remove thousand separators (.) and replace decimal separator (,) with (.)
    amount_str = str(amount_str).replace('.', '').replace(',', '.')
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
