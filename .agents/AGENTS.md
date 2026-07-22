
<RULE[project_pdf_extraction]>
---
name: multiline-invoice-items
description: Guidelines for parsing PDF invoices where item rows wrap across multiple text lines.
---
# Multiline Invoice Item Parsing

When extracting tabular data from PDF invoices using text-based regex (e.g., pdf_extractor.py), be aware that item descriptions and product codes often wrap across multiple lines.

- **Do NOT** rely solely on single-line regex matches (^...$) to collect all items, as this will drop the first half of a wrapped line.
- **Do** preprocess the text lines to detect wrapped lines. If a line clearly starts with a product code (e.g., \d{4}\.\d{3}) but is missing trailing price/quantity data, peek at the next line and join them if the combined string fulfills the complete item regex.
- Always validate that the quantities and prices extract correctly after joining the wrapped lines.
</RULE[project_pdf_extraction]>


<RULE[project_tckn_validation]>
---
name: tckn-placeholder-bypass
description: Guidelines for handling placeholder TCKN/VKN numbers (e.g., all 1s).
---
# TCKN Placeholder Bypass
When extracting and validating TCKN/VKN (Turkish ID or Tax Numbers):
1. **12-Digit Tolerance**: You must tolerate 12-digit numbers as valid tax IDs if they consist entirely of `1`s (e.g., `111111111111`), because this is a common placeholder used by accountants.
2. **Extraction Regex**: Ensure extraction regexes match `{10,12}` digits instead of strictly `{10,11}` to prevent ignoring placeholder IDs.
3. **Validation Bypass**: In any validation logic, explicitly bypass checksum rules and length checks if the TCKN is `11111111111` (11 ones) or `111111111111` (12 ones). Treat these values as valid without generating validation errors.
</RULE[project_tckn_validation]>



<RULE[project_ocr_safety]>
---
name: ocr-regex-safety
description: Guidelines for safely writing regex for OCR text to prevent cross-line bleeding.
---
# OCR Regex Safety
When writing regular expressions to extract structured data (like IDs, phone numbers, or codes) from multiline OCR text:
1. **Never use `\s` inside digit-matching groups**: Use `[ \t\xa0]` instead of `\s` or `[\s\xa0]` when allowing optional spacing between characters of a single logical string. `\s` matches `\n` and will cause the regex to "bleed" onto the next line, concatenating unrelated numbers (like dates or quantities) into the target string.
2. **Filter out table headers**: When extracting names or addresses from a block of text, always explicitly filter out common table header keywords (e.g., "Kodu", "Açýklama", "Miktar", "Fiyat", "Tutar") to avoid mistaking OCR-reordered table headers for entity names.
</RULE[project_ocr_safety]>


<RULE[project_pdf_spacing]>
---
name: pdf-money-spacing
description: Guidelines for preprocessing PDF text to fix missing spaces between adjacent currency values.
---
# PDF Money Spacing
When parsing invoices, text extraction tools (like `pdfplumber` or OCR) occasionally concatenate adjacent columns (like Unit Price and Total Price) into a single string without spaces (e.g., `?90,34?180.678,53` instead of `?90,34 ?180.678,53`). 
To ensure regexes match correctly:
1. Always preprocess invoice lines to inject a space between a digit and a currency symbol/code. 
2. Use a regex like `re.sub(r"(\d)([$€£?]|TL|TRY|USD|EUR|GBP)", r"\1 \2", line, flags=re.IGNORECASE)` to split concatenated monetary values before attempting to match line items.
</RULE[project_pdf_spacing]>
