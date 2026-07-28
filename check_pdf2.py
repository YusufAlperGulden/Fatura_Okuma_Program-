import glob
import pdfplumber

pdfs = glob.glob(r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\*.pdf")
for pdf_path in pdfs:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            if "403,35" in text:
                print("FOUND IN:", pdf_path)
                print(text)
                print("-" * 80)
    except Exception as e:
        print("Error reading", pdf_path, e)
