# Kapsamlı Mimari Revizyon, Güvenlik ve Ekranda Veri Düzenleme Planı

## Faz 0 — Acil Kilit (Hotfix) - [TAMAMLANDI]
* Otomatik Uyumsoft gönderimi UI üzerinden kaldırıldı.
* `/api/history` endpoint'i kapatıldı.
* Tüm API ve statik site HTTP Basic Auth altına alındı.
* Backend Uyumsoft endpoint'i (`/send-uyumsoft`) yalnızca `draft` işlemi kabul edecek şekilde kilitlendi.
* API'den wildcard CORS kısıtlaması kaldırıldı (aynı origin üzerinden güvenli iletişim).

## Faz 1 — Backend Sözleşmesi (Contract & Validation)
* FastAPI üzerinde katı Pydantic modellerinin uygulanması.
* Saf ve yan etkisiz (side-effect free) `/validate` uç noktasının oluşturulması.
* Dosya boyutu ve tür sınırı (upload limits) eklenmesi.
* Yanıtlarda HTTP durum kodlarının (200, 400, 413, 429 vs.) doğru kullanılması.
* Rate Limiting için `slowapi==0.1.10` entegrasyonu (başlangıçta in-memory deposu ile).

## Faz 2 — Edit Before Send (Ekranda Veri Düzenleme)
* Arayüzde `originalInvoice` ve `draftInvoice` (düzenlenen) ayrımının yapılması.
* Sonuç kartları ve tablo hücrelerinin (VKN, isim, tutarlar) editable (düzenlenebilir) hale getirilmesi.
* Her değişiklikte 350–500 ms debounce ile backend `/validate` uç noktasına istek atılarak "HATALI" / "GEÇERLİ" rozetinin yerel olarak güncellenmesi.
* Değişiklik anında "Gönder" butonunun deaktif edilmesi ve ancak geçerli bir validasyon döndüğünde tekrar aktifleşmesi.
* Kullanıcıya açık bir "Taslak Olarak Gönder" butonu sunulması ve native `confirm()` ile onay istenmesi.

## Faz 3 — DOM Güvenliği
* `ui/app.js` içerisindeki tüm fatura kaynaklı `innerHTML` kullanımlarının tamamen temizlenip `textContent` ve `createElement` ile değiştirilmesi.
* CSP (Content Security Policy) ve üçüncü taraf script kontrollerinin sıkılaştırılması.
* CSV Güvenliğinin (Excel Formül Enjeksiyonu koruması ve RFC 4180 kaçış karakterleri) eksiksiz uygulanması.

## Faz 4 — IndexedDB (Yerel Geçmiş ve Kalıcılık)
* Tüm güvenlik aşamaları tamamlandıktan sonra, IndexedDB tabanlı geçmiş yapısının kurulması.
* `autoIncrement + invoiceNo` yerine, kimlik olarak `id: crypto.randomUUID()` ve unique anahtar olarak `dedupeKey: issuerVkn|invoiceNo` kullanılması.
* `navigator.storage.persist()` için izin istenmesi (ancak reddedilme veya silinme ihtimaline karşı bilgilendirme yapılması).
* Mevcut (güvensiz ve formsuz) SQLite verilerinin otomatik migration *yapılmaması* (temiz başlangıç).
* İsteyen yöneticiler için çevrimdışı JSON Export/Import (Yedekleme ve Geri Yükleme) fonksiyonlarının eklenmesi.

## Faz 5 — Üretim Testleri (Production Tests)
* Basic Auth, 413 (Payload Too Large), 429 (Too Many Requests) HTTP yanıtlarının testi.
* Fatura içerisine yerleştirilmiş XSS payload'larının test edilmesi.
* Çift tıklama (Double click) ve Idempotency testleri.
* Sisteme dışarıdan sahte `action:"send"` isteği atılarak backend kilidinin aşılamadığının test edilmesi.

## User Review Required

> [!NOTE]
> Faz 0 (Acil Kilit) onayınız üzerine derhal kodlanmış ve yayına alınmıştır.
> Aşağıdaki adımlar sırasıyla Faz 1, 2, 3, 4 ve 5 olarak işletilecektir. Bu plan hem `brain` klasöründe hem de doğrudan repoda `docs/implementation_plan.md` olarak kaydedilmiştir.
