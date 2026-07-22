import urllib.request
from integrators.uyumsoft_api import UyumsoftSoapClient, _server_credentials

username, password = _server_credentials("test")
client = UyumsoftSoapClient(username, password, environment="test")

operation_body = """<GetOutboxInvoiceStatusWithLogs xmlns="http://tempuri.org/">
  <invoiceIds>
    <guid xmlns="http://schemas.microsoft.com/2003/10/Serialization/Arrays">619c55e7-a175-4d94-bac5-acf0c03bcfd0</guid>
  </invoiceIds>
</GetOutboxInvoiceStatusWithLogs>"""

operation_body_2 = """<GetOutboxInvoiceStatusWithLogs xmlns="http://tempuri.org/">
  <invoiceId>619c55e7-a175-4d94-bac5-acf0c03bcfd0</invoiceId>
</GetOutboxInvoiceStatusWithLogs>"""

result = client._call("GetOutboxInvoiceStatusWithLogs", operation_body_2)
print("Result with invoiceId:")
print(result)

operation_body_3 = """<GetOutboxInvoiceStatusWithLogs xmlns="http://tempuri.org/">
  <invoiceIds>
    <string xmlns="http://schemas.microsoft.com/2003/10/Serialization/Arrays">619c55e7-a175-4d94-bac5-acf0c03bcfd0</string>
  </invoiceIds>
</GetOutboxInvoiceStatusWithLogs>"""

result_3 = client._call("GetOutboxInvoiceStatusWithLogs", operation_body_3)
print("Result with invoiceIds string array:")
print(result_3)
