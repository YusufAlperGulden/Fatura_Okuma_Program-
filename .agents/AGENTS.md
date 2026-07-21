
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

