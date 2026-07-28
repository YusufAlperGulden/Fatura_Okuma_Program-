import sys
import json
from extractors.pdf_extractor import parse_pdf_invoice

# I need to run this against the specific PDF if I can.
# Wait, the user uploaded it as media__... Wait! The user did not upload the PDF just now.
# But I can see the OCR text from the previous message for this invoice.
