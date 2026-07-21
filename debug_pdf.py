import pdfplumber
import sys

file_path = r"C:\Users\tps\.gemini\antigravity\brain\54e8d961-b90a-49e2-8855-ecf3c45c0759\media__1783605515307.pdf"

with pdfplumber.open(file_path) as pdf:
    for i, page in enumerate(pdf.pages):
        print(f"--- PAGE {i} PLAIN TEXT ---")
        print(page.extract_text())
        print(f"\n--- PAGE {i} LAYOUT TEXT ---")
        print(page.extract_text(layout=True))
