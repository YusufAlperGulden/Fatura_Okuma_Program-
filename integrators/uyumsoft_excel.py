import pandas as pd
import os

def export_to_uyumsoft_excel(valid_invoices, output_path="Uyumsoft_Aktarim_Taslagi.xlsx"):
    """
    Takes a list of valid invoice data dictionaries and exports them to an Excel file
    formatted for Uyumsoft bulk import.
    """
    rows = []
    for invoice in valid_invoices:
        for item in invoice.get("items", []):
            row = {
                "Fatura Tarihi": invoice.get("date"),
                "Müşteri VKN/TCKN": invoice.get("customer_tax_id"),
                "Ürün Kodu": item.get("code"),
                "Ürün Açıklaması": item.get("description"),
                "Miktar": item.get("quantity"),
                "Birim Fiyat": item.get("unit_price"),
                "Satır Toplamı": item.get("total_price"),
                "Fatura Ara Toplam": invoice.get("subtotal"),
                "Fatura KDV": invoice.get("tax_amount"),
                "Fatura Genel Toplam": invoice.get("total_amount")
            }
            rows.append(row)
            
    df = pd.DataFrame(rows)
    
    # If the file exists, we could append to it, but for now we overwrite/create new
    df.to_excel(output_path, index=False)
    print(f"Exported {len(rows)} lines to {output_path} successfully.")
    return output_path
