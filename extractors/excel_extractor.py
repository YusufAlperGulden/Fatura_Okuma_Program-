import os
import unicodedata

import pandas as pd

from utils.serial_numbers import normalize_serial_numbers


def _normalize_header(value):
    text = "" if value is None else str(value)
    text = text.translate(str.maketrans({
        "ç": "c", "Ç": "C",
        "ğ": "g", "Ğ": "G",
        "ı": "i", "I": "I",
        "İ": "I",
        "ö": "o", "Ö": "O",
        "ş": "s", "Ş": "S",
        "ü": "u", "Ü": "U",
    }))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    for char in ["/", "\\", "-", "_", "(", ")", "%"]:
        text = text.replace(char, " ")
    return " ".join(text.split())


def _first_present(row, columns):
    for column in columns:
        if column in row and not pd.isna(row[column]) and row[column] != "":
            return row[column]
    return None


def _as_text(value):
    if value is None or pd.isna(value):
        return None
    return str(value).strip()


def _normalize_currency_value(value):
    text = _as_text(value)
    if not text:
        return None

    normalized = _normalize_header(text)
    mapping = {
        "tl": "TRY",
        "try": "TRY",
        "turk lirasi": "TRY",
        "usd": "USD",
        "dolar": "USD",
        "amerikan dolari": "USD",
        "eur": "EUR",
        "euro": "EUR",
        "gbp": "GBP",
        "sterlin": "GBP",
    }
    return mapping.get(normalized, text.upper())


def _read_table(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)


def parse_excel_invoice(file_path: str) -> dict:
    """
    Parses a Uyumsoft-style Excel/CSV invoice table.

    The current pipeline handles one invoice per upload. If the spreadsheet has
    multiple rows for the same invoice, each row is treated as one line item.
    """
    print(f"Parsing Excel invoice: {file_path}")

    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "customer_name": None,
        "customer_title": None,
        "items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None,
        "currency": "TRY",
        "exchange_rate": None,
        "discount_amount": None,
        "notes": ""
    }

    try:
        df = _read_table(file_path)
        if df.empty:
            return data

        df = df.dropna(how="all")
        df.columns = [_normalize_header(column) for column in df.columns]

        column_sets = {
            "invoice_no": ["fatura no", "belge no", "invoice no"],
            "date": ["fatura tarihi", "belge tarihi", "tarih", "date"],
            "customer_tax_id": [
                "musteri vkn tckn",
                "vkn tckn",
                "musteri vergi no",
                "customer tax id",
            ],
            "customer_name": [
                "musteri adi",
                "musteri unvan",
                "musteri unvani",
                "alici adi",
                "alici unvan",
                "customer name",
                "customer title",
            ],
            "item_code": ["urun kodu", "mal hizmet kodu", "kod", "code"],
            "item_description": [
                "urun aciklamasi",
                "urun aciklama",
                "mal hizmet adi",
                "aciklama",
                "description",
            ],
            "serial_numbers": [
                "urun seri numaralari",
                "urun seri no",
                "seri numaralari",
                "seri numarasi",
                "seri no",
                "serial numbers",
                "serial number",
                "serial no",
            ],
            "quantity": ["miktar", "quantity"],
            "unit_price": ["birim fiyat", "price", "unit price"],
            "line_total": ["satir toplami", "satir toplam", "line total"],
            "subtotal": ["fatura ara toplam", "ara toplam", "subtotal"],
            "tax_amount": ["fatura kdv", "kdv", "tax amount"],
            "total_amount": ["fatura genel toplam", "genel toplam", "total amount"],
            "currency": ["para birimi", "doviz cinsi", "doviz turu", "currency"],
            "exchange_rate": ["doviz kuru", "kur", "exchange rate"],
            "discount_amount": [
                "fatura iskonto",
                "iskonto tutari",
                "iskonto",
                "indirim",
                "discount amount",
                "discount",
            ],
            "notes": [
                "fatura notu",
                "fatura aciklamasi",
                "genel aciklama",
                "invoice note",
                "notes",
                "not",
            ],
            "tax_rate": ["kdv orani", "vergi orani", "tax rate", "vat rate"],
        }

        first = df.iloc[0]
        data["invoice_no"] = _as_text(_first_present(first, column_sets["invoice_no"]))
        data["date"] = _as_text(_first_present(first, column_sets["date"]))
        data["customer_tax_id"] = _as_text(_first_present(first, column_sets["customer_tax_id"]))
        data["customer_name"] = _as_text(_first_present(first, column_sets["customer_name"]))
        data["customer_title"] = data["customer_name"]
        data["subtotal"] = _as_text(_first_present(first, column_sets["subtotal"]))
        data["tax_amount"] = _as_text(_first_present(first, column_sets["tax_amount"]))
        data["total_amount"] = _as_text(_first_present(first, column_sets["total_amount"]))
        data["currency"] = (
            _normalize_currency_value(_first_present(first, column_sets["currency"]))
            or "TRY"
        )
        data["exchange_rate"] = _as_text(
            _first_present(first, column_sets["exchange_rate"])
        )
        data["discount_amount"] = _as_text(
            _first_present(first, column_sets["discount_amount"])
        )
        data["notes"] = _as_text(_first_present(first, column_sets["notes"])) or ""

        for _, row in df.iterrows():
            description = _as_text(_first_present(row, column_sets["item_description"]))
            quantity = _as_text(_first_present(row, column_sets["quantity"]))
            unit_price = _as_text(_first_present(row, column_sets["unit_price"]))
            line_total = _as_text(_first_present(row, column_sets["line_total"]))
            tax_rate = _as_text(_first_present(row, column_sets["tax_rate"]))

            if not any([description, quantity, unit_price, line_total]):
                continue

            data["items"].append({
                "code": _as_text(_first_present(row, column_sets["item_code"])),
                "description": description or "Unknown Item",
                "serial_numbers": normalize_serial_numbers(
                    _first_present(row, column_sets["serial_numbers"])
                ),
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": line_total,
                "tax_rate": tax_rate,
            })

        print("Successfully read Excel file.")
        return data

    except Exception as e:
        print(f"Error parsing Excel file {file_path}: {e}")
        return {}
