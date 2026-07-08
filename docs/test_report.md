# Test Raporu

Tarih: 2026-07-08

## Kontrol edilen alanlar

- PDF okuma: `ornek.pdf`
- XML okuma: `ornek.xml`
- Excel okuma ve Uyumsoft Excel aktarim cikti dosyasi
- Matematiksel fatura dogrulama
- UBL XML uretimi
- FastAPI `/upload`, `/download_excel`, `/send-uyumsoft` rotalari
- Uyumsoft `dry_run` SOAP taslak verisi uretimi
- Uyumsoft SOAP baglanti katmani

## Gecen kod testleri

```powershell
venv\Scripts\python.exe -m py_compile api.py main.py extractors\pdf_extractor.py extractors\ocr_extractor.py extractors\xml_extractor.py extractors\excel_extractor.py validators\invoice_validator.py integrators\uyumsoft_excel.py integrators\uyumsoft_api.py tests\test_pipeline.py
```

Sonuc: Sozdizimi hatasi yok.

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -v
```

Sonuc: 8 test gecti.

Test kapsami:

- `ornek.pdf` icinden tarih, TCKN/VKN, kalem, ara toplam, KDV ve genel toplam okundu.
- `ornek.xml` icinden fatura numarasi, tarih, alici, kalemler ve toplamlar okundu.
- Okunan PDF/XML verisi `validate_invoice` ile matematiksel olarak dogrulandi.
- Uyumsoft aktarim Excel'i uretildi ve tekrar Excel okuyucu ile iceri alindi.
- Excel sayisal hucrelerinden gelebilen `10.0` gibi degerlerin yanlis hesaplanmamasi test edildi.
- UBL fatura XML'i gecerli XML olarak uretildi.
- Uyumsoft `SaveAsDraft` SOAP govdesi dis servise gonderilmeden uretildi ve XML olarak dogrulandi.
- Uyumsoft gonderim sarmalayicisinin varsayilan guvenli modu `TestConnection` olarak kaldi.

## Komut satiri uctan uca test

```powershell
venv\Scripts\python.exe main.py ornek.pdf
```

Sonuc: PDF okundu, dogrulama gecti ve `Uyumsoft_Aktarim_Taslagi.xlsx` uretildi.

Aktarim dosyasinda dogrulanan ilk veri satiri:

- Fatura Tarihi: `7.07.2026`
- Musteri VKN/TCKN: `11111111111`
- Urun Kodu: `0213.217`
- Urun Aciklamasi: `NFC Silver Kart`
- Miktar: `10,00`
- Birim Fiyat: `40,00`
- Satir Toplami: `400,00`
- Fatura KDV: `80,00`
- Fatura Genel Toplam: `480,00`

## Web API testi

FastAPI uygulamasi gecici olarak yerel sunucuda calistirildi ve gercek HTTP ile test edildi.

Sonuclar:

- `/upload` + `ornek.pdf`: `is_valid=True`, toplam `480,00`, kalem `NFC Silver Kart`
- `/download_excel`: Excel dosyasi indirildi, boyut `5060` byte
- `/send-uyumsoft` + `action=dry_run`: Dis servise cikmadan `SaveAsDraft` SOAP govdesi uretildi, `operation=DryRun` dondu

## Uyumsoft dis servis durumu

Fatura icerigi gonderilmeden sadece servis erisimi kontrol edildi.

Son denemede:

- `https://efatura-test.uyumsoft.com.tr/Services/Integration?singleWsdl`: `HTTP 500 Internal Server Error`
- `https://efatura-test.uyumsoft.com.tr/Services/Integration` + `TestConnection`: `HTTP 500 Internal Server Error`

Bu nedenle Uyumsoft test ortamiyla canli dogrulama bu turda tamamlanamadi. Kod tarafinda varsayilan mod fatura verisi gondermez; sadece `test_connection` dener. Gercek aktarim icin `UYUMSOFT_ACTION=validate`, `draft` veya `send` acikca ayarlanmalidir.

## Bilinen sinirlamalar

- `ornek.pdf` metninde gorunur bir fatura numarasi bulunmadigi icin `invoice_no` bos donuyor. UBL uretiminde bu durumda otomatik yerel belge numarasi olusturulur.
- Excel okuyucu Uyumsoft aktarim tablosu benzeri kolonlari okuyacak sekilde tamamlandi. Baska formatta Excel faturalar icin kolon esleme listesi genisletilebilir.
- Gercek fatura aktarimi test edilmedi; kullanici verisini dis servise gondermek icin ayrica acik onay ve calisan Uyumsoft test servisi gerekir.
