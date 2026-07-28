import urllib.request
from integrators.uyumsoft_api import UyumsoftSoapClient, _server_credentials

username, password = _server_credentials("test")
client = UyumsoftSoapClient(username, password, environment="test")

operation_body = """<GetOutboxInvoiceStatusWithLogs xmlns="http://tempuri.org/">
  <invoiceIds>
    <guid xmlns="http://schemas.microsoft.com/2003/10/Serialization/Arrays">619c55e7-a175-4d94-bac5-acf0c03bcfd0</guid>
  </invoiceIds>
</GetOutboxInvoiceStatusWithLogs>"""

result = client._call("GetOutboxInvoiceStatusWithLogs", operation_body)
print(result)
