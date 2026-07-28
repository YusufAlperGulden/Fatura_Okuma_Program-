import json
import asyncio
from fastapi import UploadFile
from api import _process_upload

class DummyUploadFile:
    def __init__(self, filename, content):
        self.filename = filename
        self.file = type("dummy_file", (), {"read": lambda self: content, "close": lambda self: None})()

pdf_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1785232493621.pdf"
with open(pdf_path, 'rb') as f:
    content = f.read()

dummy = DummyUploadFile("media__1785232493621.pdf", content)

async def main():
    resp = _process_upload(dummy)
    if hasattr(resp, "body"):
        print(resp.body.decode('utf-8'))
    else:
        print("Currency:", resp.data.get("currency"))
        print("Genel Toplam:", resp.data.get("total_amount"))
        print("Notes:", resp.data.get("notes")[:200] if resp.data.get("notes") else None)

asyncio.run(main())
