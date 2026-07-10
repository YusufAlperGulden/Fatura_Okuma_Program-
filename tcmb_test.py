
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

def get_tcmb_rate(currency_code, date_str):
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    for _ in range(5):
        if date_obj.date() == datetime.today().date() or date_obj.date() > datetime.today().date():
            url = 'https://www.tcmb.gov.tr/kurlar/today.xml'
        else:
            url = f'https://www.tcmb.gov.tr/kurlar/{date_obj.strftime("%Y%m")}/{date_obj.strftime("%d%m%Y")}.xml'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                tree = ET.parse(response)
                root = tree.getroot()
                for curr in root.findall('Currency'):
                    if curr.attrib.get('CurrencyCode') == currency_code:
                        rate = curr.find('ForexSelling').text
                        return float(rate)
        except Exception as e:
            pass
        date_obj -= timedelta(days=1)
    return 1.0

print(get_tcmb_rate('EUR', '2026-09-09'))
print(get_tcmb_rate('EUR', '2026-07-10'))

