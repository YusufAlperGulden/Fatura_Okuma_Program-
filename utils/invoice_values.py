from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


MONEY_QUANTUM = Decimal("0.01")
# Deliberate business rule shared by local validation and Uyumsoft XML
# generation: document-level rounding differences up to 1.00 TL are accepted.
DOCUMENT_AMOUNT_TOLERANCE = Decimal("1.00")
SUPPORTED_CURRENCIES = {"TRY", "USD", "EUR", "GBP"}

_CURRENCY_ALIASES = {
    "": "TRY",
    "TL": "TRY",
    "TRY": "TRY",
    "₺": "TRY",
    "TÜRK LİRASI": "TRY",
    "TURK LIRASI": "TRY",
    "TÜRK LIRASI": "TRY",
    "USD": "USD",
    "DOLAR": "USD",
    "$": "USD",
    "AMERIKAN DOLARI": "USD",
    "AMERİKAN DOLARI": "USD",
    "EUR": "EUR",
    "EURO": "EUR",
    "€": "EUR",
    "GBP": "GBP",
    "STERLIN": "GBP",
    "STERLİN": "GBP",
    "£": "GBP",
}

_NUMBER_TOKENS = (
    "TÜRK LİRASI",
    "TURK LIRASI",
    "TÜRK LIRASI",
    "AMERİKAN DOLARI",
    "AMERIKAN DOLARI",
    "STERLİN",
    "STERLIN",
    "DOLAR",
    "EURO",
    "TRY",
    "USD",
    "EUR",
    "GBP",
    "TL",
    "₺",
    "$",
    "€",
    "£",
    "%",
)


def normalize_currency(value: Any, *, strict: bool = True) -> str:
    text = str(value or "").strip().upper()
    normalized = _CURRENCY_ALIASES.get(text)
    if normalized:
        return normalized
    if strict:
        raise ValueError(f"unsupported currency: {text or value!r}")
    return text


def parse_localized_decimal(value: Any) -> Decimal | None:
    """Parse Turkish/international decimal text without silently changing scale.

    A single comma or dot is treated as the decimal separator. Repeated equal
    separators are accepted only as conventional three-digit grouping, e.g.
    ``1.234.567``. Mixed separators use the last separator as the decimal mark.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, (int, float)):
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return parsed if parsed.is_finite() else None

    text = str(value).strip().upper()
    for token in _NUMBER_TOKENS:
        text = text.replace(token, "")
    text = "".join(text.split())
    if not text:
        return None

    comma_count = text.count(",")
    dot_count = text.count(".")
    if comma_count and dot_count:
        decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        text = text.replace(grouping_separator, "")
        text = text.replace(decimal_separator, ".")
    elif comma_count == 1:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0] != "0" and not parts[0].startswith("0"):
            text = "".join(parts)
        else:
            text = text.replace(",", ".")
    elif dot_count == 1:
        parts = text.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0] != "0" and not parts[0].startswith("0"):
            text = "".join(parts)
        else:
            pass
    elif comma_count > 1:
        parts = text.split(",")
        if not parts[0] or not all(len(part) == 3 for part in parts[1:]):
            return None
        text = "".join(parts)
    elif dot_count > 1:
        parts = text.split(".")
        if not parts[0] or not all(len(part) == 3 for part in parts[1:]):
            return None
        text = "".join(parts)

    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def decimal_places(value: Decimal) -> int:
    return max(0, -value.as_tuple().exponent)


def format_decimal(value: Decimal, *, max_places: int, min_places: int = 0) -> str:
    if decimal_places(value) > max_places:
        raise ValueError(f"value has more than {max_places} decimal places")
    text = format(value, "f")
    if "." in text:
        integer, fraction = text.split(".", 1)
        fraction = fraction.rstrip("0")
        if len(fraction) < min_places:
            fraction += "0" * (min_places - len(fraction))
        text = f"{integer}.{fraction}" if fraction else integer
    elif min_places:
        text = f"{text}.{'0' * min_places}"
    return text
