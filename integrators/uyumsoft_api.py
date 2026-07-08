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

    text = str(value).strip()
    text = text.replace("TRY", "").replace("TL", "").replace(" ", "")
    text = text.replace("\u20ba", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

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


def build_ubl_invoice(invoice: dict[str, Any]) -> str:
    invoice_no = str(invoice.get("invoice_no") or f"AUTO-{uuid.uuid4().hex[:12].upper()}")
    issue_date = _parse_date(invoice.get("date"))
    issue_time = datetime.now().strftime("%H:%M:%S")
    currency = str(invoice.get("currency") or os.getenv("UYUMSOFT_CURRENCY", "TRY"))
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

    customer_tax_id = str(invoice.get("customer_tax_id") or "").strip()
    customer_name = str(
        invoice.get("customer_title")
        or invoice.get("customer_name")
        or invoice.get("customer")
        or "UNKNOWN CUSTOMER"
    )

    items = invoice.get("items") or []
    rate = _tax_rate(invoice)
    subtotal = _money(invoice.get("subtotal"))
    tax_amount = _money(invoice.get("tax_amount"))
    total_amount = _money(invoice.get("total_amount"))

    line_xml = []
    calculated_subtotal = Decimal("0.00")
    calculated_tax = Decimal("0.00")

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
      {f'<cac:Person><cbc:FirstName>{escape(customer_name)}</cbc:FirstName><cbc:FamilyName>{escape(customer_name)}</cbc:FamilyName></cac:Person>' if customer_scheme == 'TCKN' else f'<cac:PartyName><cbc:Name>{escape(customer_name)}</cbc:Name></cac:PartyName>'}
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:TaxTotal><cbc:TaxAmount currencyID="{currency}">{_fmt_money(tax_amount)}</cbc:TaxAmount></cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{currency}">{_fmt_money(subtotal)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{currency}">{_fmt_money(subtotal)}</cbc:TaxExclusiveAmount>
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
        root = ET.fromstring(raw_xml)
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


def build_validate_invoice_body(invoice: dict[str, Any]) -> str:
    invoice_param = build_uyumsoft_invoice_element(invoice, "invoice")
    return f'<ValidateInvoice xmlns="http://tempuri.org/">{invoice_param}</ValidateInvoice>'


def build_invoice_info_body(operation: str, invoice: dict[str, Any]) -> str:
    if operation not in {"SaveAsDraft", "SendInvoice"}:
        raise ValueError("operation must be SaveAsDraft or SendInvoice")

    ubl = build_uyumsoft_invoice_element(invoice, "Invoice")
    local_document_id = escape(str(invoice.get("invoice_no") or f"AUTO-{uuid.uuid4().hex[:12]}"))
    target_vkn = escape(str(invoice.get("customer_tax_id") or ""))
    target_title = escape(
        str(invoice.get("customer_title") or invoice.get("customer_name") or invoice.get("customer") or "UNKNOWN CUSTOMER")
    )
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

    return {
        "success": result.success,
        "message": result.message,
        "operation": result.operation,
        "values": result.values,
        "details": result.raw_xml[:2000],
        "response_code": result.status_code,
    }
