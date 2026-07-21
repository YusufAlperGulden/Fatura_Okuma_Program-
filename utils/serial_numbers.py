from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any


_SERIAL_SEPARATOR_RE = re.compile(r"[~,;\r\n]+")
_OUTER_WRAPPERS = {"(": ")", "[": "]", "{": "}"}


def _serial_text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""

    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        if value.is_integer():
            return str(int(value))

    return str(value).strip()


def _strip_outer_wrapper(value: str) -> str:
    text = value.strip()
    while len(text) >= 2 and _OUTER_WRAPPERS.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    return text


def normalize_serial_numbers(value: Any) -> list[str]:
    """Return serial numbers as an ordered, de-duplicated list of strings.

    Invoice sources commonly expose serials either as a JSON list or as one
    cell/text fragment separated with tildes, commas, semicolons, or newlines.
    Serial values are deliberately kept as strings so leading zeroes and case
    are not changed.
    """

    if value is None or isinstance(value, Mapping):
        return []

    if isinstance(value, str) or not isinstance(value, Iterable):
        values = [value]
    else:
        values = value

    normalized: list[str] = []
    seen: set[str] = set()

    for raw_value in values:
        text = _strip_outer_wrapper(_serial_text(raw_value))
        if not text:
            continue

        for fragment in _SERIAL_SEPARATOR_RE.split(text):
            serial = _strip_outer_wrapper(fragment)
            if serial and serial not in seen:
                seen.add(serial)
                normalized.append(serial)

    return normalized


def normalize_invoice_serial_numbers(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize every line item's optional ``serial_numbers`` field in place."""

    items = data.get("items") or []
    if not isinstance(items, list):
        return data

    for item in items:
        if isinstance(item, dict):
            item["serial_numbers"] = normalize_serial_numbers(
                item.get("serial_numbers")
            )

    return data


def _normalized_item_code(item: Any) -> str:
    if not isinstance(item, Mapping):
        return ""
    return str(item.get("code") or "").strip().casefold()


def safe_merge_ai_data(
    target: dict[str, Any], source: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge source local data into target AI data, preserving high-confidence fields and serials."""

    if isinstance(source, dict):
        # Preserve high-confidence fields from local extraction
        for field in ["customer_tax_id", "invoice_no", "date", "time", "currency"]:
            val = source.get(field)
            if not val:
                continue
            # Only preserve tax IDs if they look like real tax IDs (10 or 11 digits)
            if field == "customer_tax_id":
                val_str = str(val).strip()
                if not (val_str.isdigit() and len(val_str) in (10, 11)):
                    continue
            target[field] = val

    normalize_invoice_serial_numbers(target)
    if not isinstance(source, dict):
        return target

    target_items = target.get("items") or []
    source_items = source.get("items") or []
    if not isinstance(target_items, list) or not isinstance(source_items, list):
        return target

    source_indexes_by_code: dict[str, list[int]] = {}
    for source_index, source_item in enumerate(source_items):
        code = _normalized_item_code(source_item)
        if code:
            source_indexes_by_code.setdefault(code, []).append(source_index)

    used_source_indexes: set[int] = set()

    for target_index, target_item in enumerate(target_items):
        if not isinstance(target_item, dict):
            continue

        source_index = None
        target_code = _normalized_item_code(target_item)
        if target_code:
            for candidate_index in source_indexes_by_code.get(target_code, []):
                if candidate_index not in used_source_indexes:
                    source_index = candidate_index
                    break

        if (
            source_index is None
            and target_index < len(source_items)
            and target_index not in used_source_indexes
        ):
            source_index = target_index

        if source_index is None:
            continue

        source_item = source_items[source_index]
        if not isinstance(source_item, Mapping):
            continue

        used_source_indexes.add(source_index)
        target_item["serial_numbers"] = normalize_serial_numbers(
            [
                *normalize_serial_numbers(target_item.get("serial_numbers")),
                *normalize_serial_numbers(source_item.get("serial_numbers")),
            ]
        )

    return target
