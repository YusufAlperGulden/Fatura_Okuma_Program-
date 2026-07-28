import os

with open("api.py", "r", encoding="utf-8") as f:
    text = f.read()

# Add Header and HTTPException to fastapi imports
if "from fastapi import FastAPI" in text:
    text = text.replace("from fastapi import FastAPI, UploadFile, File", "from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends")

# Add verify_app_password function
auth_code = '''
def verify_app_password(x_app_password: str | None = Header(None)):
    expected_password = os.environ.get("APP_PASSWORD")
    if expected_password and x_app_password != expected_password:
        raise HTTPException(status_code=401, detail="Geçersiz Uygulama Şifresi (APP_PASSWORD)")
'''

if "app = FastAPI" in text:
    text = text.replace('app = FastAPI(title="Invoice Pipeline API")', 'app = FastAPI(title="Invoice Pipeline API")\n' + auth_code)

# Add Depends to endpoints
# @app.post("/process")
text = text.replace('@app.post("/process")', '@app.post("/process", dependencies=[Depends(verify_app_password)])')
# @app.post("/send-uyumsoft")
text = text.replace('@app.post("/send-uyumsoft")', '@app.post("/send-uyumsoft", dependencies=[Depends(verify_app_password)])')
# @app.get("/history")
text = text.replace('@app.get("/history")', '@app.get("/history", dependencies=[Depends(verify_app_password)])')
# @app.post("/invoices/status")
text = text.replace('@app.post("/invoices/status")', '@app.post("/invoices/status", dependencies=[Depends(verify_app_password)])')
# @app.get("/invoices/recent")
text = text.replace('@app.get("/invoices/recent")', '@app.get("/invoices/recent", dependencies=[Depends(verify_app_password)])')


with open("api.py", "w", encoding="utf-8") as f:
    f.write(text)
