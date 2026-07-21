
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

