from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from validators.invoice_validator import validate_invoice


DEFAULT_OUTPUT_DIR = Path("scratch") / "mikro_v16"
DEFAULT_LEDGER_PATH = DEFAULT_OUTPUT_DIR / "bridge_state.sqlite"

HEADER_COLUMNS = [
    "source_system",
    "integration_id",
    "invoice_no",
    "issue_date",
    "document_type",
    "customer_tax_id",
    "customer_code",
    "customer_name",
    "currency",
    "subtotal",
    "tax_amount",
    "total_amount",
    "note",
]

LINE_COLUMNS = [
    "integration_id",
    "invoice_no",
    "line_no",
    "product_code",
    "description",
    "unit",
    "quantity",
    "unit_price",
    "vat_rate",
    "line_total",
    "warehouse_code",
]

CUSTOMER_COLUMNS = [
    "source_system",
    "customer_tax_id",
    "customer_code",
    "title",
    "tax_office",
    "address",
    "city",
    "country",
    "email",
]


class MikroBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class MikroExportResult:
    success: bool
    message: str
    package_id: str
    package_dir: str
    files: list[str]
    manifest: dict[str, Any]
    already_exported: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _money(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")

    text = str(value).strip().upper()
    for currency in ["TL", "TRY", "$", "USD", "DOLAR", "EUR", "EURO", "GBP", "%"]:
        text = text.replace(currency, "")
    text = text.replace(" ", "")

    if not text:
        return Decimal("0.00")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            text = text.replace(",", ".")
        elif len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            text = text.replace(".", "")

    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")


def _fmt_money(value: Any) -> str:
    amount = _money(value)
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_date(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return datetime.now().date().isoformat()

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text[:10]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned or "package"


def _canonical_invoice_payload(invoice: dict[str, Any], source_system: str) -> str:
    relevant = {
        "source_system": source_system,
        "invoice_no": invoice.get("invoice_no"),
        "date": invoice.get("date"),
        "customer_tax_id": invoice.get("customer_tax_id"),
        "total_amount": invoice.get("total_amount"),
        "items": invoice.get("items") or [],
    }
    return json.dumps(relevant, sort_keys=True, ensure_ascii=True, default=str)


def stable_package_id(invoice: dict[str, Any], source_system: str = "TOS") -> str:
    normalized = copy.deepcopy(invoice or {})
    validate_invoice(normalized)
    digest = hashlib.sha256(_canonical_invoice_payload(normalized, source_system).encode("utf-8")).hexdigest()
    return f"{source_system.upper()}-{digest[:16].upper()}"


def _write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _safe_text(row.get(column)) for column in columns})


def _read_ledger_record(ledger_path: Path, package_id: str) -> dict[str, Any] | None:
    if not ledger_path.exists():
        return None
    conn = sqlite3.connect(ledger_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT package_id, created_at, package_dir FROM exports WHERE package_id = ?",
            (package_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _record_ledger(ledger_path: Path, package_id: str, package_dir: Path, source_system: str) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ledger_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exports (
                package_id TEXT PRIMARY KEY,
                source_system TEXT NOT NULL,
                package_dir TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO exports (package_id, source_system, package_dir, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (package_id, source_system, str(package_dir), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def _customer_name(invoice: dict[str, Any]) -> str:
    return _safe_text(
        invoice.get("customer_title")
        or invoice.get("customer_name")
        or invoice.get("customer")
        or "UNKNOWN CUSTOMER"
    )


def _tax_rate(invoice: dict[str, Any], item: dict[str, Any] | None = None) -> str:
    item = item or {}
    if item.get("tax_rate") not in (None, ""):
        return _fmt_money(item.get("tax_rate"))
    if invoice.get("tax_rate") not in (None, ""):
        return _fmt_money(invoice.get("tax_rate"))

    subtotal = _money(invoice.get("subtotal"))
    tax = _money(invoice.get("tax_amount"))
    if subtotal > 0 and tax > 0:
        return str((tax / subtotal * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return "0.00"


def _build_header_row(invoice: dict[str, Any], package_id: str, source_system: str) -> dict[str, Any]:
    invoice_no = _safe_text(invoice.get("invoice_no")) or package_id
    return {
        "source_system": source_system,
        "integration_id": package_id,
        "invoice_no": invoice_no,
        "issue_date": _normalize_date(invoice.get("date")),
        "document_type": _safe_text(invoice.get("invoice_type") or "SATIS"),
        "customer_tax_id": _safe_text(invoice.get("customer_tax_id")),
        "customer_code": _safe_text(invoice.get("customer_code") or invoice.get("customer_tax_id")),
        "customer_name": _customer_name(invoice),
        "currency": _safe_text(invoice.get("currency") or "TRY"),
        "subtotal": _fmt_money(invoice.get("subtotal")),
        "tax_amount": _fmt_money(invoice.get("tax_amount")),
        "total_amount": _fmt_money(invoice.get("total_amount")),
        "note": _safe_text(invoice.get("note")),
    }


def _build_customer_row(invoice: dict[str, Any], source_system: str) -> dict[str, Any]:
    return {
        "source_system": source_system,
        "customer_tax_id": _safe_text(invoice.get("customer_tax_id")),
        "customer_code": _safe_text(invoice.get("customer_code") or invoice.get("customer_tax_id")),
        "title": _customer_name(invoice),
        "tax_office": _safe_text(invoice.get("customer_tax_office")),
        "address": _safe_text(invoice.get("customer_address")),
        "city": _safe_text(invoice.get("customer_city")),
        "country": _safe_text(invoice.get("customer_country") or "TR"),
        "email": _safe_text(invoice.get("customer_email")),
    }


def _build_line_rows(invoice: dict[str, Any], package_id: str) -> list[dict[str, Any]]:
    invoice_no = _safe_text(invoice.get("invoice_no")) or package_id
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(invoice.get("items") or [], start=1):
        quantity = item.get("quantity") or "1"
        unit_price = item.get("unit_price")
        line_total = item.get("total_price")

        if _money(line_total) == Decimal("0.00") and _money(quantity) and _money(unit_price):
            line_total = _money(quantity) * _money(unit_price)
        if _money(unit_price) == Decimal("0.00") and _money(quantity):
            unit_price = _money(line_total) / _money(quantity)

        rows.append(
            {
                "integration_id": package_id,
                "invoice_no": invoice_no,
                "line_no": index,
                "product_code": _safe_text(item.get("code") or item.get("product_code") or index),
                "description": _safe_text(item.get("description") or item.get("name") or "Item"),
                "unit": _safe_text(item.get("unit") or "ADET"),
                "quantity": _fmt_money(quantity),
                "unit_price": _fmt_money(unit_price),
                "vat_rate": _tax_rate(invoice, item),
                "line_total": _fmt_money(line_total),
                "warehouse_code": _safe_text(item.get("warehouse_code") or invoice.get("warehouse_code")),
            }
        )
    return rows


def _mapping_template() -> dict[str, Any]:
    return {
        "purpose": "Map the package fields to the MikroV16 import screen or approved SDK/stored procedures.",
        "strategy": "file_import_first",
        "files": {
            "customers.csv": CUSTOMER_COLUMNS,
            "invoice_headers.csv": HEADER_COLUMNS,
            "invoice_lines.csv": LINE_COLUMNS,
        },
        "notes": [
            "Use ODBC/SQL for read-only matching unless a Mikro consultant approves write procedures.",
            "Keep integration_id as the external reference to prevent duplicate imports.",
            "Adjust customer_code/product_code mapping for the local Mikro company database.",
        ],
    }


def build_mikro_v16_invoice_package(
    invoice_data: dict[str, Any],
    output_dir: str | os.PathLike[str] = DEFAULT_OUTPUT_DIR,
    source_system: str = "TOS",
    ledger_path: str | os.PathLike[str] = DEFAULT_LEDGER_PATH,
) -> MikroExportResult:
    invoice = copy.deepcopy(invoice_data or {})
    is_valid, errors = validate_invoice(invoice)
    if not is_valid:
        raise MikroBridgeError("Invoice is not valid for MikroV16 export: " + "; ".join(errors))

    package_id = stable_package_id(invoice, source_system=source_system)
    output_root = Path(output_dir)
    ledger = Path(ledger_path)
    existing = _read_ledger_record(ledger, package_id)
    package_dir = output_root / f"{datetime.now():%Y%m%d_%H%M%S}_{_slug(package_id)}"
    package_dir.mkdir(parents=True, exist_ok=True)

    header_path = package_dir / "invoice_headers.csv"
    lines_path = package_dir / "invoice_lines.csv"
    customers_path = package_dir / "customers.csv"
    mapping_path = package_dir / "field_map.example.json"
    manifest_path = package_dir / "manifest.json"

    header_row = _build_header_row(invoice, package_id, source_system)
    line_rows = _build_line_rows(invoice, package_id)
    customer_row = _build_customer_row(invoice, source_system)

    _write_csv(header_path, HEADER_COLUMNS, [header_row])
    _write_csv(lines_path, LINE_COLUMNS, line_rows)
    _write_csv(customers_path, CUSTOMER_COLUMNS, [customer_row])
    mapping_path.write_text(json.dumps(_mapping_template(), ensure_ascii=False, indent=2), encoding="utf-8")

    files = [str(customers_path), str(header_path), str(lines_path), str(mapping_path)]
    manifest = {
        "package_id": package_id,
        "source_system": source_system,
        "target_system": "MikroV16",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "already_exported": existing is not None,
        "previous_export": existing,
        "invoice": {
            "invoice_no": header_row["invoice_no"],
            "issue_date": header_row["issue_date"],
            "customer_tax_id": header_row["customer_tax_id"],
            "total_amount": header_row["total_amount"],
            "line_count": len(line_rows),
        },
        "files": [Path(file_path).name for file_path in files],
        "recommended_flow": [
            "Import customers.csv first if the customer does not exist.",
            "Import invoice_headers.csv and invoice_lines.csv with integration_id as external reference.",
            "Use MikroV16 UI import/approved SDK import mapping; avoid direct production table writes.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files.append(str(manifest_path))

    _record_ledger(ledger, package_id, package_dir, source_system)

    message = "MikroV16 import package created."
    if existing:
        message = "MikroV16 import package created; this invoice was exported before."

    return MikroExportResult(
        success=True,
        message=message,
        package_id=package_id,
        package_dir=str(package_dir),
        files=files,
        manifest=manifest,
        already_exported=existing is not None,
    )


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\[\].]+", value or ""):
        raise MikroBridgeError(f"Unsafe SQL identifier: {value}")
    return value


def _ensure_readonly_sql(sql: str) -> str:
    sql = (sql or "").strip()
    if not re.match(r"^(select|with)\b", sql, flags=re.IGNORECASE):
        raise MikroBridgeError("Only read-only SELECT queries are allowed.")
    if re.search(r"\b(insert|update|delete|drop|alter|truncate|merge|exec|execute|create)\b", sql, re.IGNORECASE):
        raise MikroBridgeError("The query contains a write or DDL command.")
    return sql


class MikroV16SqlClient:
    """Read-only MikroV16 SQL Server helper for matching customers/products."""

    def __init__(self, connection_string: str | None = None, timeout: int = 10):
        self.connection_string = connection_string or os.getenv("MIKRO_V16_ODBC_CONNECTION", "")
        self.timeout = timeout

    def _connect(self):
        if not self.connection_string:
            raise MikroBridgeError("MIKRO_V16_ODBC_CONNECTION is not configured.")
        try:
            import pyodbc  # type: ignore
        except ImportError as exc:
            raise MikroBridgeError("pyodbc is required for ODBC access. Install it on the Mikro workstation.") from exc
        return pyodbc.connect(self.connection_string, timeout=self.timeout, autocommit=True)

    def test_connection(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            row = cursor.execute("SELECT 1 AS ok").fetchone()
            return {"success": bool(row and row[0] == 1), "message": "MikroV16 SQL connection is reachable."}
        finally:
            conn.close()

    def execute_readonly_query(self, sql: str, params: Iterable[Any] = (), limit: int = 100) -> list[dict[str, Any]]:
        sql = _ensure_readonly_sql(sql)
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            columns = [column[0] for column in cursor.description or []]
            rows = cursor.fetchmany(max(1, int(limit)))
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def fetch_customers(self, limit: int = 100) -> list[dict[str, Any]]:
        table = _safe_identifier(os.getenv("MIKRO_CUSTOMER_TABLE", "CARI_HESAPLAR"))
        code_col = _safe_identifier(os.getenv("MIKRO_CUSTOMER_CODE_COL", "cari_kod"))
        title_col = _safe_identifier(os.getenv("MIKRO_CUSTOMER_TITLE_COL", "cari_unvan1"))
        tax_col = _safe_identifier(os.getenv("MIKRO_CUSTOMER_TAX_COL", "cari_vdaire_no"))
        sql = f"SELECT TOP ({int(limit)}) {code_col} AS code, {title_col} AS title, {tax_col} AS tax_id FROM {table} ORDER BY {code_col}"
        return self.execute_readonly_query(sql, limit=limit)

    def fetch_products(self, limit: int = 100) -> list[dict[str, Any]]:
        table = _safe_identifier(os.getenv("MIKRO_PRODUCT_TABLE", "STOKLAR"))
        code_col = _safe_identifier(os.getenv("MIKRO_PRODUCT_CODE_COL", "sto_kod"))
        title_col = _safe_identifier(os.getenv("MIKRO_PRODUCT_TITLE_COL", "sto_isim"))
        sql = f"SELECT TOP ({int(limit)}) {code_col} AS code, {title_col} AS title FROM {table} ORDER BY {code_col}"
        return self.execute_readonly_query(sql, limit=limit)
