import os

with open("integrators/uyumsoft_api.py", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''    # E-Fatura kuralları gereği 7 günden eski veya geçmiş yıllara ait fatura kesilmemelidir.
    current_year = datetime.now().year
    if int(issue_date[:4]) < current_year:
        raise ValueError("Geçmiş yıla ait bir faturayı canlı ortama gönderemezsiniz. Lütfen tarihi kontrol edin.")'''

original = '''    # E-Fatura kuralları gereği geçmiş yıllara ait fatura kesilemez.
    # Uyumsoft'un "varsayılan seri bilgisi bulunamadı" hatasını önlemek için 
    # eski yıllara ait faturaların tarihini bugüne eşitliyoruz.
    current_year = datetime.now().year
    if int(issue_date[:4]) < current_year:
        issue_date = datetime.now().date().isoformat()'''

if original in text:
    text = text.replace(original, replacement)
else:
    print("Could not find the original block in uyumsoft_api.py")

with open("integrators/uyumsoft_api.py", "w", encoding="utf-8") as f:
    f.write(text)
