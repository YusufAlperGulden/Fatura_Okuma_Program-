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
            return re.sub(r"[\s\xa0]+", "", match.group(1)).strip()
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


def _collapse_repeated_name(value):
    """Collapse exact name repetitions produced by multi-column PDF text."""
    words = str(value or "").split()
    for chunk_size in range(1, (len(words) // 2) + 1):
        if len(words) % chunk_size:
            continue
        chunk = words[:chunk_size]
        if chunk * (len(words) // chunk_size) == words:
            return " ".join(chunk)
    return " ".join(words)


def _extract_unlabeled_header_customer_name(text):
    """Read a company name from compact invoices without party labels.

    Some PDFs put the company name and address at the top, then print the
    VKN/TCKN a few lines later without a label. Restrict this fallback to the
    short header region before that identifier so product descriptions lower
    in the document cannot be mistaken for a customer name.
    """
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in str(text or "").splitlines()
    ]
    lines = [line for line in lines if line]

    tax_id_line_index = None
    for index, line in enumerate(lines[:20]):
        if re.search(r"\b(?:\d[ \t]*){10,11}\b", line):
            tax_id_line_index = index
            break

    if tax_id_line_index is None:
        return None

    header_text = "\n".join(lines[: tax_id_line_index + 1])
    has_explicit_seller_label = re.search(
        r"\b(?:Satıcı|Satici|Seller|Supplier)(?:\s+Bilgileri)?\b",
        header_text,
        re.IGNORECASE,
    )
    has_explicit_buyer_label = re.search(
        r"\b(?:Alıcı|Alici|Buyer|Customer)(?:\s+Bilgileri)?\b",
        header_text,
        re.IGNORECASE,
    )
    if has_explicit_seller_label and not has_explicit_buyer_label:
        return None

    for line in lines[: tax_id_line_index + 1]:
        candidate_line = re.sub(r"\b(?:\d[ \t]*){10,11}\b.*$", "", line).strip(" :-")
        if not candidate_line:
            continue
        if re.search(
            r"\b\d{1,2}\.\d{1,2}\.\d{4}\b|\b\d{1,2}:\d{2}\b",
            candidate_line,
        ):
            continue
        if re.search(
            r"\b(?:Satıcı|Satici|Supplier|Alıcı|Alici|Buyer|Customer)"
            r"(?:\s+Bilgileri)?\b",
            candidate_line,
            re.IGNORECASE,
        ):
            continue

        customer_name = _clean_customer_name_line(candidate_line)
        if not customer_name or len(customer_name) > 160:
            continue

        customer_name = _collapse_repeated_name(customer_name)

        words = re.findall(r"[^\W\d_]{2,}", customer_name, re.UNICODE)
        if len(words) >= 2:
            return customer_name

    return None


def _extract_unlabeled_invoice_no(text):
    """Read a short document number sandwiched by an identical timestamp.

    Some label-free PDF exports place the invoice number on its own line
    between the issue timestamp and a repeated timestamp.  Keeping this
    fallback deliberately narrow prevents arbitrary short numbers in invoice
    bodies from being mistaken for document numbers.
    """
    match = re.search(
        r"(?m)^\s*(\d{1,2}\.\d{2}\.\d{4}[ \t]+\d{1,2}:\d{2})\s*$"
        r"\n^\s*([A-Za-z0-9][A-Za-z0-9_./-]{0,29})\s*$"
        r"\n^\s*\1\s*$",
        text or "",
    )
    return match.group(2) if match else None


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

    return _extract_unlabeled_header_customer_name(text)


def _extract_customer_tax_id(text):
    for line in _buyer_section_lines(text):
        match = re.search(
            r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi[ \t]*No)[ \t]*[:#-]?[ \t]*(\d(?:[\s\xa0]*\d){9,10})\b",
            line,
            re.IGNORECASE,
        )
        if match:
            return re.sub(r"[\s\xa0]+", "", match.group(1))

    return _first_match(
        [
            r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi[ \t]*No)[ \t]*[:#-]?[ \t]*(\d(?:[\s\xa0]*\d){9,10})\b",
            r"\b(\d(?:[\s\xa0]*\d){9,10})\b",
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


SERIAL_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,63}$")
SERIAL_GROUP_RE = re.compile(r"([\(\[])(.*?)([\)\]])", re.DOTALL)
SERIAL_LABEL_RE = re.compile(
    r"(?i)\b(?:seri(?:\s*(?:no\.?|numara(?:si|s\u0131)?))?|serial(?:\s*(?:no\.?|number))?|s/n|imei)"
    r"\s*[:=-]\s*([^\r\n]+)"
)


def _is_serial_token(value):
    token = re.sub(r"\s+", "", str(value or "")).strip("()[]{}")
    return (
        bool(SERIAL_TOKEN_RE.fullmatch(token))
        and any(char.isdigit() for char in token)
        and (any(char.isalpha() for char in token) or len(token) >= 4)
    )


def _serials_from_group(value, require_multiple=True):
    compact = re.sub(r"\s+", "", str(value or "")).strip("()[]{}")
    parts = [part for part in re.split(r"[~,;]+", compact) if part]
    if require_multiple and len(parts) < 2:
        return []
    if not parts or not all(_is_serial_token(part) for part in parts):
        return []
    return parts


def _extract_item_serial_numbers(text):
    """Extract serials only from an individual line-item text block."""
    source = str(text or "")
    serials = []

    # PDF text extraction can split one serial in the middle, for example
    # "DBJ\n251703866". Removing whitespace inside a delimited serial group
    # reconstructs that value without changing ordinary description text.
    for match in SERIAL_GROUP_RE.finditer(source):
        body = match.group(2)
        if "~" not in body and ";" not in body and "," not in body:
            continue
        serials.extend(_serials_from_group(body, require_multiple=True))

    # Explicit item-level labels may contain a single serial number.
    for match in SERIAL_LABEL_RE.finditer(source):
        labelled = re.split(
            rf"\s+(?=\d+(?:[.,]\d+)?\s+(?:{UNIT_RE}\s+)?{MONEY_TOKEN_RE})",
            match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        serials.extend(_serials_from_group(labelled, require_multiple=False))

    unique = []
    seen = set()
    for serial in serials:
        if serial not in seen:
            seen.add(serial)
            unique.append(serial)
    return unique


def _description_without_serials(text):
    source = str(text or "")

    def remove_serial_group(match):
        if _serials_from_group(match.group(2), require_multiple=True):
            return " "
        return match.group(0)

    source = SERIAL_GROUP_RE.sub(remove_serial_group, source)
    source = SERIAL_LABEL_RE.sub(" ", source)
    return re.sub(r"\s+", " ", source).strip(" :-")


def _is_likely_item_description(line):
    candidate = re.sub(r"\s+", " ", str(line or "")).strip()
    if not candidate or not re.search(r"[A-Za-z]", candidate):
        return False
    if _extract_item_serial_numbers(candidate) or "~" in candidate:
        return False
    if re.match(
        r"(?i)^(?:kodu|kod\b|aciklama|mal\s*/?\s*hizmet|urun|miktar|birim|ara\s*toplam|kdv|yekun|genel\s*toplam|odenecek)",
        candidate,
    ):
        return False
    return True


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
                raw_description = clean_table_cell(row[1])
                serial_numbers = _extract_item_serial_numbers(raw_description)
                description = _description_without_serials(raw_description)
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
                    "serial_numbers": serial_numbers,
                    "quantity": quantity_match.group(0).replace(".", ",") if quantity_match else quantity.replace(".", ","),
                    "unit_price": _format_amount(_parse_money_number(unit_price)),
                    "tax_rate": tax_match.group(0) if tax_match else tax_rate,
                    "total_price": _format_amount(_parse_money_number(total_price)),
                })

    return items


def _find_items(text):
    item_line_pattern = re.compile(
        rf"^[ \t]*(?P<code>(?:\d{{4}}\.\d{{3}}|[A-Z]{{2,4}}-\d{{3}}|[-\w][\w.-]*))[ \t]+"
        rf"(?P<description>.*?)[ \t]*"
        rf"(?P<quantity>\d+(?:[.,]\d+)?(?:[.,]\d+)?)[ \t]+"
        rf"(?:(?P<unit>{UNIT_RE})[ \t]+)?"
        rf"(?:(?P<unit_price>{MONEY_TOKEN_RE})[ \t]*)?"
        rf"(?:%?[ \t]*(?P<tax_rate>\d+(?:[.,]\d+)?)[ \t]*%?[ \t]*)?"
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

    cleaned_lines = [_clean_pdf_line(line).strip() for line in text.splitlines()]
    items = []
    seen = set()
    for line_idx, line in enumerate(cleaned_lines):
        for segment in split_repeated_item_line(line):
            match = item_line_pattern.match(segment)
            if not match:
                continue

            unit_price_str = match.group("unit_price")
            total_price_str = match.group("total_price")
            qty_val = float(match.group("quantity").replace(".", "").replace(",", "."))
            total_price_val = _parse_money_number(total_price_str)

            if unit_price_str:
                unit_price_val = _parse_money_number(unit_price_str)
            else:
                unit_price_val = total_price_val / qty_val if qty_val else 0.0

            item = {
                "code": match.group("code"),
                "description": re.sub(r"\s+", " ", match.group("description")).strip(),
                "serial_numbers": [],
                "quantity": match.group("quantity"),
                "unit_price": _format_amount(unit_price_val),
                "tax_rate": match.group("tax_rate"),
                "total_price": _format_amount(total_price_val),
                "_line_idx": line_idx,
            }
            key = (item["code"], item["description"], item["quantity"], item["unit_price"], item["total_price"])
            if key not in seen:
                seen.add(key)
                items.append(item)

    section_stop = re.compile(
        r"(?i)^(?:ara\s*toplam|kdv|yekun|genel\s*toplam|odenecek|vergi|toplam\s*tutar)\b"
    )

    for item_index, item in enumerate(items):
        line_idx = item["_line_idx"]
        next_line_idx = len(cleaned_lines)
        for following_item in items[item_index + 1 :]:
            if following_item["_line_idx"] > line_idx:
                next_line_idx = following_item["_line_idx"]
                break

        # The KATLAN-style layout puts the serial group on the item anchor
        # line, then wraps one serial across the next PDF text line. Only join
        # lines while an item-level serial construct is visibly continuing.
        serial_context = [item["description"]]
        open_group = item["description"].count("(") + item["description"].count("[")
        open_group -= item["description"].count(")") + item["description"].count("]")
        desc_no_serials = _description_without_serials(item["description"]).strip()
        if not desc_no_serials or re.fullmatch(r"[\(\)\[\]\-~,; ]+", desc_no_serials):
            previous_idx = line_idx - 1
            while previous_idx >= 0 and not cleaned_lines[previous_idx]:
                previous_idx -= 1
            if previous_idx >= 0 and _is_likely_item_description(cleaned_lines[previous_idx]):
                serial_context.insert(0, cleaned_lines[previous_idx])

        for continuation in cleaned_lines[line_idx + 1 : next_line_idx]:
            if not continuation or section_stop.search(continuation):
                break
            
            if re.match(r"(?i)^(?:Notlar|İrsaliye|Irsaliye|Fatura\s+Tarihi|Sipariş|Siparis|Banka|IBAN|Hesap|Döviz|Doviz|Yalnız|Yalniz|Yazıyla|Yaziyla|Fatura|İ\s*Bu|Is\s*Bu|İş\s*Bu)\b", continuation):
                break

            serial_context.append(continuation)

        item_text = " ".join(serial_context)
        item["serial_numbers"] = _extract_item_serial_numbers(item_text)
        cleaned_description = _description_without_serials(item_text)

        if cleaned_description:
            item["description"] = cleaned_description

    return items


def _merge_table_items_with_text_items(table_items, text_items):
    """Keep serial metadata when pdfplumber's table candidate wins."""
    used_text_indexes = set()

    for table_index, table_item in enumerate(table_items):
        table_item["serial_numbers"] = list(table_item.get("serial_numbers") or [])
        match_index = None

        for text_index, text_item in enumerate(text_items):
            if text_index in used_text_indexes:
                continue
            if table_item.get("code") and table_item.get("code") == text_item.get("code"):
                match_index = text_index
                break

        if match_index is None and table_index < len(text_items) and table_index not in used_text_indexes:
            match_index = table_index

        if match_index is None:
            continue

        used_text_indexes.add(match_index)
        text_item = text_items[match_index]
        if not table_item["serial_numbers"]:
            table_item["serial_numbers"] = list(text_item.get("serial_numbers") or [])
        if not table_item.get("description") and text_item.get("description"):
            table_item["description"] = text_item["description"]

    return table_items


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
    if not data["invoice_no"]:
        data["invoice_no"] = _extract_unlabeled_invoice_no(text)
    search_text = top_text if top_text is not None else text

    # Ultimate safeguard: Find exact product items and slice before them
    try:
        items = _find_items(search_text)
        if items and "_line_idx" in items[0]:
            first_item_line_idx = items[0]["_line_idx"]
            lines = search_text.split('\n')
            search_text = '\n'.join(lines[:first_item_line_idx])
    except Exception:
        pass

    # Safely cut off at the start of product tables to avoid product serials
    # 'Açıklama' is removed because it can appear at the top.
    header_end_match = re.search(r"(?i)\b(?:Mal[ \t/]+Hizmet|Cinsi|Ürünler|Urunler|(?:Ürün|Urun)[ \t/]+(?:Kodu|Ad[ıi]|Açıklaması|Aciklamasi|Cinsi|Tan[ıi]m[ıi]|Detay[ıi]|Listesi|Hizmet)|Miktar|Birim[ \t]+Fiyat|Stoklar|Par[çc]alar|Par[çc]a[ \t]+Listesi|Hizmetler|Stok[ \t]+Listesi)\b", search_text)
    if header_end_match:
        search_text = search_text[:header_end_match.start()]
    elif top_text is None:
        search_text = "\n".join(search_text.splitlines()[:60])

    # Find all potential matches
    series_regex = r"(?i)(?:Fatura[ \t]+)?(?:Seri(?:[ \t]+No|[ \t]+Numarası|[ \t]+Numarasi)?)[ \t]*[:=-][ \t]*([A-Za-z0-9_./-]+)"
    valid_series = None
    for line in search_text.splitlines():
        # Reject lines that clearly belong to products
        if re.search(r"(?i)\b(?:Yazıcı|Yazici|Cihaz|Ürün|Urun|Model)\b", line):
            continue

        matches = re.findall(series_regex, line)
        if matches:
            # Strip trailing punctuation (., -, /, _)
            val = matches[0].rstrip('.-_/')
            if val:
                valid_series = val
                break

    data["invoice_series"] = valid_series
    data["date"] = _first_match([r"\b(\d{1,2}\.\d{2}\.\d{4})\b"], text)
    data["time"] = _first_match([r"\b(\d{2}:\d{2}(?::\d{2})?)\b"], text)
    data["customer_tax_id"] = _extract_customer_tax_id(text)
    data["customer_name"] = _extract_customer_name(text)
    data["customer_title"] = data["customer_name"]
    data["exchange_rate"] = _extract_exchange_rate(text)
    data["notes"] = _extract_invoice_notes(text)

    data["items"] = _find_items(text)
    for item in data["items"]:
        item.pop("_line_idx", None)

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

            if pdf.pages:
                first_page = pdf.pages[0]
                if first_page.width > first_page.height * 1.1:
                    # Possible landscape multi-copy layout. Let's check for repeated columns.
                    if plain_text.count("Ara Toplam") >= 2 or plain_text.count("Genel Toplam") >= 2 or plain_text.count("KDV") >= 3:
                        print("Detected multi-copy landscape layout. Cropping to the left third to prevent horizontal bleed...")
                        plain_text = ""
                        layout_text = ""
                        for page in pdf.pages:
                            # Crop to left 34%
                            bbox = (0, 0, page.width * 0.34, page.height)
                            cropped = page.crop(bbox)
                            pt = cropped.extract_text()
                            lt = cropped.extract_text(layout=True)
                            if pt: plain_text += pt + "\n"
                            if lt: layout_text += lt + "\n"

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
                data["items"] = _merge_table_items_with_text_items(
                    table_items,
                    data.get("items", []),
                )

        if not data["items"]:
            print("PDF text was read, but line items were not matched. Falling back to OCR...")
            from extractors.ocr_extractor import parse_pdf_invoice_ocr

            return parse_pdf_invoice_ocr(file_path)

        print("Successfully read PDF file.")
        return data

    except Exception as e:
        print(f"Error parsing PDF file {file_path}: {e}")
        return {}
