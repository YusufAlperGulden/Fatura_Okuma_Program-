import re

import pdfplumber


CURRENCY_SYMBOLS = "₺$€£"
AMOUNT_NUMBER_RE = r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2}"
MONEY_RE = rf"(?:[{CURRENCY_SYMBOLS}][ \t]*)?({AMOUNT_NUMBER_RE})(?:[ \t]*(?:TL|TRY|USD|EUR|GBP|DOLAR|EURO|[{CURRENCY_SYMBOLS}]))?"
MONEY_TOKEN_RE = rf"(?:[{CURRENCY_SYMBOLS}][ \t]*)?{AMOUNT_NUMBER_RE}(?:[ \t]*(?:TL|TRY|USD|EUR|GBP|DOLAR|EURO|[{CURRENCY_SYMBOLS}]))?"
UNIT_RE = r"Adet|AdeTt|Kg|Lt|Paket|Pak|Kutu|Ay|Yıl|Yil|Ad\.|M2|M3|Saat|Hizmet|Gün|Gun"
WATERMARK_CHARS = "A-ZÇĞİÖŞÜ"


def _first_match(patterns, text, flags=0):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def _parse_money_number(value):
    if value is None or value == "":
        return 0.0

    text = str(value).strip().upper()
    for token in ["₺", "TL", "TRY", "$", "USD", "DOLAR", "€", "EUR", "EURO", "£", "GBP", "%"]:
        text = text.replace(token, "")
    text = text.replace(" ", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            text = text.replace(".", "")

    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_amount(value):
    return f"{value:.2f}".replace(".", ",")


def _clean_pdf_line(line):
    line = line.replace("\xa0", " ")
    line = re.sub(r"\bAdeTt\b", "Adet", line)

    # Vertical watermark letters sometimes land inside codes, units, or amounts.
    line = re.sub(rf"(\d{{4}})[{WATERMARK_CHARS}]\.(\d{{3}})", r"\1.\2", line)
    line = re.sub(rf"(\d{{4}}\.\d{{3}})[{WATERMARK_CHARS}](?=[A-Za-zÇĞİÖŞÜçğıöşü])", r"\1 ", line)
    line = re.sub(rf"(?<=\s)[{WATERMARK_CHARS}]+([{re.escape(CURRENCY_SYMBOLS)}])(?=\d)", r"\1", line)
    line = re.sub(rf"([{re.escape(CURRENCY_SYMBOLS)}])[ \t]*[{WATERMARK_CHARS}]+[ \t]*(?=\d)", r"\1", line)
    line = re.sub(rf"([.,])[ \t]*[{WATERMARK_CHARS}]+[ \t]*(?=\d{{2,3}}\b)", r"\1", line)
    line = re.sub(
        rf"(%[ \t]*\d+(?:[.,]\d+)?)[ \t]*[{WATERMARK_CHARS}]+[ \t]*([{re.escape(CURRENCY_SYMBOLS)}])",
        r"\1 \2",
        line,
    )
    line = re.sub(rf"(?<=\s)[{WATERMARK_CHARS}]+({UNIT_RE})\b", r"\1", line, flags=re.IGNORECASE)
    line = re.sub(rf"(\d+(?:[.,]\d+)?)[ \t]*[{WATERMARK_CHARS}]+({UNIT_RE})\b", r"\1 \2", line, flags=re.IGNORECASE)
    line = re.sub(
        rf"(?<=\s)[{WATERMARK_CHARS}]+(\d+(?:[.,]\d+)?)[ \t]+({UNIT_RE})\b",
        r"\1 \2",
        line,
        flags=re.IGNORECASE,
    )
    return line


def _normalize_extracted_text(text):
    cleaned = "\n".join(_clean_pdf_line(line) for line in text.splitlines())
    return re.sub(r"(?i)\b(?:ÖRNEKTİR|RESMİ FATURA DEĞİLDİR|ARA FATURASI)\b", "", cleaned)


def _find_items(text):
    item_line_pattern = re.compile(
        rf"^[ \t]*(?P<code>(?:\d{{4}}\.\d{{3}}|[A-Z]{{2,4}}-\d{{3}}|[-\w][\w.-]*))[ \t]+"
        rf"(?P<description>.+?)[ \t]+"
        rf"(?P<quantity>\d+(?:[.,]\d+)?)[ \t]+"
        rf"(?:(?P<unit>{UNIT_RE})[ \t]+)?"
        rf"(?P<unit_price>{MONEY_TOKEN_RE})[ \t]+"
        rf"(?:%?[ \t]*(?P<tax_rate>\d+(?:[.,]\d+)?)[ \t]+)?"
        rf"(?P<total_price>{MONEY_TOKEN_RE})[ \t]*$",
        re.IGNORECASE,
    )

    code_start_pattern = re.compile(r"(?=(?:\d{4}\.\d{3}|[A-Z]{2,4}-\d{3})[ \t]+)")

    def split_repeated_item_line(line):
        starts = [match.start() for match in code_start_pattern.finditer(line)]
        if len(starts) <= 1:
            return [line]

        segments = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(line)
            segment = line[start:end].strip()
            if segment:
                segments.append(segment)
        return segments

    items = []
    seen = set()
    for raw_line in text.splitlines():
        line = _clean_pdf_line(raw_line).strip()
        for segment in split_repeated_item_line(line):
            match = item_line_pattern.match(segment)
            if not match:
                continue

            item = {
                "code": match.group("code"),
                "description": re.sub(r"\s+", " ", match.group("description")).strip(),
                "quantity": match.group("quantity").replace(".", ","),
                "unit_price": _format_amount(_parse_money_number(match.group("unit_price"))),
                "tax_rate": match.group("tax_rate"),
                "total_price": _format_amount(_parse_money_number(match.group("total_price"))),
            }
            key = (item["code"], item["description"], item["quantity"], item["unit_price"], item["total_price"])
            if key not in seen:
                seen.add(key)
                items.append(item)

    return items


def _sum_tax_lines(text):
    total = 0.0
    found = False
    for line in text.splitlines():
        if "KDV" not in line.upper():
            continue
        matches = list(re.finditer(MONEY_RE, line, re.IGNORECASE))
        if not matches:
            continue
        found = True
        total += _parse_money_number(matches[-1].group(1))

    return _format_amount(total) if found else None


def _items_subtotal(data):
    return sum(_parse_money_number(item.get("total_price")) for item in data.get("items", []))


def _score_data(data):
    subtotal = _parse_money_number(data.get("subtotal"))
    discount = _parse_money_number(data.get("discount_amount"))
    item_sum = _items_subtotal(data)
    subtotal_gap = min(abs(item_sum - subtotal), abs((item_sum - discount) - subtotal))

    score = len(data.get("items", [])) * 10
    if subtotal and subtotal_gap <= 0.05:
        score += 1000
    elif subtotal:
        score -= min(subtotal_gap, 100000) / 1000
    return score


def parse_invoice_text(text: str) -> dict:
    text = _normalize_extracted_text(text)
    data = {
        "invoice_no": None,
        "date": None,
        "customer_tax_id": None,
        "items": [],
        "subtotal": None,
        "discount_amount": 0.0,
        "tax_amount": None,
        "total_amount": None,
        "currency": "TRY",
    }

    usd_matches = len(re.findall(r"\$[ \t]*\d|\d+(?:[.,]\d+)?[ \t]*(?:USD|DOLAR)", text, re.IGNORECASE))
    eur_matches = len(re.findall(r"€[ \t]*\d|\d+(?:[.,]\d+)?[ \t]*(?:EUR|EURO)", text, re.IGNORECASE))
    gbp_matches = len(re.findall(r"£[ \t]*\d|\d+(?:[.,]\d+)?[ \t]*GBP", text, re.IGNORECASE))
    try_matches = len(re.findall(r"₺[ \t]*\d|\d+(?:[.,]\d+)?[ \t]*(?:TL|TRY)", text, re.IGNORECASE))

    if usd_matches > try_matches and usd_matches > eur_matches and usd_matches > gbp_matches:
        data["currency"] = "USD"
    elif eur_matches > try_matches and eur_matches > usd_matches and eur_matches > gbp_matches:
        data["currency"] = "EUR"
    elif gbp_matches > try_matches and gbp_matches > usd_matches and gbp_matches > eur_matches:
        data["currency"] = "GBP"

    data["invoice_no"] = _first_match(
        [
            r"(?:Fatura|Belge|Invoice)[ \t]*(?:No|Numarası|Numarasi|Number)?[ \t]*[:#-][ \t]*([A-Z0-9-]+)",
            r"\b([A-Z]{3}\d{13})\b",
        ],
        text,
        re.IGNORECASE,
    )
    data["date"] = _first_match([r"\b(\d{1,2}\.\d{2}\.\d{4})\b"], text)
    data["customer_tax_id"] = _first_match(
        [
            r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi[ \t]*No)[ \t]*[:#-]?[ \t]*(\d{10,11})\b",
            r"\b(\d{10,11})\b",
        ],
        text,
        re.IGNORECASE,
    )

    data["items"] = _find_items(text)
    data["subtotal"] = _first_match([rf"Ara\s*Toplam\s+{MONEY_RE}"], text, re.IGNORECASE)
    data["discount_amount"] = (
        _first_match([rf"(?:İskonto|İndirim|Discount).*?{MONEY_RE}"], text, re.IGNORECASE) or 0.0
    )
    data["tax_amount"] = _sum_tax_lines(text)
    data["total_amount"] = _first_match(
        [
            rf"Yekün.*?{MONEY_RE}",
            rf"Döviz\s*Toplam\s*:?\s*{MONEY_RE}",
            rf"FATURA\s+BEDELİ\s+{MONEY_RE}",
            rf"Genel\s*Toplam\s+{MONEY_RE}",
            rf"Ödenecek\s*Tutar\s+{MONEY_RE}",
        ],
        text,
        re.IGNORECASE,
    )

    return data


def parse_pdf_invoice(file_path: str) -> dict:
    """
    Parses a digital PDF invoice using pdfplumber and regex.
    """
    print(f"Parsing PDF invoice: {file_path}")

    try:
        with pdfplumber.open(file_path) as pdf:
            plain_text = ""
            layout_text = ""
            for page in pdf.pages:
                plain_extracted = page.extract_text()
                layout_extracted = page.extract_text(layout=True)
                if plain_extracted:
                    plain_text += plain_extracted + "\n"
                if layout_extracted:
                    layout_text += layout_extracted + "\n"

            candidate_texts = [text.strip() for text in (plain_text, layout_text) if text and text.strip()]
            if not candidate_texts:
                print("No selectable text found via pdfplumber. Falling back to OCR...")
                from extractors.ocr_extractor import parse_pdf_invoice_ocr

                return parse_pdf_invoice_ocr(file_path)

            candidates = []
            for text in candidate_texts:
                parsed = parse_invoice_text(text)
                parsed["_raw_text"] = text
                candidates.append(parsed)
            data = max(candidates, key=_score_data)

        if not data["items"]:
            print("PDF text was read, but line items were not matched. Falling back to OCR...")
            from extractors.ocr_extractor import parse_pdf_invoice_ocr

            return parse_pdf_invoice_ocr(file_path)

        print("Successfully read PDF file.")
        return data

    except Exception as e:
        print(f"Error parsing PDF file {file_path}: {e}")
        return {}
