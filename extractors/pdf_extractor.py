import re

import pdfplumber


CURRENCY_SYMBOLS = "₺$€£"
AMOUNT_NUMBER_RE = r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2}"
MONEY_RE = rf"(?:[{CURRENCY_SYMBOLS}][ \t]*)?({AMOUNT_NUMBER_RE})(?:[ \t]*(?:TL|TRY|USD|EUR|GBP|DOLAR|EURO|[{CURRENCY_SYMBOLS}]))?"
MONEY_TOKEN_RE = rf"(?:[{CURRENCY_SYMBOLS}][ \t]*)?{AMOUNT_NUMBER_RE}(?:[ \t]*(?:TL|TRY|USD|EUR|GBP|DOLAR|EURO|[{CURRENCY_SYMBOLS}]))?"
UNIT_RE = r"Adet|AdeTt|Kg|Lt|Paket|Pak|Kutu|Ay|Yıl|Yil|Ad\.|M2|M3|Saat|Hizmet|Gün|Gun"

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
            return re.sub(r"[ \t\xa0]+", "", match.group(1)).strip()
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
        if re.search(r"\b(?:\d[ \t]*){10,12}\b", line):
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
        candidate_line = re.sub(r"\b(?:\d[ \t]*){10,12}\b.*$", "", line).strip(" :-")
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
            
        # Ignore table header rows that might be OCR'd before the tax ID
        if re.search(
            r"\b(?:Kodu|Açıklama|Aciklama|Miktar|Birim|Fiyatı|Fiyati|Tutar|Toplam)\b",
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
    tax_id = None
    for line in _buyer_section_lines(text):
        match = re.search(
            r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi[ \t]*No)[ \t]*[:#-]?[ \t]*(\d(?:[ \t\xa0]*\d){9,11})\b",
            line,
            re.IGNORECASE,
        )
        if match:
            tax_id = re.sub(r"[ \t\xa0]+", "", match.group(1))
            break

    if not tax_id:
        tax_id = _first_match(
            [
                r"\b(?:TC|TCKN|VKN|VKN/TCKN|Vergi[ \t]*No)[ \t]*[:#-]?[ \t]*(\d(?:[ \t\xa0]*\d){9,11})\b",
                r"\b(\d(?:[ \t\xa0]*\d){9,11})\b",
            ],
            text,
            re.IGNORECASE,
        )

    if tax_id and len(tax_id) == 12 and set(tax_id) == {"1"}:
        return "11111111111"
    return tax_id


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
    
    # Fix missing spaces between concatenated monetary values (e.g. 90,34₺180.678,53)
    line = re.sub(rf"(\d)([{re.escape(CURRENCY_SYMBOLS)}]|TL|TRY|USD|EUR|GBP)", r"\1 \2", line, flags=re.IGNORECASE)

    return line


def _normalize_extracted_text(text):
    cleaned = "\n".join(_clean_pdf_line(line) for line in text.splitlines())
    return re.sub(r"(?i)\b(?:ÖRNEKTİR|RESMİ FATURA DEĞİLDİR|ARA FATURASI)\b", "", cleaned)


def clean_table_cell(value):
    if value is None:
        return ""

    text = str(value).replace("\n", " ").replace("\xa0", " ").strip()
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
    parts = [part for part in re.split(r"[~,;\-]+", compact) if part]
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
        if "~" not in body and ";" not in body and "," not in body and "-" not in body:
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


def extract_items_from_tables(pages):
    items = []

    for page in pages:
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
                    "quantity": quantity_match.group(0) if quantity_match else quantity,
                    "unit_price": _format_amount(_parse_money_number(unit_price)),
                    "tax_rate": tax_match.group(0) if tax_match else tax_rate,
                    "total_price": _format_amount(_parse_money_number(total_price)),
                })

    return items


def _find_items(text):
    item_line_pattern = re.compile(
        rf"^[ \t]*(?P<code>(?:\d{{4}}\.\d{{3}}|[A-Z]{{2,4}}-\d{{3}}|[A-Za-z0-9][\w.-]*))[ \t]+"
        rf"(?P<description>.*?)[ \t]*"
        rf"(?P<quantity>\d+(?:[.,]\d+)?(?:[.,]\d+)?)[ \t]+"
        rf"(?:(?P<unit>{UNIT_RE})[ \t]+)?"
        rf"(?:(?P<unit_price>{MONEY_TOKEN_RE})[ \t]+)?"
        rf"(?:%?[ \t]*(?P<tax_rate>\d+(?:[.,]\d+)?)[ \t]*%?(?=\s|$)[ \t]*)?"
        rf"(?P<total_price>{MONEY_TOKEN_RE})(?:[ \t]+[^0-9]+)?$",
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

    def _join_wrapped_item_lines(lines):
        joined_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(r"^[ \t]*(?:\d{4}\.\d{3}|[A-Z]{2,4}-\d{3})", line) and not item_line_pattern.match(line):
                matched = False
                candidates = [(line, 0)]
                for j in range(1, 6):
                    if i + j < len(lines):
                        new_candidates = []
                        for c_text, _ in candidates:
                            new_candidates.append((c_text + " " + lines[i+j], j))
                            new_candidates.append((c_text + lines[i+j], j))
                        
                        for c_text, consumed in new_candidates:
                            if item_line_pattern.match(c_text):
                                joined_lines.append(c_text)
                                i += consumed
                                matched = True
                                break
                        if matched:
                            break
                        candidates = new_candidates
                if matched:
                    i += 1
                    continue
            joined_lines.append(line)
            i += 1
        return joined_lines

    raw_cleaned = [_clean_pdf_line(line).strip() for line in text.splitlines()]
    cleaned_lines = _join_wrapped_item_lines(raw_cleaned)
    items = []
    seen = set()
    for line_idx, line in enumerate(cleaned_lines):
        if re.match(r"(?i)^[ \t]*(?:Fatura\s+(?:Seri|No|Tarihi|Tutar|Bedeli)|Seri\s+No|İrsaliye|Irsaliye)\b", line):
            continue

        for segment in split_repeated_item_line(line):
            match = item_line_pattern.match(segment)
            if not match:
                continue

            if re.match(r"(?i)^(?:kodu|kod\b|açıklama|aciklama|mal\s*/?\s*hizmet|ürün|urun|miktar|birim|ara\s*toplam|kdv|k\.?d\.?v\.?|yekun|genel\s*toplam|ödenecek|odenecek|indirim|iskonto|toplam)", match.group("code")):
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
        if (
            not desc_no_serials
            or re.fullmatch(r"[\(\)\[\]\-~,; ]+", desc_no_serials)
            or "~" in desc_no_serials
            or bool(_extract_item_serial_numbers(desc_no_serials))
        ):
            previous_idx = line_idx - 1
            while previous_idx >= 0:
                prev_line = cleaned_lines[previous_idx]
                if not prev_line:
                    previous_idx -= 1
                    continue
                if _extract_item_serial_numbers(prev_line) or "~" in prev_line or prev_line.startswith("("):
                    serial_context.insert(0, prev_line)
                    previous_idx -= 1
                    continue
                if _is_likely_item_description(prev_line):
                    serial_context.insert(0, prev_line)
                    break
                previous_idx -= 1

        for continuation in cleaned_lines[line_idx + 1 : next_line_idx]:
            if not continuation or section_stop.search(continuation):
                break

            # Stop if this line looks like a new product code starting alone
            if re.match(r"^\d{4}\.\d{3}\b|^[A-Z]{2,4}-\d{3}\b", continuation):
                break

            # Stop if this line contains a price/currency token — it's a data row, not a description
            if re.search(r"(?:₺|TL|USD|EUR)\s*[\d.,]+|[\d.,]+\s*(?:₺|TL|USD|EUR)", continuation):
                break

            if re.match(r"(?i)^(?:Notlar|İrsaliye|Irsaliye|Fatura\s+Tarihi|Sipariş|Siparis|Banka|IBAN|Hesap|Hesaba|Havale|Sanal|Döviz|Doviz|Yalnız|Yalniz|Yalnızca|Yazıyla|Yaziyla|Fatura|İ\s*Bu|Is\s*Bu|İş\s*Bu|DSM\s+GRUP|\*[ \t]*Fatura)\b", continuation):
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
        table_desc_clean = _description_without_serials(table_item.get("description", "")).strip()
        if (not table_item.get("description") or not table_desc_clean or re.fullmatch(r"[\(\)\[\]\-~,; ]+", table_desc_clean)) and text_item.get("description"):
            table_item["description"] = text_item["description"]

    return table_items


def _trim_trailing_row_bleed(items):
    """Trim trailing words from an item description if they match the start of the next item description."""
    for i in range(len(items) - 1):
        curr_desc = (items[i].get("description") or "").strip()
        next_desc = (items[i + 1].get("description") or "").strip()

        curr_words = curr_desc.split()
        next_words = next_desc.split()

        if not curr_words or not next_words:
            continue

        for start_idx in range(1, len(curr_words)):
            suffix = " ".join(curr_words[start_idx:]).strip()
            suffix_lower = suffix.lower()
            next_desc_lower = next_desc.lower()

            if (
                next_desc_lower.startswith(suffix_lower)
                or suffix_lower.startswith(next_desc_lower[:len(suffix_lower)])
            ):
                new_curr = " ".join(curr_words[:start_idx]).strip(" -:,")
                if new_curr:
                    items[i]["description"] = new_curr
                break
    return items


def _sum_tax_lines(text):
    total = 0.0
    found = False
    seen_tax_parts = set()
    for line in text.splitlines():
        if "KDV" not in line.upper() and "K.D.V" not in line.upper():
            continue
        if "MATRAH" in line.upper():
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
            r"(?:Fatura|Belge|Invoice)[ \t]*(?:No|Numarası|Numarasi|Number)?[ \t]*[:#-][ \t]*([A-Z0-9-/]+)",
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


def extract_items_via_item_blocks(pages):
    """
    Item Block Geometry Extractor:
    Uses word coordinates (x, y) to construct vertical item bands, match financial anchors,
    and cleanly separate product descriptions from multiline serial blocks.
    """
    items = []
    for page in pages:
        words = page.extract_words()
        if not words:
            continue

        code_words = []
        for w in words:
            text = w["text"].strip()
            if re.fullmatch(r"\d{3,5}\.\d{3}|[A-Z]{2,4}-\d{3}", text):
                code_words.append(w)

        if not code_words:
            continue

        words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))
        lines = []
        for w in words_sorted:
            w_center = (w["top"] + w["bottom"]) / 2
            matched_line = None
            for line in lines[-5:]:
                line_center = (line["top"] + line["bottom"]) / 2
                if abs(w_center - line_center) <= 4:
                    matched_line = line
                    break
            if matched_line is None:
                lines.append({"top": w["top"], "bottom": w["bottom"], "words": [w]})
            else:
                matched_line["words"].append(w)
                matched_line["top"] = min(matched_line["top"], w["top"])
                matched_line["bottom"] = max(matched_line["bottom"], w["bottom"])

        anchors = []
        for code_w in code_words:
            code_y = (code_w["top"] + code_w["bottom"]) / 2
            best_line = None
            min_dist = 999999
            for line in lines:
                line_y = (line["top"] + line["bottom"]) / 2
                line_text = " ".join(w["text"] for w in line["words"])
                if abs(line_y - code_y) <= 80:
                    if re.search(r"[\d.,]+,\d{2}", line_text):
                        dist = abs(line_y - code_y)
                        if dist < min_dist:
                            min_dist = dist
                            best_line = line
            if best_line:
                anchors.append({
                    "code": code_w["text"],
                    "code_word": code_w,
                    "anchor_y": (best_line["top"] + best_line["bottom"]) / 2,
                    "line": best_line
                })

        anchors = sorted(anchors, key=lambda a: a["anchor_y"])
        if not anchors:
            continue

        # Detect Table Header Bottom & Footer Top for generic item_top / item_bottom bounds
        header_bottom = 0.0
        footer_top = page.height

        for l in lines:
            l_text = " ".join(w["text"] for w in l["words"])
            if re.search(r"(?i)\b(?:kodu|aciklama|açıklama|miktar|birim|fiyat)\b", l_text):
                if l["bottom"] > header_bottom:
                    header_bottom = l["bottom"]
            if re.search(r"(?i)\b(?:ara\s*toplam|kdv|yekun|genel\s*toplam|odenecek)\b", l_text):
                if l["top"] < footer_top:
                    footer_top = l["top"]

        # Detect Horizontal Rule lines on page for item-table bottom boundary
        h_rules = []
        for l in (page.lines or []):
            if abs(l["top"] - l["bottom"]) <= 3 and (l["x1"] - l["x0"]) >= 50:
                h_rules.append(l["top"])
        for r in (page.rects or []):
            if r.get("height", 0) <= 3 and r.get("width", 0) >= 50:
                h_rules.append(r["top"])

        table_top = header_bottom if header_bottom > 0 else (min(a["anchor_y"] for a in anchors) - 40)
        table_bottom = footer_top if footer_top < page.height else (max(a["anchor_y"] for a in anchors) + 40)

        for idx, anchor in enumerate(anchors):
            top_y = table_top if idx == 0 else (anchors[idx - 1]["anchor_y"] + anchor["anchor_y"]) / 2
            bot_y = table_bottom if idx == len(anchors) - 1 else (anchor["anchor_y"] + anchors[idx + 1]["anchor_y"]) / 2

            if idx < len(anchors) - 1:
                next_anchor = anchors[idx + 1]
                next_code_y = next_anchor["anchor_y"]
                # Check lines between current anchor and next anchor for next item's pre-anchor description line
                # A pre-anchor line is close to next_code_y (< 15pt above next anchor) and starts before next_line_top
                candidate_pre_lines = []
                for l in lines:
                    l_center = (l["top"] + l["bottom"]) / 2
                    if anchor["anchor_y"] + 5 < l_center < next_code_y:
                        l_text = " ".join(w["text"] for w in l["words"]).strip()
                        # If line is close to next anchor (< 15pt) and does not look like current item continuation
                        if (next_code_y - l_center) <= 15:
                            candidate_pre_lines.append(l["top"])
                
                limit_y = min(candidate_pre_lines) - 0.5 if candidate_pre_lines else (next_anchor["line"]["top"] - 0.5)
                bot_y = min(bot_y, limit_y)

            if idx == len(anchors) - 1:
                rules_below = [r_y for r_y in h_rules if r_y > anchor["anchor_y"] + 5]
                if rules_below:
                    bot_y = min(bot_y, min(rules_below))

            # Filter lines above and below anchor using local continuity
            anchor_line_y = (anchor["line"]["top"] + anchor["line"]["bottom"]) / 2
            
            # Pre-anchor lines: scan upward step-by-step starting from anchor line
            pre_anchor_lines = []
            curr_y = anchor["line"]["top"]
            lines_above = sorted([l for l in lines if top_y <= (l["top"] + l["bottom"]) / 2 < anchor_line_y - 4], key=lambda l: l["bottom"], reverse=True)
            
            for l in lines_above:
                gap = curr_y - l["bottom"]
                l_text = " ".join(w["text"] for w in l["words"]).strip()
                if gap > 22 or re.search(r"(?i)^(?:Kodu|Kod\b|Açıklama|Aciklama|Miktar|Birim|Fiyat|TC\b|Tarih|Posta|Adres|Sayın|Müşteri)", l_text):
                    break
                pre_anchor_lines.append(l)
                curr_y = l["top"]
            pre_anchor_lines.reverse()

            # Post-anchor & anchor lines
            post_anchor_lines = [l for l in lines if anchor_line_y - 4 <= (l["top"] + l["bottom"]) / 2 <= bot_y]

            band_lines = pre_anchor_lines + post_anchor_lines

            desc_parts = []
            serial_raw_parts = []
            in_serial_block = False
            paren_balance = 0

            for line in sorted(band_lines, key=lambda l: l["top"]):
                line_y = (line["top"] + line["bottom"]) / 2
                is_anchor = abs(line_y - anchor["anchor_y"]) <= 4

                # Classify the entire physical line FIRST before column filtering
                full_line_text = " ".join(w["text"].strip() for w in line["words"]).strip()
                full_line_x0 = min(w["x0"] for w in line["words"])
                full_line_x1 = max(w["x1"] for w in line["words"])

                # Check if this line is a structural footer/note prose block
                if not is_anchor and line_y > anchor["anchor_y"] + 10:
                    is_footer_prose = (
                        re.search(r"(?i)^(?:İş\s*bu\s*fatura|Fatura\s*üzerindeki|\*\s*RFIDmarket|\*\s*E-İrsaliye|\*\s*Kredi\s*kartı|Döviz\s*Kuru|Döviz\s*Toplam|Ara\s*Toplam|KDV|Yekün|Genel\s*Toplam)", full_line_text)
                        or ((full_line_x1 - full_line_x0 > 320) and full_line_x0 < 80)
                    )
                    if is_footer_prose:
                        break

                filtered_words = [w for w in line["words"] if w["text"].strip() != anchor["code"]]
                line_words_clean = []
                for w in sorted(filtered_words, key=lambda w: w["x0"]):
                    t = w["text"].strip()
                    if is_anchor:
                        if re.fullmatch(r"[₺$€]?\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})", t) or t in ("₺", "TL", "USD", "EUR"):
                            continue
                        if w["x0"] > (anchor["code_word"]["x0"] + 110) and re.fullmatch(r"\d+(?:[.,]\d+)?", t):
                            continue
                    line_words_clean.append(t)

                clean_text = " ".join(line_words_clean).strip()
                if not clean_text:
                    continue

                if re.search(r"(?i)^(?:Ara\s*Toplam|KDV|Yekün|Genel\s*Toplam|Top|Toplam)", clean_text):
                    break

                has_serial = bool(_extract_item_serial_numbers(clean_text) or re.search(r"[A-Z]{2,}\d{3,}", clean_text))
                if in_serial_block or ("(" in clean_text and has_serial and any(c in clean_text for c in ("~", ";", ",", "-"))):
                    in_serial_block = True
                    serial_raw_parts.append(clean_text)
                    paren_balance += clean_text.count("(") - clean_text.count(")")
                    if paren_balance <= 0 and ")" in clean_text:
                        in_serial_block = False
                else:
                    if not re.fullmatch(r"[\(\)\[\]\-~,; ]+", clean_text):
                        desc_parts.append(clean_text)

            raw_serial = "".join(serial_raw_parts).strip("()[] ")
            serials = [s.strip() for s in re.split(r"[~,;\-]+", raw_serial) if s.strip() and _is_serial_token(s.strip())]
            
            raw_description = " ".join(desc_parts).strip()
            extra_serials = _extract_item_serial_numbers(raw_description)
            if extra_serials and not serials:
                serials = extra_serials

            description = _description_without_serials(raw_description)
            description = re.sub(r"\s+", " ", description)
            description = re.sub(r"\s+([,.:;])", r"\1", description).strip()

            # Deduplicate repeated phrase copies from multi-copy landscape layouts
            desc_words = description.split()
            for n in (3, 2):
                if desc_words and len(desc_words) % n == 0:
                    k = len(desc_words) // n
                    chunk = desc_words[:k]
                    if all(desc_words[i * k : (i + 1) * k] == chunk for i in range(1, n)):
                        description = " ".join(chunk)
                        break

            items.append({
                "code": anchor["code"],
                "description": description,
                "serial_numbers": serials,
            })

    unique_items = []
    for it in items:
        if not any(u["code"] == it["code"] and u["description"] == it["description"] for u in unique_items):
            unique_items.append(it)

    return unique_items


def parse_pdf_invoice(file_path: str) -> dict:
    """
    Parses a digital PDF invoice using pdfplumber and regex.
    """
    print(f"Parsing PDF invoice: {file_path}")

    try:
        with pdfplumber.open(file_path) as pdf:
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
                        print("Detected multi-copy landscape layout. Cropping to the right third to prevent horizontal bleed...")
                        plain_text = ""
                        layout_text = ""
                        cropped_pages = []
                        for page in pdf.pages:
                            # Crop to right 34% (copy 3) to prevent right-side clipping
                            bbox = (page.width * 0.66, 0, page.width, page.height)
                            cropped = page.crop(bbox)
                            cropped_pages.append(cropped)
                            pt = cropped.extract_text()
                            lt = cropped.extract_text(layout=True)
                            if pt: plain_text += pt + "\n"
                            if lt: layout_text += lt + "\n"
                        table_items = extract_items_from_tables(cropped_pages)
                    else:
                        table_items = extract_items_from_tables(pdf.pages)
                else:
                    table_items = extract_items_from_tables(pdf.pages)
            else:
                table_items = []

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

        # Fikir 4.1 Item Block Geometry Reconciliation:
        # If an item's description is missing, contains only serial numbers, or lost pre-anchor lines (e.g. ASYAPORT, KATLAN),
        # use the Item Block Geometry Extractor to reconstruct the complete description & multiline serial block.
        geom_items = None
        for item in data.get("items", []):
            desc_clean = _description_without_serials(item.get("description", "")).strip()
            needs_geom = (
                not item.get("description")
                or not desc_clean
                or re.fullmatch(r"[\(\)\[\]\-~,; ]+", desc_clean)
            )

            if geom_items is None:
                try:
                    target_pages = cropped_pages if 'cropped_pages' in locals() and cropped_pages else pdf.pages
                    geom_items = extract_items_via_item_blocks(target_pages)
                except Exception as ge:
                    print(f"Geometry item block extraction note: {ge}")
                    geom_items = []

            if geom_items:
                for g in geom_items:
                    if g.get("code") == item.get("code") and g.get("description"):
                        item["description"] = g["description"]
                        if g.get("serial_numbers") and not item.get("serial_numbers"):
                            item["serial_numbers"] = g["serial_numbers"]
                        break

        data["items"] = _trim_trailing_row_bleed(data.get("items", []))

        for item in data.get("items", []):
            desc = item.get("description", "")
            if _extract_item_serial_numbers(desc) and not item.get("serial_numbers"):
                item["serial_numbers"] = _extract_item_serial_numbers(desc)
            desc_clean = _description_without_serials(desc)
            if desc_clean:
                item["description"] = desc_clean
            if re.match(r"(?i)^kargo\s+ücreti\b", item.get("description", "")):
                item["description"] = "Kargo Ücreti"

        if not data["items"]:
            print("PDF text was read, but line items were not matched. Falling back to OCR...")
            from extractors.ocr_extractor import parse_pdf_invoice_ocr

            return parse_pdf_invoice_ocr(file_path)

        print("Successfully read PDF file.")
        return data

    except Exception as e:
        print(f"Error parsing PDF file {file_path}: {e}")
        return {}
