# Uyumsoft test ve canlı ortam ayarları

Uygulama yanlışlıkla gerçek hesaba taslak oluşturmamak için varsayılan olarak
Uyumsoft test ortamını kullanır.

## Test ortamı

```text
UYUMSOFT_ENV=test
UYUMSOFT_PORTAL_URL=http://portal-test.uyumsoft.com.tr/Taslak
```

SOAP entegrasyon adresi kod tarafından otomatik seçilir:
`https://efatura-test.uyumsoft.com.tr/Services/Integration`.

## Gerçek işyeri / canlı ortam

Render servisinin Environment bölümünde şu değerler tanımlanmalıdır:

```text
UYUMSOFT_ENV=prod
UYUMSOFT_USERNAME=<işyerinin gerçek entegrasyon kullanıcı adı>
UYUMSOFT_PASSWORD=<işyerinin gerçek entegrasyon şifresi>
UYUMSOFT_PORTAL_URL=<işyerinin Uyumsoft taslaklar sayfasının kesin adresi>
UYUMSOFT_SUPPLIER_VKN=<işyerinin VKN/TCKN bilgisi>
UYUMSOFT_SUPPLIER_NAME=<işyerinin resmi ünvanı>
UYUMSOFT_SUPPLIER_TAX_OFFICE=<işyerinin vergi dairesi>
```

`UYUMSOFT_ENV=prod` olduğunda SOAP entegrasyon adresi otomatik olarak
`https://efatura.uyumsoft.com.tr/Services/Integration` olur. Portal adresi ile
SOAP adresi farklı amaçlara sahiptir: SOAP adresi taslağı oluşturur; portal
adresi yalnızca kullanıcının oluşturulan taslağı tarayıcıda görmesini sağlar.

`UYUMSOFT_PORTAL_URL` bilinmiyorsa Uyumsoft'un genel kullanıcı giriş sayfası
açılır. Canlı taslak sayfası için kesin adres Uyumsoft hesabından veya Uyumsoft
destekten doğrulanmalıdır; uygulama tahmini bir canlı `/Taslak` adresi kullanmaz.

Ortam değişkenleri değiştirildikten sonra Render servisi yeniden deploy
edilmelidir. Arayüzde gönderim düğmelerinin altında `TEST` veya
`GERÇEK / CANLI` etiketi görünür.
