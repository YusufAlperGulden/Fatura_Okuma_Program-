import urllib.request
import urllib.error

url = "https://efatura.uyumsoft.com.tr/Services/Integration"
operation_body = '<TestConnection xmlns="http://tempuri.org/" />'
username = ""
password = ""
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
envelope = f"""<s:Envelope xmlns:s="{SOAP_ENV_NS}" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
  <s:Header>
    <wsse:Security s:mustUnderstand="1">
      <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password>{password}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </s:Header>
  <s:Body>{operation_body}</s:Body>
</s:Envelope>"""

req = urllib.request.Request(
    url,
    data=envelope.encode("utf-8"),
    headers={
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': '"http://tempuri.org/IIntegration/TestConnection"'
    },
    method='POST'
)

try:
    response = urllib.request.urlopen(req)
    print("SUCCESS", response.getcode())
    print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}")
    print(e.read()[:500].decode('utf-8', errors='replace'))
