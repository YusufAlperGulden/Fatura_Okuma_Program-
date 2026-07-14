import sys
import os

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
except ImportError:
    print("reportlab not installed, skipping PDF generation")
    sys.exit(0)

c = canvas.Canvas("test_invoice_fixture.pdf", pagesize=A4)
width, height = A4

# Top Left: Sender Info
c.drawString(50, height - 50, "Gönderici: ABC LTD")
c.drawString(50, height - 70, "Adres: Test Mahallesi")

# Top Right: Invoice Info
# This should fall within the top 40% and right 50%
c.drawString(width - 200, height - 50, "Fatura Tarihi: 15.07.2026")
c.drawString(width - 200, height - 70, "Fatura Seri No: TOPRIGHT99")

# Middle/Bottom: Product Table (this falls below the top 40%)
c.drawString(50, height - 300, "Parça Listesi")
c.drawString(50, height - 320, "Ürün Kodu   Açıklama   Miktar   Fiyat")
c.drawString(50, height - 340, "1234.567    Yazıcı Seri No: BOTTOMLFT11   1   Adet   150,00   20%   180,00")

c.save()
print("test_invoice_fixture.pdf generated successfully")
