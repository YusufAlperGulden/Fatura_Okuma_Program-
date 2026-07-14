import re

import pdfplumber


CURRENCY_SYMBOLS = "₺$€£"
AMOUNT_NUMBER_RE = r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2}"
MONEY_RE = rf"(?:[{CURRENCY_SYMBOLS}][ \t]*)?({AMOUNT_NUMBER_RE})(?:[ \t]*(?:TL|TRY|USD|EUR|GBP|DOLAR|EURO|[{CURRENCY_SYMBOLS}]))?"
MONEY_TOKEN_RE = rf"(?:[{CURRENCY_SYMBOLS}][ \t]*)?{AMOUNT_NUMBER_RE}(?:[ \t]*(?:TL|TRY|USD|EUR|GBP|DOLAR|EURO|[{CURRENCY_SYMBOLS}]))?"
UNIT_RE = r"Adet|AdeTt|Kg|Lt|Paket|Pak|Kutu|Ay|Yıl|Yil|Ad\.|M2|M3|Saat|Hizmet|Gün|Gun"
WATERMARK_CHARS = "A-ZÇĞİÖŞÜ"


def _fix_mojibake_currency(text):
    return (
        text.replace("\u00e2\u201a\u00ba", "₺")
        .replace("\u00e2\u0082\u00ba", "₺")
        .replace("\u00e2\u201a\u00ac", "€")
        .replace("\u00e2\u0082\u00ac", "€")
        .replace("\u00c2\u00a3", "£")
    )


def _first_match(patterns, text, flags=0):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip()
    return None


def _buyer_section_lines(text):
    lines = [line.strip() for line in text.splitlines()]
    buyer_lines = []
    in_buyer_section = False

    for line in lines:
        if not line:
            continue

        if re.search(r"\b(?:Alıcı|Alici|Buyer|Customer)\b", line, re.IGNORECASE):
            in_buyer_section = True
            continue

        if in_buyer_section and re.search(
            r"^(?:Kodu|Kod\s|Mal\s*/?\s*Hizmet|Ürün|Urun|Ara\s*Toplam|Döviz\s*Kuru|Doviz\s*Kuru)\b",
            line,
            re.IGNORECASE,
        ):
            break

        if in_buyer_section:
            buyer_lines.append(line)

    return buyer_lines


def _clean_customer_name_line(line):
    line = _fix_mojibake_currency(str(line or "")).strip()
    if not line:
        return None

    line = re.split(
        r"\b(?:Ödeme|Odeme)\s*şekli\b|\bVade\b|\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi\s*No)\b|\bTahsilat\b",
        line,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" :-")

    if not line or not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", line):
        return None

    skip_patterns = [
        r"\b(?:Mah\.?|Mahallesi|Cad\.?|Caddesi|Sk\.?|Sok\.?|Sokak|Bulvar|No:|Türkiye|Turkey)\b",
        r"\b(?:Fatura|Düzenleme|Duzenleme|Vergi\s*Dairesi|Para\s*Birimi|Senaryo)\b",
    ]
    if any(re.search(pattern, line, re.IGNORECASE) for pattern in skip_patterns):
        return None

    return re.sub(r"\s+", " ", line).strip()


def _extract_customer_name(text):
    for line in _buyer_section_lines(text):
        customer_name = _clean_customer_name_line(line)
        if customer_name:
            return customer_name

    match = re.search(
        r"\b(?:Alıcı|Alici|Buyer|Customer)\b[^\n]*\n\s*([^\n]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return _clean_customer_name_line(match.group(1))

    return None


def _extract_customer_tax_id(text):
    for line in _buyer_section_lines(text):
        match = re.search(
            r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi[ \t]*No)[ \t]*[:#-]?[ \t]*(\d{10,11})\b",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)

    return _first_match(
        [
            r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi[ \t]*No)[ \t]*[:#-]?[ \t]*(\d{10,11})\b",
            r"\b(\d{10,11})\b",
        ],
        text,
        re.IGNORECASE,
    )


def _parse_money_number(value):
    if value is None or value == "":
        return 0.0

    text = _fix_mojibake_currency(str(value)).strip().upper()
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


def _extract_exchange_rate(text):
    raw_rate = _first_match(
        [
            r"(?:Döviz|Doviz|DÃ¶viz)\s*Kuru\s*[:=-]?\s*(\d+(?:[.,]\d{1,6})?)",
            r"Exchange\s*Rate\s*[:=-]?\s*(\d+(?:[.,]\d{1,6})?)",
            r"\bKur\s*[:=-]\s*(\d+(?:[.,]\d{1,6})?)",
        ],
        text,
        re.IGNORECASE,
    )
    rate = _parse_money_number(raw_rate)
    if rate <= 0:
        return None
    return f"{rate:.6f}".rstrip("0").rstrip(".")


def _extract_invoice_notes(text):
    note_header = re.compile(
        r"^(?:(?:Genel|Fatura)\s+)?(?:Açıklama(?:lar)?|Aciklama(?:lar)?|AÃ§Ä±klama(?:lar)?|Not(?:u|lar)?)"
        r"\s*(?:(?::|-)\s*(.*))?$",
        re.IGNORECASE,
    )
    section_stop = re.compile(
        r"^(?:Kodu\b|Kod\s|Mal\s*/?\s*Hizmet|Ürün\b|Urun\b|Ara\s*Toplam\b|"
        r"K\.?D\.?V\.?\b|Genel\s*Toplam\b|Yek(?:un|ün)\b|(?:Ödenecek|Odenecek)\s*Tutar\b|"
        r"(?:Satıcı|Satici|Alıcı|Alici)\b|Fatura\s+(?:No|Tarihi)\b|ETTN\b|İmza\b|Imza\b|Kaşe\b|Kase\b)",
        re.IGNORECASE,
    )

    lines = [_clean_pdf_line(line).strip() for line in text.splitlines()]
    notes = []
    seen = set()

    for index, line in enumerate(lines):
        if not line:
            continue

        match = note_header.match(line)
        if not match:
            continue

        parts = []
        inline_note = (match.group(1) or "").strip()
        if inline_note:
            parts.append(inline_note)

        for continuation in lines[index + 1 : index + 9]:
            if not continuation:
                break
            if note_header.match(continuation) or section_stop.search(continuation):
                break
            parts.append(continuation)

        note = re.sub(r"\s+", " ", " ".join(parts)).strip(" :-")
        note_key = note.casefold()
        if note and note_key not in seen:
            seen.add(note_key)
            notes.append(note)

    return "\n".join(notes)


def _clean_pdf_line(line):
    line = _fix_mojibake_currency(line)
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
    line = re.sub(rf"\bK[{WATERMARK_CHARS}]*D[{WATERMARK_CHARS}]*V\b", "KDV", line, flags=re.IGNORECASE)
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


def clean_table_cell(value):
    if value is None:
        return ""

    text = str(value).replace("\n", " ").replace("\xa0", " ").strip()
    text = re.sub(r"\b[A-ZÇĞİÖŞÜ]\b", "", text)
    text = re.sub(
        r"(\d+(?:[.,]\d+)?)[A-ZÇĞİÖŞÜ]+(Adet|Saat|Hizmet|Kg|Lt|Paket|Kutu)",
        r"\1 \2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b[A-ZÇĞİÖŞÜ]+(Adet|Saat|Hizmet|Kg|Lt|Paket|Kutu)\b",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"([€$₺£]\d+[.,])[A-ZÇĞİÖŞÜ]+(?=\d)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_items_from_tables(pdf):
    items = []

    for page in pdf.pages:
        tables = page.extract_tables() or []

        for table in tables:
            if not table or len(table) < 2:
                continue

            header = [clean_table_cell(c).lower() for c in table[0]]

            if not any("kodu" in h for h in header):
                continue
            if not any("toplam" in h for h in header):
                continue

            for row in table[1:]:
                if not row or len(row) < 7:
                    continue

                code = clean_table_cell(row[0])
                description = clean_table_cell(row[1])
                quantity = clean_table_cell(row[2])
                unit = clean_table_cell(row[3])
                unit_price = clean_table_cell(row[4])
                tax_rate = clean_table_cell(row[5])
                total_price = clean_table_cell(row[6])

                quantity_match = re.search(r"\d+(?:[.,]\d+)?", quantity)
                tax_match = re.search(r"\d+(?:[.,]\d+)?", tax_rate)

                if not quantity_match or not _parse_money_number(total_price):
                    continue

                items.append({
                    "code": code,
                    "description": description,
                    "quantity": quantity_match.group(0).replace(".", ",") if quantity_match else quantity.replace(".", ","),
                    "unit_price": _format_amount(_parse_money_number(unit_price)),
                    "tax_rate": tax_match.group(0) if tax_match else tax_rate,
                    "total_price": _format_amount(_parse_money_number(total_price)),
                })

    return items


def _find_items(text):
    item_line_pattern = re.compile(
        rf"^[ \t]*(?P<code>(?:\d{{4}}\.\d{{3}}|[A-Z]{{2,4}}-\d{{3}}|[-\w][\w.-]*))[ \t]+"
        rf"(?P<description>.+?)[ \t]+"
        rf"(?P<quantity>\d+(?:[.,]\d+)?)[ \t]+"
        rf"(?:(?P<unit>{UNIT_RE})[ \t]+)?"
        rf"(?P<unit_price>{MONEY_TOKEN_RE})[ \t]+"
        rf"(?:%?[ \t]*(?P<tax_rate>\d+(?:[.,]\d+)?)[ \t]*%?[ \t]+)?"
        rf"(?P<total_price>{MONEY_TOKEN_RE})(?:[ \t]+.*)?$",
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
    seen_tax_parts = set()
    for line in text.splitlines():
        if "KDV" not in line.upper() and "K.D.V" not in line.upper():
            continue
        parts = re.split(r'(?i)\bK\.?D\.?V\.?\b', line)
        for part in parts[1:]:
            matches = list(re.finditer(MONEY_RE, part, re.IGNORECASE))
            if matches:
                norm_part = re.sub(r'\s+', '', part).upper()
                if norm_part in seen_tax_parts:
                    continue
                seen_tax_parts.add(norm_part)
                
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


def parse_invoice_text(text: str, top_text: str = None) -> dict:
    text = _normalize_extracted_text(text)
    data = {
        "invoice_no": None,
        "invoice_series": None,
        "date": None,
        "time": None,
        "customer_tax_id": None,
        "customer_name": None,
        "customer_title": None,
        "items": [],
        "discount_amount": 0.0,
        "tax_amount": None,
        "total_amount": None,
        "currency": "TRY",
        "exchange_rate": None,
        "subtotal": None,
        "notes": "",
        "_extraction_method": "Yerel Okuyucu (PDF)",
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
    search_text = top_text if top_text is not None else text
    header_end_match = re.search(r"(?i)\b(?:Mal Hizmet|Açıklama|Cinsi|Ürün(?:ler)?|Miktar|Birim Fiyat)\b", search_text)
    if header_end_match:
        search_text = search_text[:header_end_match.start()]
    elif top_text is None:
        search_text = "\n".join(search_text.splitlines()[:50])

    data["invoice_series"] = _first_match(
        [
            r"(?i)(?<![A-Za-zÇĞİÖŞÜçğıöşü])(?<![A-Za-zÇĞİÖŞÜçğıöşü][ \t])(?<![A-Za-zÇĞİÖŞÜçğıöşü][ \t]{2})(?:Fatura[ \t]+)?(?:Seri(?:[ \t]+No|[ \t]+Numarası|[ \t]+Numarasi)?)[ \t]*[:=-][ \t]*([A-Za-z0-9_./-]+(?<!\.))"
        ],
        search_text,
        re.IGNORECASE,
    )
    data["date"] = _first_match([r"\b(\d{1,2}\.\d{2}\.\d{4})\b"], text)
    data["time"] = _first_match([r"\b(\d{2}:\d{2}(?::\d{2})?)\b"], text)
    data["customer_tax_id"] = _extract_customer_tax_id(text)
    data["customer_name"] = _extract_customer_name(text)
    data["customer_title"] = data["customer_name"]
    data["exchange_rate"] = _extract_exchange_rate(text)
    data["notes"] = _extract_invoice_notes(text)

    data["items"] = _find_items(text)
    data["subtotal"] = _first_match([rf"Ara\s*Toplam\s+{MONEY_RE}"], text, re.IGNORECASE)
    data["discount_amount"] = (
        _first_match(
            [rf"(?:Iskonto|İskonto|Ä°skonto|Indirim|İndirim|Ä°ndirim|Discount).*?{MONEY_RE}"],
            text,
            re.IGNORECASE,
        )
        or 0.0
    )
    data["tax_amount"] = _sum_tax_lines(text)
    data["total_amount"] = _first_match(
        [
            rf"Yek(?:un|ün|Ã¼n).*?{MONEY_RE}",
            rf"D(?:oviz|öviz|Ã¶viz)\s*Toplam\s*:?\s*{MONEY_RE}",
            rf"FATURA\s+BEDEL(?:I|İ|Ä°)\s+{MONEY_RE}",
            rf"Genel\s*Toplam\s+{MONEY_RE}",
            rf"(?:Odenecek|Ödenecek|Ã–denecek)\s*Tutar\s+{MONEY_RE}",
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
            table_items = extract_items_from_tables(pdf)

            plain_text = ""
            layout_text = ""
            top_text = None
            if pdf.pages:
                first_page = pdf.pages[0]
                try:
                    top_bbox = (first_page.width * 0.5, 0, first_page.width, first_page.height * 0.4)
                    top_text = first_page.crop(top_bbox).extract_text()
                except Exception:
                    pass

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
                parsed = parse_invoice_text(text, top_text=top_text)
                parsed["_raw_text"] = text
                candidates.append(parsed)
            data = max(candidates, key=_score_data)

            if table_items and len(table_items) >= len(data.get("items", [])):
                data["items"] = table_items

        if not data["items"]:
            print("PDF text was read, but line items were not matched. Falling back to OCR...")
            from extractors.ocr_extractor import parse_pdf_invoice_ocr

            return parse_pdf_invoice_ocr(file_path)

        print("Successfully read PDF file.")
        return data

    except Exception as e:
        print(f"Error parsing PDF file {file_path}: {e}")
        return {}
