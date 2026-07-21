# Uyumsoft Integration API Notlari

Bu proje icin gereken servis REST/JSON degil, WCF SOAP servisidir.

## Dogrulanan adresler

- Test WSDL: https://efatura-test.uyumsoft.com.tr/Services/Integration?singleWsdl
- Test endpoint: https://efatura-test.uyumsoft.com.tr/Services/Integration
- Canli WSDL: https://efatura.uyumsoft.com.tr/Services/Integration?singleWsdl
- Canli endpoint: https://efatura.uyumsoft.com.tr/Services/Integration
- Test portal: http://portal-test.uyumsoft.com.tr/

## Kimlik dogrulama

Servis HTTPS uzerinden SOAP 1.1 calisiyor ve WS-Security `UsernameToken` bekliyor.
Test kullanicisi ile `TestConnection` cagrisi dogrulandi:

- Kullanici adi: `Uyumsoft`
- Sifre: `Uyumsoft`
- Sonuc: `TestConnectionResult IsSucceded="true" Value="true"`

## Fatura aktarimi icin ana metodlar

WSDL'de fatura aktarimi icin en ilgili metodlar sunlar:

- `ValidateInvoice`: UBL `InvoiceType` dogrulama.
- `SaveAsDraft`: UBL faturayi Uyumsoft test portalinda taslak olarak olusturma.
- `SendInvoice`: UBL faturayi dogrudan gonderme.
- `SubmitInvoicesBatch`: Birden fazla `InvoiceInfo` icin `Send` veya `SaveDraft` aksiyonu.
- `QueryOutboxInvoiceStatus`: Giden fatura durumunu sorgulama.
- `GetOutboxInvoicePdf`: Giden fatura PDF goruntusunu alma.

`SaveAsDraft` ve `SendInvoice` girdisi:

```xml
<invoices>
  <InvoiceInfo LocalDocumentId="...">
    <Invoice>UBL InvoiceType icerigi</Invoice>
    <TargetCustomer VknTckn="..." Alias="..." Title="..." />
    <Scenario>Automated</Scenario>
    <CreateDateUtc>2026-07-08T07:46:52Z</CreateDateUtc>
  </InvoiceInfo>
</invoices>
```

`InvoiceInfo` alanlari WSDL'de su sekilde gorundu:

- `Invoice`: UBL 2.x `InvoiceType`
- `TargetCustomer`: `VknTckn`, `Alias`, `Title`
- `EArchiveInvoiceInfo`: e-Arsiv bilgileri gerekiyorsa
- `Scenario`: `Automated`, `eInvoice`, `eArchive`, `MusteArchive`
- `Notification`: e-posta/SMS bildirimleri
- `CreateDateUtc`: UTC olusturma zamani
- `LocalDocumentId`: attribute olarak yerel belge numarasi

## Projedeki guvenli varsayilan

`/send-uyumsoft` endpoint'i eklendi, ancak varsayilan aksiyon `test_connection`.
Bu mod fatura icerigini Uyumsoft'a gondermez; sadece servis baglantisini test eder.

Dis servise veri gondermeden SOAP taslak govdesini uretmek icin:

```powershell
$env:UYUMSOFT_ACTION = "dry_run"
```

Gercek fatura verisi aktarimi icin ortam degiskeni bilincli olarak acilmali:

```powershell
$env:UYUMSOFT_ACTION = "validate"  # fatura XML'ini dogrulamaya gonderir
$env:UYUMSOFT_ACTION = "draft"     # Uyumsoft'ta taslak olusturur
$env:UYUMSOFT_ACTION = "send"      # faturayi dogrudan gonderir
```

Canli ortam icin ayrica:

```powershell
$env:UYUMSOFT_ENV = "prod"
$env:UYUMSOFT_USERNAME = "..."
$env:UYUMSOFT_PASSWORD = "..."
```

## Onemli entegrasyon notu

PDF'den cikan ham alanlar Uyumsoft'a dogrudan gonderilmiyor. Once UBL-TR uyumlu
bir `Invoice` XML'i uretilmeli; sonra bu XML `InvoiceInfo` zarfinin icine konmali.
Mevcut kod bu donusum icin baslangic UBL'i uretiyor. Canli gonderimden once
`ValidateInvoice` ile UBL alanlari, KDV oranlari, alici alias bilgisi ve senaryo
secimi test edilmelidir.
