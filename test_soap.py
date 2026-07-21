import urllib.request
import urllib.error

url = "https://efatura-test.uyumsoft.com.tr/Services/Integration"
req = urllib.request.Request(
    url,
    data=b'<xml/>',
    headers={
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': '"http://tempuri.org/IIntegration/TestConnection"'
    },
    method='POST'
)

try:
    urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}")
    print(e.read()[:500].decode('utf-8', errors='replace'))
