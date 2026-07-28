import os

with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace('''class ProcessResponse(BaseModel):
    filename: str
    is_valid: bool
    data: dict | None
    errors: list[str]

class SendUyumsoftRequest(BaseModel):
    invoice_data: dict
    action: str | None = None

DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024

    pass''', '''class ProcessResponse(BaseModel):
    filename: str
    is_valid: bool
    data: dict | None
    errors: list[str]

class SendUyumsoftRequest(BaseModel):
    invoice_data: dict
    action: str | None = None

DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024

class _UploadTooLargeError(Exception):
    pass''')

with open("api.py", "w", encoding="utf-8") as f:
    f.write(text)
