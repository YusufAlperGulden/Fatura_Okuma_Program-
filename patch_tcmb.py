with open('integrators/uyumsoft_api.py', 'r', encoding='utf-8') as f:
    content = f.read()

import_block = """
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
"""

if "def get_tcmb_rate" not in content:
    content = content.replace("from xml.sax.saxutils import escape", import_block)

calc_block = """    doc_tax_subtotal_str = "".join(doc_tax_subtotals_xml)

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
"""

if "pricing_exchange_rate_xml" not in content:
    content = content.replace('    doc_tax_subtotal_str = "".join(doc_tax_subtotals_xml)', calc_block)
    
    content = content.replace(
        "<cbc:LineCountNumeric>{len(items)}</cbc:LineCountNumeric>",
        "<cbc:LineCountNumeric>{len(items)}</cbc:LineCountNumeric>{pricing_exchange_rate_xml}"
    )

with open('integrators/uyumsoft_api.py', 'w', encoding='utf-8') as f:
    f.write(content)
