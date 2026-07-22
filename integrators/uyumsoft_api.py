from __future__ import annotations

import os
import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from defusedxml import ElementTree as ET

from xml.sax.saxutils import escape
import urllib.request
from datetime import datetime, timedelta
from utils.money_to_text import amount_to_turkish_text
from utils.serial_numbers import normalize_serial_numbers
from utils.invoice_values import (
    DOCUMENT_AMOUNT_TOLERANCE,
    MONEY_QUANTUM,
    format_decimal,
    normalize_currency as normalize_invoice_currency,
    parse_localized_decimal,
    quantize_money,
)

def get_tcmb_rate(currency_code, date_str):
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        date_obj = datetime.now()

    max_days_back = 10
    for _ in range(max_days_back):
        url_date = date_obj.strftime("%Y%m/%d%m%Y")
        url = f"https://www.tcmb.gov.tr/kurlar/{url_date}.xml"
        if date_obj.date() == datetime.now().date():
            url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as response:
                xml_data = response.read()
            tree = ET.fromstring(xml_data)
            
            for currency in tree.findall('Currency'):
                if currency.get('CurrencyCode') == currency_code:
                    forex_buying = currency.find('ForexBuying')
                    if forex_buying is not None and forex_buying.text:
                        return forex_buying.text
        except HTTPError as e:
            if e.code == 404:
                date_obj -= timedelta(days=1)
                continue
            else:
                break
        except Exception:
            break
            
        date_obj -= timedelta(days=1)
            
    return None



TEST_ENDPOINT = "https://efatura-test.uyumsoft.com.tr/Services/Integration"
PROD_ENDPOINT = "https://efatura.uyumsoft.com.tr/Services/Integration"
TEMPURI_NS = "http://tempuri.org/"
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
UBL_INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


def normalize_uyumsoft_environment(value: Any = None) -> str:
    """Return the only two supported environment names, defaulting safely to test."""
    raw = os.getenv("UYUMSOFT_ENV", "test") if value is None else value
    return "prod" if str(raw).strip().lower() == "prod" else "test"


def _server_credentials(environment: str) -> tuple[str, str]:
    """Resolve credentials exclusively from server-side environment variables."""
    if environment == "prod":
        username = os.getenv("UYUMSOFT_PROD_USERNAME") or os.getenv("UYUMSOFT_USERNAME")
        password = os.getenv("UYUMSOFT_PROD_PASSWORD") or os.getenv("UYUMSOFT_PASSWORD")
    else:
        username = (
            os.getenv("UYUMSOFT_TEST_USERNAME")
            or os.getenv("UYUMSOFT_USERNAME")
            or "Uyumsoft"
        )
        password = (
            os.getenv("UYUMSOFT_TEST_PASSWORD")
            or os.getenv("UYUMSOFT_PASSWORD")
            or "Uyumsoft"
        )
    return username or "", password or ""


class UyumsoftSoapError(RuntimeError):
    pass


@dataclass
class UyumsoftResult:
    success: bool
    message: str
    status_code: int
    operation: str
    values: list[dict[str, Any]]
    raw_xml: str


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _money(value: Any, *, field_name: str = "amount") -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    parsed = parse_localized_decimal(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be numeric")
    return parsed


def _fmt_money(value: Decimal) -> str:
    return f"{quantize_money(value):.2f}"


def _fmt_quantity(value: Decimal) -> str:
    return format_decimal(value, max_places=6)


def _fmt_unit_price(value: Decimal) -> str:
    return format_decimal(value, max_places=8, min_places=2)


def _fmt_tax_rate(value: Decimal) -> str:
    """Keep the tax precision used by the calculation in the emitted UBL."""
    return format_decimal(value, max_places=4, min_places=2)


def _xml_attribute(value: Any) -> str:
    """Escape a value that is interpolated into a double-quoted XML attribute."""
    return escape(str(value), {'"': "&quot;", "'": "&apos;"})


def _resolve_invoice_no(value: Any) -> str:
    # An empty number is intentional: Uyumsoft may assign it while creating
    # the draft.  The wrapper and embedded UBL must carry the same value.
    return str(value or "").strip()


def _parse_date(value: Any) -> str:
    if not value:
        return datetime.now().date().isoformat()

    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text[:10]


def _parse_time(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None

    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    raise ValueError("time must use HH:MM or HH:MM:SS format")


def _scheme_id(tax_id: str) -> str:
    return "TCKN" if len(tax_id) == 11 else "VKN"


def _tax_rate(invoice: dict[str, Any]) -> Decimal:
    explicit = invoice.get("tax_rate")
    if explicit not in (None, ""):
        return _money(explicit)

    subtotal = _money(invoice.get("subtotal"))
    tax_amount = _money(invoice.get("tax_amount"))
    if subtotal > 0 and tax_amount > 0:
        return (tax_amount / subtotal * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return Decimal("0.00")


def normalize_currency(value):
    return normalize_invoice_currency(value)


def _customer_display_name(invoice: dict[str, Any], customer_tax_id: str) -> str:
    name = (
        invoice.get("customer_name")
        or invoice.get("customer_title")
        or invoice.get("customer")
    )
    if name:
        return " ".join(str(name).split())
    if customer_tax_id and customer_tax_id != "0000000000":
        return f"MUSTERI {customer_tax_id}"
    return "BILINMEYEN MUSTERI"


def _customer_party_name_xml(customer_name: str, customer_scheme: str) -> str:
    """Build customer name XML without duplicating TCKN display names.

    Uyumsoft renders a TCKN party by joining Person/FirstName and
    Person/FamilyName.  Writing the full display name into both elements made
    the portal show values such as ``ALPER23 ALPER23``.  Split a multi-word
    name once; for a single-token name, emit only FirstName.
    """
    normalized_name = " ".join(str(customer_name or "").split())
    escaped_name = escape(normalized_name)

    if customer_scheme != "TCKN":
        return f"<cac:PartyName><cbc:Name>{escaped_name}</cbc:Name></cac:PartyName>"

    name_parts = normalized_name.rsplit(maxsplit=1)
    first_name = escape(name_parts[0])
    family_name_xml = (
        f"<cbc:FamilyName>{escape(name_parts[1])}</cbc:FamilyName>"
        if len(name_parts) == 2
        else ""
    )
    return (
        f"<cac:Person><cbc:FirstName>{first_name}</cbc:FirstName>"
        f"{family_name_xml}</cac:Person>"
    )


def _allocate_discount_shares(
    line_totals: list[Decimal], discount: Decimal
) -> list[Decimal]:
    if not line_totals:
        return []
    subtotal = sum(line_totals, Decimal("0.00"))
    if subtotal <= 0 or discount <= 0:
        return [Decimal("0.00") for _ in line_totals]

    capacities = [
        int((quantize_money(max(line_total, Decimal("0.00"))) * 100).to_integral_value())
        for line_total in line_totals
    ]
    discount_cents = int((quantize_money(discount) * 100).to_integral_value())
    capacity_cents = sum(capacities)
    if discount_cents > capacity_cents:
        raise ValueError("discount_amount cannot exceed line totals")

    exact_shares = [
        Decimal(discount_cents) * Decimal(capacity) / Decimal(capacity_cents)
        for capacity in capacities
    ]
    allocated_cents = [
        min(capacity, int(exact.to_integral_value(rounding=ROUND_FLOOR)))
        for capacity, exact in zip(capacities, exact_shares)
    ]
    remaining = discount_cents - sum(allocated_cents)
    distribution_order = sorted(
        range(len(capacities)),
        key=lambda index: (
            exact_shares[index] - Decimal(allocated_cents[index]),
            capacities[index],
            -index,
        ),
        reverse=True,
    )
    while remaining:
        progressed = False
        for index in distribution_order:
            if allocated_cents[index] >= capacities[index]:
                continue
            allocated_cents[index] += 1
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:
            raise ValueError("discount_amount could not be allocated across invoice lines")

    return [Decimal(cents) / Decimal("100") for cents in allocated_cents]


def build_ubl_invoice(invoice: dict[str, Any]) -> str:
    if not isinstance(invoice, dict):
        raise ValueError("invoice must be an object")

    invoice_no = _resolve_invoice_no(invoice.get("invoice_no"))
    issue_date = _parse_date(invoice.get("date"))
    issue_time = _parse_time(invoice.get("time"))
    issue_time_xml = (
        f"\n  <cbc:IssueTime>{escape(issue_time)}</cbc:IssueTime>"
        if issue_time
        else ""
    )
        
    currency = normalize_currency(
        invoice.get("currency") or os.getenv("UYUMSOFT_CURRENCY", "TRY")
    )
    profile_id = str(invoice.get("profile_id") or os.getenv("UYUMSOFT_PROFILE_ID", "TICARIFATURA"))
    invoice_type = str(invoice.get("invoice_type") or os.getenv("UYUMSOFT_INVOICE_TYPE", "SATIS"))
    
    extracted_notes = str(invoice.get("notes") or "").strip()
    notes_xml = f"\n  <cbc:Note>{escape(extracted_notes)}</cbc:Note>" if extracted_notes else ""

    environment = normalize_uyumsoft_environment()
    default_supplier_vkn = "9000068418" if environment == "test" else ""
    default_supplier_name = (
        "UYUMSOFT BILGI SISTEMLERI VE TEKNOLOJILERI TICARET ANONIM SIRKETI"
        if environment == "test"
        else ""
    )
    supplier_tax_id = "".join(filter(str.isdigit, str(
        invoice.get("supplier_tax_id")
        or os.getenv("UYUMSOFT_SUPPLIER_VKN", default_supplier_vkn)
    )))
    if len(supplier_tax_id) not in (10, 11):
        raise ValueError("supplier_tax_id must contain 10 or 11 digits")
    supplier_name = str(
        invoice.get("supplier_name")
        or os.getenv("UYUMSOFT_SUPPLIER_NAME", default_supplier_name)
    )
    supplier_tax_office = str(
        invoice.get("supplier_tax_office") or os.getenv("UYUMSOFT_SUPPLIER_TAX_OFFICE", "")
    )

    customer_tax_id_raw = str(invoice.get("customer_tax_id") or "").strip()
    customer_tax_id = "".join(filter(str.isdigit, customer_tax_id_raw))
    if len(customer_tax_id) == 12 and set(customer_tax_id) == {"1"}:
        customer_tax_id = "11111111111"
    if len(customer_tax_id) not in (10, 11):
        raise ValueError("customer_tax_id must contain 10 or 11 digits")
        
    customer_name = _customer_display_name(invoice, customer_tax_id)

    items = invoice.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    rate = _tax_rate(invoice)
    parsed_items: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"item {index} must be an object")
        quantity = _money(item.get("quantity"), field_name=f"item {index} quantity")
        unit_price = _money(item.get("unit_price"), field_name=f"item {index} unit_price")
        line_total = quantize_money(
            _money(item.get("total_price"), field_name=f"item {index} total_price")
        )
        if quantity <= 0 or unit_price < 0 or line_total < 0:
            raise ValueError(f"item {index} contains invalid numeric values")

        item_rate_value = item.get("tax_rate")
        item_rate = _money(
            item_rate_value if item_rate_value not in (None, "") else rate,
            field_name=f"item {index} tax_rate",
        )
        if item_rate < 0 or item_rate > 100:
            raise ValueError(f"item {index} tax_rate must be between 0 and 100")

        description_value = item.get("description") or item.get("name")
        description_text = str(description_value or "").strip()
        if not description_text:
            raise ValueError(f"item {index} description cannot be empty")
        serial_numbers = normalize_serial_numbers(item.get("serial_numbers"))
        if serial_numbers:
            if quantity != quantity.to_integral_value():
                raise ValueError(
                    f"item {index} quantity must be an integer when serial numbers are supplied"
                )
            if len(serial_numbers) != int(quantity):
                raise ValueError(
                    f"item {index} serial count must equal its quantity"
                )

        parsed_items.append(
            {
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
                "tax_rate": item_rate,
                "description": description_text,
                "code": str(item.get("code") or "").strip(),
                "serial_numbers": serial_numbers,
            }
        )

    calculated_subtotal = quantize_money(
        sum((item["line_total"] for item in parsed_items), Decimal("0.00"))
    )
    discount_amount = quantize_money(
        _money(invoice.get("discount_amount"), field_name="discount_amount")
    )
    if discount_amount < 0 or discount_amount > calculated_subtotal:
        raise ValueError("discount_amount must be between zero and subtotal")

    supplied_subtotal = _money(invoice.get("subtotal"), field_name="subtotal")
    if invoice.get("subtotal") not in (None, ""):
        supplied_q = quantize_money(supplied_subtotal)
        if (
            abs(supplied_q - calculated_subtotal) > DOCUMENT_AMOUNT_TOLERANCE
            and abs(supplied_q - quantize_money(calculated_subtotal - discount_amount))
            > DOCUMENT_AMOUNT_TOLERANCE
        ):
            raise ValueError("invoice subtotal does not match line totals")

    discount_shares = _allocate_discount_shares(
        [item["line_total"] for item in parsed_items], discount_amount
    )
    tax_subtotals: dict[Decimal, dict[str, Decimal]] = {}
    line_xml: list[str] = []
    calculated_tax = Decimal("0.00")

    for index, (item, discount_share) in enumerate(
        zip(parsed_items, discount_shares), start=1
    ):
        quantity = item["quantity"]
        unit_price = item["unit_price"]
        line_total = item["line_total"]
        item_rate = item["tax_rate"]
        taxable_amount = line_total - discount_share
        line_tax = quantize_money(taxable_amount * item_rate / Decimal("100"))
        calculated_tax += line_tax

        group = tax_subtotals.setdefault(
            item_rate,
            {"gross": Decimal("0.00"), "discount": Decimal("0.00"),
             "taxable": Decimal("0.00"), "tax": Decimal("0.00")},
        )
        group["gross"] += line_total
        group["discount"] += discount_share
        group["taxable"] += taxable_amount
        group["tax"] += line_tax

        code_text = item["code"]
        sellers_item_xml = (
            "\n      <cac:SellersItemIdentification>"
            f"<cbc:ID>{escape(code_text)}</cbc:ID>"
            "</cac:SellersItemIdentification>"
            if code_text
            else ""
        )
        item_instances_xml = "".join(
            "\n      <cac:ItemInstance>"
            f"<cbc:SerialID>{escape(serial_number)}</cbc:SerialID>"
            "</cac:ItemInstance>"
            for serial_number in item["serial_numbers"]
        )
        line_xml.append(
            f"""
  <cac:InvoiceLine>
    <cbc:ID>{index}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">{_fmt_quantity(quantity)}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{currency}">{_fmt_money(line_total)}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="{currency}">{_fmt_money(line_tax)}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{currency}">{_fmt_money(taxable_amount)}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{currency}">{_fmt_money(line_tax)}</cbc:TaxAmount>
        <cbc:Percent>{_fmt_tax_rate(item_rate)}</cbc:Percent>
        <cac:TaxCategory>
          <cac:TaxScheme>
            <cbc:Name>KDV</cbc:Name>
            <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
          </cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Name>{escape(item["description"])}</cbc:Name>{sellers_item_xml}{item_instances_xml}
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="{currency}">{_fmt_unit_price(unit_price)}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>"""
        )

    calculated_tax = quantize_money(calculated_tax)
    supplied_tax = _money(invoice.get("tax_amount"), field_name="tax_amount")
    if (
        invoice.get("tax_amount") not in (None, "")
        and abs(quantize_money(supplied_tax) - calculated_tax)
        > DOCUMENT_AMOUNT_TOLERANCE
    ):
        raise ValueError("invoice tax_amount does not match line tax calculation")
    line_extension_amount = calculated_subtotal
    taxable_amount = calculated_subtotal - discount_amount
    total_amount = quantize_money(taxable_amount + calculated_tax)
    supplied_total = _money(invoice.get("total_amount"), field_name="total_amount")
    if (
        invoice.get("total_amount") not in (None, "")
        and abs(quantize_money(supplied_total) - total_amount)
        > DOCUMENT_AMOUNT_TOLERANCE
    ):
        raise ValueError("invoice total_amount does not match calculated total")
    tax_amount = calculated_tax

    supplier_scheme = _scheme_id(supplier_tax_id)
    customer_scheme = _scheme_id(customer_tax_id)
    customer_party_name_xml = _customer_party_name_xml(customer_name, customer_scheme)

    allowance_charge_parts = []
    if discount_amount > 0:
        for tax_rate, amounts in tax_subtotals.items():
            if amounts["discount"] <= 0:
                continue
            allowance_charge_parts.append(f"""
  <cac:AllowanceCharge>
    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:Amount currencyID="{currency}">{_fmt_money(amounts["discount"])}</cbc:Amount>
    <cac:TaxCategory>
      <cbc:Percent>{_fmt_tax_rate(tax_rate)}</cbc:Percent>
      <cac:TaxScheme><cbc:Name>KDV</cbc:Name><cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme>
    </cac:TaxCategory>
  </cac:AllowanceCharge>""")
    allowance_charge_xml = "".join(allowance_charge_parts)

    text_amount = amount_to_turkish_text(total_amount, currency)
    notes_xml += f"\n  <cbc:Note>{escape(text_amount)}</cbc:Note>"

    doc_tax_subtotals_xml = []
    for t_rate, t_amounts in tax_subtotals.items():
        doc_tax_subtotals_xml.append(f"""
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{currency}">{_fmt_money(t_amounts["taxable"])}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{currency}">{_fmt_money(t_amounts["tax"])}</cbc:TaxAmount>
      <cbc:Percent>{_fmt_tax_rate(t_rate)}</cbc:Percent>
      <cac:TaxCategory>
        <cac:TaxScheme>
          <cbc:Name>KDV</cbc:Name>
          <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
        </cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>""")
    doc_tax_subtotal_str = "".join(doc_tax_subtotals_xml)

    allowance_total_xml = f'\n    <cbc:AllowanceTotalAmount currencyID="{currency}">{_fmt_money(discount_amount)}</cbc:AllowanceTotalAmount>' if discount_amount > Decimal("0.00") else ""

    pricing_exchange_rate_xml = ""
    if currency != "TRY":
        rate_val = invoice.get("exchange_rate")
        rate_decimal = _money(rate_val, field_name="exchange rate") if rate_val not in (None, "") else Decimal("0")
        if rate_decimal <= Decimal("0"):
            looked_up_rate = get_tcmb_rate(currency, issue_date)
            if looked_up_rate in (None, ""):
                raise ValueError(f"exchange rate could not be obtained for {currency}")
            rate_decimal = _money(looked_up_rate, field_name="exchange rate")
        if rate_decimal <= Decimal("0"):
            raise ValueError(f"exchange rate must be positive for {currency}")
        rate_val_fmt = format_decimal(rate_decimal, max_places=8, min_places=4)
            
        pricing_exchange_rate_xml = f'''
  <cac:PricingExchangeRate>
    <cbc:SourceCurrencyCode>{currency}</cbc:SourceCurrencyCode>
    <cbc:TargetCurrencyCode>TRY</cbc:TargetCurrencyCode>
    <cbc:CalculationRate>{rate_val_fmt}</cbc:CalculationRate>
    <cbc:Date>{issue_date}</cbc:Date>
  </cac:PricingExchangeRate>'''


    return f"""<Invoice xmlns="{UBL_INVOICE_NS}" xmlns:cac="{CAC_NS}" xmlns:cbc="{CBC_NS}">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>{escape(profile_id)}</cbc:ProfileID>
  <cbc:ID>{escape(invoice_no)}</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:UUID>{uuid.uuid4()}</cbc:UUID>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>{issue_time_xml}
  <cbc:InvoiceTypeCode>{escape(invoice_type)}</cbc:InvoiceTypeCode>{notes_xml}
  <cbc:DocumentCurrencyCode>{currency}</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>{len(items)}</cbc:LineCountNumeric>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyIdentification><cbc:ID schemeID="{supplier_scheme}">{escape(supplier_tax_id)}</cbc:ID></cac:PartyIdentification>
      <cac:PartyName><cbc:Name>{escape(supplier_name)}</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:Name>{escape(supplier_tax_office)}</cbc:Name>
        <cac:TaxScheme><cbc:Name>{escape(supplier_tax_office)}</cbc:Name></cac:TaxScheme>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyIdentification><cbc:ID schemeID="{customer_scheme}">{escape(customer_tax_id)}</cbc:ID></cac:PartyIdentification>
      {customer_party_name_xml}
    </cac:Party>
  </cac:AccountingCustomerParty>
  {allowance_charge_xml}{pricing_exchange_rate_xml}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{currency}">{_fmt_money(tax_amount)}</cbc:TaxAmount>
    {doc_tax_subtotal_str}
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{currency}">{_fmt_money(line_extension_amount)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{currency}">{_fmt_money(taxable_amount)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{currency}">{_fmt_money(total_amount)}</cbc:TaxInclusiveAmount>{allowance_total_xml}
    <cbc:PayableAmount currencyID="{currency}">{_fmt_money(total_amount)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
{''.join(line_xml)}
</Invoice>"""


def build_uyumsoft_invoice_element(invoice: dict[str, Any], element_name: str = "Invoice") -> str:
    """Wrap the UBL invoice in the WCF element namespace Uyumsoft expects."""
    ubl = build_ubl_invoice(invoice)
    ubl = ubl.replace(
        f'<Invoice xmlns="{UBL_INVOICE_NS}"',
        f'<{element_name} xmlns="{TEMPURI_NS}"',
        1,
    )
    return ubl.replace("</Invoice>", f"</{element_name}>", 1)


class UyumsoftSoapClient:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        environment: str = "test",
        endpoint: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.username = username
        self.password = password
        normalized_environment = normalize_uyumsoft_environment(environment)
        self.endpoint = endpoint or (
            PROD_ENDPOINT if normalized_environment == "prod" else TEST_ENDPOINT
        )
        self.timeout = timeout

    def test_connection(self) -> UyumsoftResult:
        return self._call("TestConnection", '<TestConnection xmlns="http://tempuri.org/" />')

    def filter_e_invoice_users(self, vkn_tckn: str, page_size: int = 10) -> UyumsoftResult:
        return self._call("FilterEInvoiceUsers", build_filter_e_invoice_users_body(vkn_tckn, page_size))

    def get_user_aliases(self, vkn_tckn: str) -> UyumsoftResult:
        safe_vkn = escape("".join(filter(str.isdigit, str(vkn_tckn or ""))))
        return self._call(
            "GetUserAliasses",
            f'<GetUserAliasses xmlns="http://tempuri.org/"><vknTckn>{safe_vkn}</vknTckn></GetUserAliasses>',
        )

    def validate_invoice_data(self, invoice: dict[str, Any]) -> UyumsoftResult:
        return self._call("ValidateInvoice", build_validate_invoice_body(invoice))

    def save_as_draft_data(self, invoice: dict[str, Any]) -> UyumsoftResult:
        return self._send_invoice_info("SaveAsDraft", invoice)

    def send_invoice_data(self, invoice: dict[str, Any]) -> UyumsoftResult:
        return self._send_invoice_info("SendInvoice", invoice)

    def _send_invoice_info(self, operation: str, invoice: dict[str, Any]) -> UyumsoftResult:
        return self._call(operation, build_invoice_info_body(operation, invoice))

    def _call(self, operation: str, operation_body: str) -> UyumsoftResult:
        envelope = self._envelope(operation_body)
        request = Request(
            self.endpoint,
            data=envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"http://tempuri.org/IIntegration/{operation}"',
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_xml = response.read().decode("utf-8", errors="replace")
                status_code = response.status
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise UyumsoftSoapError(f"HTTP {exc.code} for URL {request.full_url}: {raw[:1000]}") from exc
        except URLError as exc:
            raise UyumsoftSoapError(str(exc.reason)) from exc

        return self._parse_result(operation, status_code, raw_xml)

    def _envelope(self, operation_body: str) -> str:
        return build_soap_envelope(self.username, self.password, operation_body)

    def _parse_result(self, operation: str, status_code: int, raw_xml: str) -> UyumsoftResult:
        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError as e:
            return UyumsoftResult(False, f"SOAP parse error: {str(e)}", status_code, operation, [], raw_xml)
            
        fault = next((node for node in root.iter() if _local_name(node.tag) == "Fault"), None)
        if fault is not None:
            fault_text = " ".join(text.strip() for text in fault.itertext() if text and text.strip())
            return UyumsoftResult(False, fault_text or "SOAP fault", status_code, operation, [], raw_xml)

        result_node = next(
            (node for node in root.iter() if _local_name(node.tag) == f"{operation}Result"),
            None,
        )
        if result_node is None:
            return UyumsoftResult(False, "SOAP result node not found", status_code, operation, [], raw_xml)

        success = result_node.attrib.get("IsSucceded", "").lower() == "true"
        message = result_node.attrib.get("Message") or ("OK" if success else "Failed")
        values: list[dict[str, Any]] = []

        for child in result_node:
            if _local_name(child.tag) != "Value":
                continue
            value: dict[str, Any] = dict(child.attrib)
            for grandchild in child:
                value[_local_name(grandchild.tag)] = grandchild.text
            if child.text and child.text.strip():
                value["text"] = child.text.strip()
            values.append(value)

        return UyumsoftResult(success, message, status_code, operation, values, raw_xml)


def build_filter_e_invoice_users_body(vkn_tckn: str, page_size: int = 10) -> str:
    safe_filter = escape("".join(filter(str.isdigit, str(vkn_tckn or ""))))
    safe_page_size = max(1, min(int(page_size or 10), 50))
    nil_dt = ' xsi:nil="true"'
    return f"""
<FilterEInvoiceUsers xmlns="http://tempuri.org/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <context PageIndex="0" PageSize="{safe_page_size}">
    <Filter>{safe_filter}</Filter>
    <SystemCreateDateBegin{nil_dt} />
    <SystemCreateDateEnd{nil_dt} />
    <FirstCreateDateBegin{nil_dt} />
    <FirstCreateDateEnd{nil_dt} />
    <UpdateDateBegin{nil_dt} />
    <UpdateDateEnd{nil_dt} />
  </context>
</FilterEInvoiceUsers>"""


def _extract_system_user_values(result: UyumsoftResult) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = [
        dict(value) for value in result.values if isinstance(value, dict)
    ]
    try:
        root = ET.fromstring(result.raw_xml)
    except ET.ParseError:
        return users

    for node in root.iter():
        attrs = dict(node.attrib)
        for child in node:
            child_name = _local_name(child.tag)
            if child.text and child.text.strip() and child_name in {
                "Identifier",
                "Title",
                "PostboxAlias",
                "Alias",
            }:
                attrs[child_name] = child.text.strip()
        if any(
            attrs.get(key)
            for key in ("Title", "Identifier", "PostboxAlias", "Alias")
        ):
            users.append(attrs)
    return users


def _best_uyumsoft_user_match(result: UyumsoftResult, vkn_tckn: str) -> dict[str, Any] | None:
    target = "".join(filter(str.isdigit, str(vkn_tckn or "")))
    if len(target) not in (10, 11):
        return None

    for user in _extract_system_user_values(result):
        identifier = "".join(filter(str.isdigit, str(user.get("Identifier") or "")))
        if identifier == target and user.get("Title"):
            return user

    return None


def _best_uyumsoft_alias_match(
    result: UyumsoftResult, vkn_tckn: str
) -> dict[str, Any] | None:
    """Find an alias returned for a queried taxpayer, including alias-only rows."""
    target = "".join(filter(str.isdigit, str(vkn_tckn or "")))
    if len(target) not in (10, 11):
        return None

    alias_only_match = None
    for user in _extract_system_user_values(result):
        alias = str(user.get("PostboxAlias") or user.get("Alias") or "").strip()
        if not alias:
            continue
        identifier = "".join(filter(str.isdigit, str(user.get("Identifier") or "")))
        if identifier == target:
            return user
        if not identifier and alias_only_match is None:
            # GetUserAliasses is already scoped by the queried VKN/TCKN, and
            # some Uyumsoft responses contain only the alias value.
            alias_only_match = user
    return alias_only_match


def enrich_invoice_customer_from_uyumsoft(invoice_data: dict[str, Any]) -> dict[str, Any]:
    """Fill customer name/title from Uyumsoft taxpayer list when VKN/TCKN is available.

    This is best-effort by design. A lookup failure must not stop PDF extraction,
    validation, or invoice transfer.
    """
    if not isinstance(invoice_data, dict):
        return invoice_data

    target_vkn = "".join(filter(str.isdigit, str(invoice_data.get("customer_tax_id") or "")))
    if (
        invoice_data.get("_uyumsoft_customer_lookup") == "matched"
        and invoice_data.get("customer_alias_tax_id") == target_vkn
        and invoice_data.get("customer_alias")
        and (
        invoice_data.get("customer_title") or invoice_data.get("customer_name")
        )
    ):
        return invoice_data

    if invoice_data.get("customer_alias_tax_id") != target_vkn:
        invoice_data.pop("customer_alias", None)
        invoice_data.pop("customer_alias_tax_id", None)
        invoice_data.pop("_uyumsoft_customer_lookup", None)

    if os.getenv("UYUMSOFT_CUSTOMER_LOOKUP", "1").lower() in {"0", "false", "no", "off"}:
        return invoice_data

    if len(target_vkn) not in (10, 11):
        return invoice_data

    environment = normalize_uyumsoft_environment()
    username, password = _server_credentials(environment)
    if not username or not password:
        return invoice_data

    client = UyumsoftSoapClient(
        username,
        password,
        environment=environment,
        timeout=int(os.getenv("UYUMSOFT_LOOKUP_TIMEOUT", "8")),
    )

    lookup_failures = []
    result = None
    aliases_result = None
    try:
        result = client.filter_e_invoice_users(target_vkn, page_size=10)
    except Exception as exc:
        lookup_failures.append(f"filter: {type(exc).__name__}: {str(exc)}")
    try:
        aliases_result = client.get_user_aliases(target_vkn)
    except Exception as exc:
        lookup_failures.append(f"aliases: {type(exc).__name__}: {str(exc)}")

    title_match = (
        _best_uyumsoft_user_match(result, target_vkn) if result is not None else None
    )
    alias_match = (
        _best_uyumsoft_alias_match(aliases_result, target_vkn)
        if aliases_result is not None
        else None
    ) or (
        _best_uyumsoft_alias_match(result, target_vkn) if result is not None else None
    )

    if not title_match and not alias_match:
        invoice_data["_uyumsoft_customer_lookup"] = (
            f"failed: {'; '.join(lookup_failures)}"
            if lookup_failures
            else "not_found"
        )
        return invoice_data

    title = str((title_match or {}).get("Title") or "").strip()
    if title:
        invoice_data["customer_name"] = title
        invoice_data["customer_title"] = title
        invoice_data["_uyumsoft_customer_lookup"] = "matched"

    alias = str(
        (alias_match or {}).get("PostboxAlias")
        or (alias_match or {}).get("Alias")
        or ""
    ).strip()
    if alias:
        invoice_data["customer_alias"] = alias
        invoice_data["customer_alias_tax_id"] = target_vkn
        invoice_data["_uyumsoft_customer_lookup"] = "matched"

    if lookup_failures:
        invoice_data["_uyumsoft_customer_lookup_warning"] = "; ".join(lookup_failures)

    return invoice_data


def build_validate_invoice_body(invoice: dict[str, Any]) -> str:
    invoice_param = build_uyumsoft_invoice_element(invoice, "invoice")
    return f'<ValidateInvoice xmlns="http://tempuri.org/">{invoice_param}</ValidateInvoice>'


def build_invoice_info_body(operation: str, invoice: dict[str, Any]) -> str:
    if operation not in {"SaveAsDraft", "SendInvoice"}:
        raise ValueError("operation must be SaveAsDraft or SendInvoice")

    invoice_for_build = dict(invoice)
    resolved_invoice_no = _resolve_invoice_no(invoice.get("invoice_no"))
    invoice_for_build["invoice_no"] = resolved_invoice_no
    ubl = build_uyumsoft_invoice_element(invoice_for_build, "Invoice")
    local_document_id = _xml_attribute(resolved_invoice_no)
    
    target_vkn_raw = str(invoice.get("customer_tax_id") or "").strip()
    target_vkn = "".join(filter(str.isdigit, target_vkn_raw))
    if len(target_vkn) == 12 and set(target_vkn) == {"1"}:
        target_vkn = "11111111111"
    if len(target_vkn) not in (10, 11):
        raise ValueError("customer_tax_id must contain 10 or 11 digits")
    target_vkn = _xml_attribute(target_vkn)
    
    target_title = _xml_attribute(_customer_display_name(invoice, target_vkn))
    alias_tax_id = "".join(
        filter(str.isdigit, str(invoice.get("customer_alias_tax_id") or ""))
    )
    target_alias = (
        invoice.get("customer_alias") if alias_tax_id == target_vkn else None
    )
    alias_attr = f' Alias="{_xml_attribute(target_alias)}"' if target_alias else ""
    scenario = escape(str(invoice.get("scenario") or os.getenv("UYUMSOFT_SCENARIO", "Automated")))
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return f"""
<{operation} xmlns="http://tempuri.org/">
  <invoices>
    <InvoiceInfo LocalDocumentId="{local_document_id}">
      {ubl}
      <TargetCustomer VknTckn="{target_vkn}" Title="{target_title}"{alias_attr} />
      <Scenario>{scenario}</Scenario>
      <CreateDateUtc>{created_at}</CreateDateUtc>
    </InvoiceInfo>
  </invoices>
</{operation}>"""


def build_soap_envelope(username: str, password: str, operation_body: str) -> str:
    return f"""<s:Envelope xmlns:s="{SOAP_ENV_NS}" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
  <s:Header>
    <wsse:Security s:mustUnderstand="1">
      <wsse:UsernameToken>
        <wsse:Username>{escape(username)}</wsse:Username>
        <wsse:Password>{escape(password)}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </s:Header>
  <s:Body>{operation_body}</s:Body>
</s:Envelope>"""


def send_invoice_to_uyumsoft(
    invoice_data: dict[str, Any],
    action: str | None = None,
    environment: str | None = None,
    prod_username: str | None = None,
    prod_password: str | None = None,
) -> dict[str, Any]:
    if not isinstance(invoice_data, dict):
        return {
            "success": False,
            "message": "Invoice payload must be an object.",
            "details": "A JSON object is required.",
            "response_code": 400,
        }

    # Legacy arguments stay in the signature only for Python call-site
    # compatibility. Deployment configuration exclusively owns endpoint and
    # credentials; callers cannot override either value.
    _ = (environment, prod_username, prod_password)
    server_environment = normalize_uyumsoft_environment()
    username, password = _server_credentials(server_environment)

    if not username or not password:
        return {
            "success": False,
            "message": "UYUMSOFT_USERNAME and UYUMSOFT_PASSWORD must be configured.",
            "details": "Credentials are required before sending invoice data to Uyumsoft.",
            "response_code": 401,
        }

    selected_action = (action or os.getenv("UYUMSOFT_ACTION", "test_connection")).lower()
    if selected_action in {"test", "test_connection"}:
        client = UyumsoftSoapClient(
            username,
            password,
            environment=server_environment,
        )
        try:
            result = client.test_connection()
        except UyumsoftSoapError as exc:
            return {
                "success": False,
                "message": "Uyumsoft SOAP request failed.",
                "details": str(exc),
                "response_code": 502,
            }
        except Exception as exc:
            return {
                "success": False,
                "message": "Internal Uyumsoft Integration Error.",
                "details": f"{type(exc).__name__}: {str(exc)}",
                "response_code": 500,
            }
        return {
            "success": result.success,
            "message": result.message,
            "operation": result.operation,
            "values": result.values,
            "details": result.raw_xml[:2000],
            "response_code": result.status_code,
        }

    default_supplier_vkn = "9000068418" if server_environment == "test" else ""
    default_supplier_name = (
        "UYUMSOFT BILGI SISTEMLERI VE TEKNOLOJILERI TICARET ANONIM SIRKETI"
        if server_environment == "test"
        else ""
    )
    supplier_tax_id = "".join(
        filter(
            str.isdigit,
            str(os.getenv("UYUMSOFT_SUPPLIER_VKN", default_supplier_vkn)),
        )
    )
    supplier_name = str(
        os.getenv("UYUMSOFT_SUPPLIER_NAME", default_supplier_name)
    ).strip()
    supplier_tax_office = str(
        os.getenv("UYUMSOFT_SUPPLIER_TAX_OFFICE", "")
    ).strip()
    if len(supplier_tax_id) not in (10, 11) or not supplier_name:
        if server_environment == "prod":
            return {
                "success": False,
                "message": "Canlı Uyumsoft gönderimi için işyeri bilgileri eksik.",
                "details": (
                    "UYUMSOFT_SUPPLIER_VKN ve UYUMSOFT_SUPPLIER_NAME "
                    "değerlerini sunucu ortamında tanımlayın."
                ),
                "response_code": 422,
            }
        return {
            "success": False,
            "message": "Uyumsoft supplier configuration is invalid.",
            "details": "Configure a 10/11 digit supplier VKN and supplier name.",
            "response_code": 422,
        }

    prepared_invoice = copy.deepcopy(invoice_data)
    prepared_invoice["supplier_tax_id"] = supplier_tax_id
    prepared_invoice["supplier_name"] = supplier_name
    prepared_invoice["supplier_tax_office"] = supplier_tax_office
    for key, env_name in (
        ("profile_id", "UYUMSOFT_PROFILE_ID"),
        ("invoice_type", "UYUMSOFT_INVOICE_TYPE"),
        ("scenario", "UYUMSOFT_SCENARIO"),
    ):
        configured = os.getenv(env_name)
        if configured:
            prepared_invoice[key] = configured

    client = UyumsoftSoapClient(username, password, environment=server_environment)

    if selected_action in {"dry_run", "preview"}:
        try:
            preview_currency = normalize_currency(
                prepared_invoice.get("currency")
                or os.getenv("UYUMSOFT_CURRENCY", "TRY")
            )
            raw_rate = prepared_invoice.get("exchange_rate")
            preview_rate = (
                _money(raw_rate, field_name="exchange rate")
                if raw_rate not in (None, "")
                else Decimal("0")
            )
        except ValueError as exc:
            return {
                "success": False,
                "message": "Dry-run invoice data is invalid.",
                "details": str(exc),
                "response_code": 422,
            }
        if preview_currency != "TRY" and preview_rate <= 0:
            return {
                "success": False,
                "message": "Exchange rate is required for an offline dry-run.",
                "details": (
                    f"Provide a positive exchange_rate for {preview_currency}; "
                    "dry-run never performs a hidden TCMB network lookup."
                ),
                "response_code": 422,
            }

    try:
        if selected_action in {"test", "test_connection"}:
            result = client.test_connection()
        elif selected_action in {"dry_run", "preview"}:
            body = build_invoice_info_body("SaveAsDraft", prepared_invoice)
            ET.fromstring(body)
            return {
                "success": True,
                "message": "Uyumsoft taslak SOAP verisi üretildi; dış servise gönderilmedi.",
                "operation": "DryRun",
                "values": [],
                "details": body[:4000],
                "response_code": 200,
            }
        elif selected_action == "validate":
            result = client.validate_invoice_data(prepared_invoice)
        elif selected_action == "draft":
            result = client.save_as_draft_data(prepared_invoice)
        elif selected_action == "send":
            result = client.send_invoice_data(prepared_invoice)
        else:
            return {
                "success": False,
                "message": f"Unsupported Uyumsoft action: {selected_action}",
                "details": "Use test_connection, validate, draft, or send.",
                "response_code": 400,
            }
    except UyumsoftSoapError as exc:
        return {
            "success": False,
            "message": "Uyumsoft SOAP request failed.",
            "details": str(exc),
            "response_code": 502,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": "Internal Uyumsoft Integration Error.",
            "details": f"{type(exc).__name__}: {str(exc)}",
            "response_code": 500,
        }

    return {
        "success": result.success,
        "message": result.message,
        "operation": result.operation,
        "values": result.values,
        "details": result.raw_xml[:2000],
        "response_code": result.status_code,
    }
