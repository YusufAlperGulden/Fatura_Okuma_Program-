from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from xml.sax.saxutils import escape
import urllib.request
from datetime import datetime, timedelta

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
            with urllib.request.urlopen(req, timeout=5) as response:
                xml_data = response.read()
            tree = ET.fromstring(xml_data)
            
            for currency in tree.findall('Currency'):
                if currency.get('CurrencyCode') == currency_code:
                    forex_selling = currency.find('ForexSelling')
                    if forex_selling is not None and forex_selling.text:
                        return forex_selling.text
        except HTTPError as e:
            if e.code == 404:
                date_obj -= timedelta(days=1)
                continue
        except Exception:
            pass
        date_obj -= timedelta(days=1)
    
    return "1.0000"



TEST_ENDPOINT = "https://efatura-test.uyumsoft.com.tr/Services/Integration"
PROD_ENDPOINT = "https://efatura.uyumsoft.com.tr/Services/Integration"
TEMPURI_NS = "http://tempuri.org/"
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
UBL_INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


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


def _money(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")

    text = str(value).strip().upper()
    for currency in ["₺", "TL", "TRY", "$", "USD", "DOLAR", "€", "EUR", "EURO", "£", "GBP", "%"]:
        text = text.replace(currency, "")
    text = text.replace(" ", "").strip()

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
        elif len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            text = text.replace(".", "")

    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0.00")


def _fmt_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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
    text = str(value or "").strip().upper()

    mapping = {
        "TL": "TRY",
        "TRY": "TRY",
        "₺": "TRY",
        "TÜRK LİRASI": "TRY",
        "TURK LIRASI": "TRY",

        "EURO": "EUR",
        "EUR": "EUR",
        "€": "EUR",

        "DOLAR": "USD",
        "USD": "USD",
        "$": "USD",
        "AMERIKAN DOLARI": "USD",
        "AMERİKAN DOLARI": "USD",
    }

    return mapping.get(text, "TRY")


def _customer_display_name(invoice: dict[str, Any], customer_tax_id: str) -> str:
    name = (
        invoice.get("customer_title")
        or invoice.get("customer_name")
        or invoice.get("customer")
    )
    if name:
        return str(name).strip()
    if customer_tax_id and customer_tax_id != "0000000000":
        return f"MUSTERI {customer_tax_id}"
    return "BILINMEYEN MUSTERI"


def build_ubl_invoice(invoice: dict[str, Any]) -> str:
    invoice_no = str(invoice.get("invoice_no") or f"AUTO-{uuid.uuid4().hex[:12].upper()}")
    issue_date = _parse_date(invoice.get("date"))
    
    extracted_time = invoice.get("time")
    if extracted_time:
        if len(extracted_time) == 5:
            extracted_time += ":00"
        issue_time = extracted_time
    else:
        issue_time = datetime.now().strftime("%H:%M:%S")
        
    currency = normalize_currency(invoice.get("currency") or os.getenv("UYUMSOFT_CURRENCY", "TRY"))
    profile_id = str(invoice.get("profile_id") or os.getenv("UYUMSOFT_PROFILE_ID", "TICARIFATURA"))
    invoice_type = str(invoice.get("invoice_type") or os.getenv("UYUMSOFT_INVOICE_TYPE", "SATIS"))

    supplier_tax_id = str(
        invoice.get("supplier_tax_id") or os.getenv("UYUMSOFT_SUPPLIER_VKN", "9000068418")
    )
    supplier_name = str(
        invoice.get("supplier_name")
        or os.getenv(
            "UYUMSOFT_SUPPLIER_NAME",
            "UYUMSOFT BILGI SISTEMLERI VE TEKNOLOJILERI TICARET ANONIM SIRKETI",
        )
    )
    supplier_tax_office = str(
        invoice.get("supplier_tax_office") or os.getenv("UYUMSOFT_SUPPLIER_TAX_OFFICE", "")
    )

    customer_tax_id_raw = str(invoice.get("customer_tax_id") or "").strip()
    customer_tax_id = "".join(filter(str.isdigit, customer_tax_id_raw))
    if len(customer_tax_id) not in (10, 11):
        customer_tax_id = "0000000000"
        
    customer_name = _customer_display_name(invoice, customer_tax_id)

    items = invoice.get("items") or []
    rate = _tax_rate(invoice)
    subtotal = _money(invoice.get("subtotal"))
    tax_amount = _money(invoice.get("tax_amount"))
    total_amount = _money(invoice.get("total_amount"))

    line_xml = []
    calculated_subtotal = Decimal("0.00")
    calculated_tax = Decimal("0.00")
    tax_subtotals: dict[Decimal, dict[str, Decimal]] = {}

    for index, item in enumerate(items, start=1):
        quantity = _money(item.get("quantity") or "1")
        unit_price = _money(item.get("unit_price"))
        line_total = _money(item.get("total_price"))

        if line_total == Decimal("0.00") and quantity and unit_price:
            line_total = quantity * unit_price
        if unit_price == Decimal("0.00") and quantity:
            unit_price = line_total / quantity

        item_rate = _money(item.get("tax_rate")) if item.get("tax_rate") else rate
        line_tax = (line_total * item_rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        calculated_subtotal += line_total
        calculated_tax += line_tax
        
        if item_rate not in tax_subtotals:
            tax_subtotals[item_rate] = {"taxable": Decimal("0.00"), "tax": Decimal("0.00")}
        tax_subtotals[item_rate]["taxable"] += line_total
        tax_subtotals[item_rate]["tax"] += line_tax

        description = escape(str(item.get("description") or item.get("name") or "Item"))
        code = escape(str(item.get("code") or index))
        line_xml.append(
            f"""
  <cac:InvoiceLine>
    <cbc:ID>{index}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">{_fmt_money(quantity)}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{currency}">{_fmt_money(line_total)}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="{currency}">{_fmt_money(line_tax)}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{currency}">{_fmt_money(line_total)}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{currency}">{_fmt_money(line_tax)}</cbc:TaxAmount>
        <cbc:Percent>{_fmt_money(item_rate)}</cbc:Percent>
        <cac:TaxCategory>
          <cac:TaxScheme>
            <cbc:Name>KDV</cbc:Name>
            <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
          </cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Name>{description}</cbc:Name>
      <cac:SellersItemIdentification><cbc:ID>{code}</cbc:ID></cac:SellersItemIdentification>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="{currency}">{_fmt_money(unit_price)}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>"""
        )

    if subtotal == Decimal("0.00"):
        subtotal = calculated_subtotal
    if tax_amount == Decimal("0.00"):
        tax_amount = calculated_tax
    if total_amount == Decimal("0.00"):
        total_amount = subtotal + tax_amount

    supplier_scheme = _scheme_id(supplier_tax_id)
    customer_scheme = _scheme_id(customer_tax_id)

    allowance_charge_xml = ""
    discount_amount = _money(invoice.get("discount_amount"))
    taxable_amount = subtotal - discount_amount
    
    if discount_amount > Decimal("0.00"):
        allowance_charge_xml = f"""
  <cac:AllowanceCharge>
    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:Amount currencyID="{currency}">{_fmt_money(discount_amount)}</cbc:Amount>
  </cac:AllowanceCharge>"""
        if calculated_subtotal > Decimal("0.00"):
            for t_rate, t_amounts in tax_subtotals.items():
                proportion = t_amounts["taxable"] / calculated_subtotal
                discount_part = (discount_amount * proportion).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                t_amounts["taxable"] -= discount_part
                t_amounts["tax"] = (t_amounts["taxable"] * t_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    doc_tax_subtotals_xml = []
    for t_rate, t_amounts in tax_subtotals.items():
        doc_tax_subtotals_xml.append(f"""
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{currency}">{_fmt_money(t_amounts["taxable"])}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{currency}">{_fmt_money(t_amounts["tax"])}</cbc:TaxAmount>
      <cbc:Percent>{_fmt_money(t_rate)}</cbc:Percent>
      <cac:TaxCategory>
        <cac:TaxScheme>
          <cbc:Name>KDV</cbc:Name>
          <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
        </cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>""")
    doc_tax_subtotal_str = "".join(doc_tax_subtotals_xml)

    pricing_exchange_rate_xml = ""
    if currency != "TRY":
        rate_val = invoice.get("exchange_rate") or get_tcmb_rate(currency, issue_date)
        if rate_val:
            try:
                rate_val_fmt = f"{float(rate_val):.4f}"
            except (ValueError, TypeError):
                rate_val_fmt = "1.0000"
        else:
            rate_val_fmt = "1.0000"
            
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
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:IssueTime>{issue_time}</cbc:IssueTime>
  <cbc:InvoiceTypeCode>{escape(invoice_type)}</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>{currency}</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>{len(items)}</cbc:LineCountNumeric>{pricing_exchange_rate_xml}
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
      {f'<cac:Person><cbc:FirstName>{escape(customer_name)}</cbc:FirstName><cbc:FamilyName>{escape(customer_name)}</cbc:FamilyName></cac:Person>' if customer_scheme == 'TCKN' else f'<cac:PartyName><cbc:Name>{escape(customer_name)}</cbc:Name></cac:PartyName>'}
    </cac:Party>
  </cac:AccountingCustomerParty>
  {allowance_charge_xml}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{currency}">{_fmt_money(tax_amount)}</cbc:TaxAmount>
    {doc_tax_subtotal_str}
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{currency}">{_fmt_money(subtotal)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{currency}">{_fmt_money(taxable_amount)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{currency}">{_fmt_money(total_amount)}</cbc:TaxInclusiveAmount>
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
        timeout: int = 30,
    ) -> None:
        self.username = username
        self.password = password
        self.endpoint = endpoint or (PROD_ENDPOINT if environment == "prod" else TEST_ENDPOINT)
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
    users: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(result.raw_xml)
    except ET.ParseError:
        return users

    for node in root.iter():
        if _local_name(node.tag) not in {"Items", "Definition"}:
            continue
        attrs = dict(node.attrib)
        if attrs.get("Title") or attrs.get("Identifier"):
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

    for user in _extract_system_user_values(result):
        if user.get("Title"):
            return user
    return None


def enrich_invoice_customer_from_uyumsoft(invoice_data: dict[str, Any]) -> dict[str, Any]:
    """Fill customer name/title from Uyumsoft taxpayer list when VKN/TCKN is available.

    This is best-effort by design. A lookup failure must not stop PDF extraction,
    validation, or invoice transfer.
    """
    if not isinstance(invoice_data, dict):
        return invoice_data

    if invoice_data.get("_uyumsoft_customer_lookup") == "matched" and (
        invoice_data.get("customer_title") or invoice_data.get("customer_name")
    ):
        return invoice_data

    if os.getenv("UYUMSOFT_CUSTOMER_LOOKUP", "1").lower() in {"0", "false", "no", "off"}:
        return invoice_data

    target_vkn = "".join(filter(str.isdigit, str(invoice_data.get("customer_tax_id") or "")))
    if len(target_vkn) not in (10, 11):
        return invoice_data

    environment = os.getenv("UYUMSOFT_ENV", "test").lower()
    username = os.getenv("UYUMSOFT_USERNAME") or ("Uyumsoft" if environment == "test" else "")
    password = os.getenv("UYUMSOFT_PASSWORD") or ("Uyumsoft" if environment == "test" else "")
    if not username or not password:
        return invoice_data

    client = UyumsoftSoapClient(
        username,
        password,
        environment=environment,
        timeout=int(os.getenv("UYUMSOFT_LOOKUP_TIMEOUT", "8")),
    )

    try:
        result = client.filter_e_invoice_users(target_vkn, page_size=10)
        match = _best_uyumsoft_user_match(result, target_vkn)
        if not match:
            aliases_result = client.get_user_aliases(target_vkn)
            match = _best_uyumsoft_user_match(aliases_result, target_vkn)
    except Exception as exc:
        invoice_data["_uyumsoft_customer_lookup"] = f"failed: {type(exc).__name__}: {str(exc)}"
        return invoice_data

    if not match:
        invoice_data["_uyumsoft_customer_lookup"] = "not_found"
        return invoice_data

    title = str(match.get("Title") or "").strip()
    if title:
        invoice_data["customer_name"] = title
        invoice_data["customer_title"] = title
        invoice_data["_uyumsoft_customer_lookup"] = "matched"

    alias = str(match.get("PostboxAlias") or match.get("Alias") or "").strip()
    if alias and not invoice_data.get("customer_alias"):
        invoice_data["customer_alias"] = alias

    return invoice_data


def build_validate_invoice_body(invoice: dict[str, Any]) -> str:
    invoice_param = build_uyumsoft_invoice_element(invoice, "invoice")
    return f'<ValidateInvoice xmlns="http://tempuri.org/">{invoice_param}</ValidateInvoice>'


def build_invoice_info_body(operation: str, invoice: dict[str, Any]) -> str:
    if operation not in {"SaveAsDraft", "SendInvoice"}:
        raise ValueError("operation must be SaveAsDraft or SendInvoice")

    ubl = build_uyumsoft_invoice_element(invoice, "Invoice")
    local_document_id = escape(str(invoice.get("invoice_no") or f"AUTO-{uuid.uuid4().hex[:12]}"))
    
    target_vkn_raw = str(invoice.get("customer_tax_id") or "").strip()
    target_vkn = "".join(filter(str.isdigit, target_vkn_raw))
    if len(target_vkn) not in (10, 11):
        target_vkn = "0000000000"
    target_vkn = escape(target_vkn)
    
    target_title = escape(_customer_display_name(invoice, target_vkn))
    target_alias = invoice.get("customer_alias")
    alias_attr = f' Alias="{escape(str(target_alias))}"' if target_alias else ""
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


def send_invoice_to_uyumsoft(invoice_data: dict[str, Any], action: str | None = None) -> dict[str, Any]:
    environment = os.getenv("UYUMSOFT_ENV", "test").lower()
    username = os.getenv("UYUMSOFT_USERNAME") or ("Uyumsoft" if environment == "test" else "")
    password = os.getenv("UYUMSOFT_PASSWORD") or ("Uyumsoft" if environment == "test" else "")

    if not username or not password:
        return {
            "success": False,
            "message": "UYUMSOFT_USERNAME and UYUMSOFT_PASSWORD must be configured.",
            "details": "Credentials are required before sending invoice data to Uyumsoft.",
            "response_code": 401,
        }

    selected_action = (action or os.getenv("UYUMSOFT_ACTION", "test_connection")).lower()
    client = UyumsoftSoapClient(username, password, environment=environment)

    try:
        if selected_action in {"test", "test_connection"}:
            result = client.test_connection()
        elif selected_action in {"dry_run", "preview"}:
            body = build_invoice_info_body("SaveAsDraft", invoice_data)
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
            result = client.validate_invoice_data(invoice_data)
        elif selected_action == "draft":
            result = client.save_as_draft_data(invoice_data)
        elif selected_action == "send":
            result = client.send_invoice_data(invoice_data)
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
