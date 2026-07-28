import pandas as pd
import os

from utils.serial_numbers import (
    format_customer_postal_address,
    normalize_customer_postal_address,
    normalize_serial_numbers,
)


def _address_export_fields(invoice):
    raw_address = invoice.get("customer_address")
    postal_address = normalize_customer_postal_address(
        invoice.get("customer_postal_address")
        or (raw_address if isinstance(raw_address, dict) else None)
    )
    if isinstance(raw_address, str):
        raw_address = raw_address.strip()
    else:
        raw_address = format_customer_postal_address(
            postal_address or raw_address
        )
    if not raw_address:
        raw_address = format_customer_postal_address(postal_address)

    return {
        "Müşteri Adresi": raw_address,
        "Cadde/Sokak Adı": postal_address.get("street_name", ""),
        "Bina Adı": postal_address.get("building_name", ""),
        "Bina No": postal_address.get("building_number", ""),
        "İlçe": postal_address.get("city_subdivision_name", ""),
        "İl": postal_address.get("city_name", ""),
        "Posta Kodu": postal_address.get("postal_zone", ""),
        "Mahalle": postal_address.get("district", ""),
        "Ülke Kodu": postal_address.get("country_code", ""),
        "Ülke Adı": postal_address.get("country_name", ""),
        "Adres Satırları": "|".join(
            postal_address.get("address_lines", [])
        ),
    }

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
                "Müşteri Adı": invoice.get("customer_title") or invoice.get("customer_name"),
                "Ürün Kodu": item.get("code"),
                "Ürün Açıklaması": item.get("description"),
                "Seri Numaraları": "~".join(
                    normalize_serial_numbers(item.get("serial_numbers"))
                ),
                "Miktar": item.get("quantity"),
                "Birim Fiyat": item.get("unit_price"),
                "Satır Toplamı": item.get("total_price"),
                "Fatura Ara Toplam": invoice.get("subtotal"),
                "Fatura KDV": invoice.get("tax_amount"),
                "Fatura Genel Toplam": invoice.get("total_amount"),
                **_address_export_fields(invoice),
            }
            rows.append(row)
            
    df = pd.DataFrame(rows)
    
    # If the file exists, we could append to it, but for now we overwrite/create new
    df.to_excel(output_path, index=False)
    print(f"Exported {len(rows)} lines to {output_path} successfully.")
    return output_path
