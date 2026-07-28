import pdfplumber
import sys

pdf_path = r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\media__1784899911232.pdf"
# I don't know the exact PDF name for this 403,35 TL invoice. 
# But let's look for it in the uploaded files.
import glob
pdfs = glob.glob(r"C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\.user_uploaded\*.pdf")
print("Found PDFs:", pdfs)
