import os

with open("integrators/uyumsoft_api.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''def send_invoice_to_uyumsoft(
    invoice_data: dict[str, Any],
    action: str | None = None,
) -> dict[str, Any]:
    if not isinstance(invoice_data, dict):
        return {
            "success": False,
            "message": "Invoice payload must be an object.",
            "details": "A JSON object is required.",
            "response_code": 400,
        }

    # Only use server environment and credentials
    server_environment = normalize_uyumsoft_environment()
    username, password = _server_credentials(server_environment)

    if not username or not password:'''

original = '''def send_invoice_to_uyumsoft(
    invoice_data: dict[str, Any],
    action: str | None = None,
    environment: str | None = None,
    prod_username: str | None = None,
    prod_password: str | None = None,
) -> dict[str, Any]:
    if not isinstance(invoice_data, dict):
        return {
            "success": False,
            "message": "Invoice payload must be an object.",
            "details": "A JSON object is required.",
            "response_code": 400,
        }

    # Use provided arguments if available (e.g. from frontend configuration),
    # otherwise fall back to the server's deployment configuration.
    server_environment = environment.lower() if environment else normalize_uyumsoft_environment()
    
    env_username, env_password = _server_credentials(server_environment)
    username = prod_username if prod_username else env_username
    password = prod_password if prod_password else env_password

    if not username or not password:'''

if original in text:
    text = text.replace(original, replacement)
else:
    print("Could not find the original block in uyumsoft_api.py")

with open("integrators/uyumsoft_api.py", "w", encoding="utf-8") as f:
    f.write(text)
