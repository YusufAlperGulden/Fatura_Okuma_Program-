import io
import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # Keep non-AI helpers importable in lightweight test installs.
    genai = None
    genai_types = None

from utils.serial_numbers import (
    format_customer_postal_address,
    normalize_customer_postal_address,
    normalize_invoice_serial_numbers,
)
from utils.invoice_values import parse_localized_decimal, quantize_money


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
FALLBACK_GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)

USD_EXTRACTION_INSTRUCTIONS = """
KRITIK USD KURALI:
- Belgenin HERHANGI BIR YERINDE bagimsiz para birimi kodu olarak "USD" geciyorsa
  bu belgeyi USD tahsilatli fatura kabul et. USD ifadesi notlarda, dipnotta,
  satir aciklamasinda veya toplamlar bolumunde olsa da bu kural gecerlidir.
- Ozellikle "IS BU FATURA BEDELI ... USD OLUP, BEDELI USD OLARAK TAHSIL
  EDILECEKTIR", "BEDELI USD OLARAK TAHSIL EDILECEKTIR" veya ayni anlama gelen
  bir cumle kesin USD kanitidir.
- Bu durumda has_usd_mention=true, currency="USD",
  document_currency="USD" ve settlement_currency="USD" dondur.
- Belgede kalemler ve toplamlar TL olarak yazilmis, ancak tahsilat USD ise
  accounting_currency="TRY" dondur. TL degerlerin orijinallerini local_subtotal,
  local_discount_amount, local_tax_amount, local_total ve kalemlerde
  local_unit_price/local_total_price alanlarinda koru.
- Faturada acikca yazan doviz kurunu exchange_rate alanina koy. Kur yaziyorsa TL
  tutarlari bu kura bolerek USD subtotal, discount_amount, tax_amount,
  total_amount ve kalem fiyatlarini hesapla. Yuvarlamayi iki ondalikla yap.
- Cumlede acikca yazan USD fatura bedelini foreign_total alanina koy ve
  total_amount ile ayni USD degeri kullan. foreign_total * exchange_rate ile
  local_total tutarliligini kontrol et.
- Kur belgede yoksa ASLA kur tahmin etme. exchange_rate=null dondur; TL
  orijinalleri local_* alanlarinda koru ve fx_conversion_required=true yap.
- USD hic gecmiyorsa has_usd_mention=false dondur ve belgedeki gercek para
  birimini normal sekilde kullan.
""".strip()


def _is_truthy_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "evet"}


def _contains_usd_token(value) -> bool:
    """Return whether any AI-returned text contains the standalone USD code."""

    if isinstance(value, dict):
        return any(_contains_usd_token(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_usd_token(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(re.search(r"(?<![A-Z])USD(?![A-Z])", value.upper()))


def _decimal_string(value: Decimal) -> str:
    return f"{quantize_money(value):.2f}"


def _unit_price_string(value: Decimal) -> str:
    text = format(
        value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP), "f"
    ).rstrip("0").rstrip(".")
    if not text:
        return "0.00"
    if "." not in text:
        return f"{text}.00"
    if len(text.rsplit(".", 1)[1]) == 1:
        return f"{text}0"
    return text


def _normalize_ai_usd_currency(data: dict) -> dict:
    """Make Gemini's USD evidence and monetary fields internally consistent."""

    if not isinstance(data, dict):
        return data

    has_usd_mention = _is_truthy_flag(data.get("has_usd_mention")) or _contains_usd_token(
        data
    )
    data["has_usd_mention"] = has_usd_mention
    if not has_usd_mention:
        return data

    original_currency = str(data.get("currency") or "").strip().upper()
    accounting_currency = str(
        data.get("accounting_currency") or ""
    ).strip().upper()
    rate = parse_localized_decimal(data.get("exchange_rate"))
    explicit_foreign_total = parse_localized_decimal(data.get("foreign_total"))

    local_mappings = (
        ("subtotal", "local_subtotal"),
        ("discount_amount", "local_discount_amount"),
        ("tax_amount", "local_tax_amount"),
        ("total_amount", "local_total"),
    )
    has_local_values = any(
        data.get(local_field) not in (None, "")
        for _document_field, local_field in local_mappings
    )
    local_values_are_primary = (
        original_currency in {"TRY", "TL"}
        or accounting_currency in {"TRY", "TL"}
        or has_local_values
    )

    data["currency"] = "USD"
    data["document_currency"] = "USD"
    data["settlement_currency"] = "USD"

    if local_values_are_primary:
        data["accounting_currency"] = "TRY"
        if original_currency in {"TRY", "TL"}:
            for document_field, local_field in local_mappings:
                if data.get(local_field) in (
                    None,
                    "",
                ) and data.get(document_field) not in (None, ""):
                    data[local_field] = data[document_field]

        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            if original_currency in {"TRY", "TL"}:
                if item.get("local_unit_price") in (None, "") and item.get(
                    "unit_price"
                ) not in (None, ""):
                    item["local_unit_price"] = item["unit_price"]
                if item.get("local_total_price") in (None, "") and item.get(
                    "total_price"
                ) not in (None, ""):
                    item["local_total_price"] = item["total_price"]
            item["local_amount_currency"] = "TRY"

    document_total = parse_localized_decimal(data.get("total_amount"))
    local_total = parse_localized_decimal(data.get("local_total"))
    needs_conversion = (
        original_currency in {"TRY", "TL"}
        or (
            accounting_currency in {"TRY", "TL"}
            and not has_local_values
        )
    )
    if not needs_conversion and accounting_currency in {"TRY", "TL"}:
        for document_field, local_field in local_mappings:
            document_value = parse_localized_decimal(data.get(document_field))
            local_value = parse_localized_decimal(data.get(local_field))
            if (
                document_value is not None
                and local_value is not None
                and abs(document_value - local_value) <= Decimal("1.00")
            ):
                needs_conversion = True
                break
    if not needs_conversion and document_total is not None:
        if (
            local_total is not None
            and abs(document_total - local_total) <= Decimal("1.00")
        ):
            needs_conversion = True
        elif (
            explicit_foreign_total is not None
            and abs(document_total - explicit_foreign_total) > Decimal("1.00")
            and document_total > explicit_foreign_total * Decimal("1.5")
        ):
            needs_conversion = True

    if needs_conversion:
        data["accounting_currency"] = "TRY"
        for document_field, local_field in local_mappings:
            if data.get(local_field) in (
                None,
                "",
            ) and data.get(document_field) not in (None, ""):
                data[local_field] = data[document_field]
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            if item.get("local_unit_price") in (None, "") and item.get(
                "unit_price"
            ) not in (None, ""):
                item["local_unit_price"] = item["unit_price"]
            if item.get("local_total_price") in (None, "") and item.get(
                "total_price"
            ) not in (None, ""):
                item["local_total_price"] = item["total_price"]
            item["local_amount_currency"] = "TRY"
        local_total = parse_localized_decimal(data.get("local_total"))

    if (
        (rate is None or rate <= 0)
        and needs_conversion
        and local_total is not None
        and local_total > 0
        and explicit_foreign_total is not None
        and explicit_foreign_total > 0
    ):
        rate = local_total / explicit_foreign_total
        data["exchange_rate"] = format(
            rate.quantize(Decimal("0.000001")), "f"
        ).rstrip("0").rstrip(".")

    if rate is not None and rate > 0:
        data["fx_conversion_required"] = False
        if needs_conversion:
            for document_field, local_field in local_mappings:
                local_value = parse_localized_decimal(data.get(local_field))
                if local_value is not None:
                    data[document_field] = _decimal_string(local_value / rate)

            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                local_unit_price = parse_localized_decimal(
                    item.get("local_unit_price")
                )
                local_total_price = parse_localized_decimal(
                    item.get("local_total_price")
                )
                converted_total_price = (
                    quantize_money(local_total_price / rate)
                    if local_total_price is not None
                    else None
                )
                if local_unit_price is not None:
                    converted_unit_price = local_unit_price / rate
                    quantity = parse_localized_decimal(item.get("quantity"))
                    if (
                        quantity is not None
                        and quantity > 0
                        and converted_total_price is not None
                    ):
                        line_based_unit_price = converted_total_price / quantity
                        if (
                            abs(line_based_unit_price - converted_unit_price)
                            <= Decimal("0.01")
                        ):
                            converted_unit_price = line_based_unit_price
                    item["unit_price"] = _unit_price_string(
                        converted_unit_price
                    )
                if converted_total_price is not None:
                    item["total_price"] = _decimal_string(converted_total_price)
                item["amount_currency"] = "USD"
    else:
        data["fx_conversion_required"] = bool(needs_conversion)
        if needs_conversion:
            # Never relabel unconverted TRY figures as USD.  Keep the source
            # amounts in local_* so a later rate-resolution step can convert
            # them, while validation prevents an incorrect USD draft.
            for document_field, _local_field in local_mappings:
                data[document_field] = None
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                item["unit_price"] = None
                item["total_price"] = None
                item["amount_currency"] = "USD"

    if explicit_foreign_total is not None:
        data["foreign_total"] = _decimal_string(explicit_foreign_total)
        data["total_amount"] = data["foreign_total"]
    elif rate is not None and rate > 0:
        local_total = parse_localized_decimal(data.get("local_total"))
        if local_total is not None:
            data["foreign_total"] = _decimal_string(local_total / rate)
            data["total_amount"] = data["foreign_total"]
        else:
            total_amount = parse_localized_decimal(data.get("total_amount"))
            if total_amount is not None:
                data["foreign_total"] = _decimal_string(total_amount)

    local_total = parse_localized_decimal(data.get("local_total"))
    foreign_total = parse_localized_decimal(data.get("foreign_total"))
    if (
        rate is not None
        and rate > 0
        and local_total is not None
        and foreign_total is not None
    ):
        data["fx_math_is_valid"] = abs(
            (foreign_total * rate) - local_total
        ) <= Decimal("1.00")

    return data


def _is_model_selection_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "404" in text
        or "not found" in text
        or "not supported" in text
        or "unsupported" in text
    )


def _require_genai_sdk() -> None:
    if genai is None or genai_types is None:
        raise RuntimeError(
            "The google-genai package is required for Gemini extraction. "
            "Install the dependencies from requirements.txt."
        )


def _create_client(api_key: str | None):
    _require_genai_sdk()
    if api_key:
        return genai.Client(api_key=api_key)
    return genai.Client()


def _candidate_model_names(client) -> list[str]:
    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    candidates: list[str] = []

    for model_name in (configured_model, *FALLBACK_GEMINI_MODELS):
        if model_name and model_name not in candidates:
            candidates.append(model_name)

    try:
        for model_info in client.models.list():
            actions = getattr(model_info, "supported_actions", []) or []
            if not any(
                str(action).replace("_", "").lower() == "generatecontent"
                for action in actions
            ):
                continue

            model_name = getattr(model_info, "name", "")
            if model_name.startswith("models/"):
                model_name = model_name.split("/", 1)[1]
            if model_name and model_name not in candidates:
                candidates.append(model_name)
    except Exception:
        pass

    return candidates


def _generate_content_with_available_model(client, input_data: list) -> str:
    last_model_error: Exception | None = None

    for model_name in _candidate_model_names(client):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=input_data,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            return response.text
        except Exception as exc:
            if not _is_model_selection_error(exc):
                raise
            last_model_error = exc

    raise RuntimeError(
        "No usable Gemini model found for generateContent. "
        "Set GEMINI_MODEL to a model listed by ModelService.ListModels."
    ) from last_model_error


def _load_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _stringify_amount_fields(data: dict) -> dict:
    data = _normalize_ai_usd_currency(data)

    for key in (
        "subtotal",
        "discount_amount",
        "tax_amount",
        "total_amount",
        "exchange_rate",
        "foreign_total",
        "local_subtotal",
        "local_discount_amount",
        "local_tax_amount",
        "local_total",
    ):
        if key in data and data[key] is not None:
            data[key] = str(data[key])

    for item in data.get("items", []):
        for key in (
            "quantity",
            "unit_price",
            "total_price",
            "tax_rate",
            "local_unit_price",
            "local_total_price",
        ):
            if key in item and item[key] is not None:
                item[key] = str(item[key])

    postal_address = normalize_customer_postal_address(
        data.get("customer_postal_address")
        or (
            data.get("customer_address")
            if isinstance(data.get("customer_address"), dict)
            else None
        )
    )
    if postal_address:
        data["customer_postal_address"] = postal_address
        if not isinstance(data.get("customer_address"), str):
            data["customer_address"] = format_customer_postal_address(
                postal_address
            )

    return normalize_invoice_serial_numbers(data)


def extract_invoice_with_ai(file_bytes: bytes, mime_type: str = "application/pdf") -> dict:
    """
    Extract invoice data using Gemini. The response schema is described in the
    prompt instead of generation_config because Render/Gemini package versions
    can reject Pydantic schema fields such as "default".
    """
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("Warning: GEMINI_API_KEY is not set.")

    if mime_type in ["image/jpeg", "image/png", "image/webp"]:
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(file_bytes))
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")

            max_size = 1600
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            output_buffer = io.BytesIO()
            image.save(output_buffer, format="JPEG", quality=75, optimize=True)
            file_bytes = output_buffer.getvalue()
            mime_type = "image/jpeg"
            print(f"Compressed image for Gemini. New size: {len(file_bytes)} bytes.")
        except Exception as exc:
            print(f"Image compression skipped due to error: {exc}")

    prompt = USD_EXTRACTION_INSTRUCTIONS + "\n\n" + """
Sen uzman bir muhasebe asistanisin. Ekli fatura belgesini dikkatlice analiz et
ve sadece gecerli JSON dondur. Markdown, aciklama, kod blogu veya ek metin yazma.

DİKKAT: Faturadaki TÜM KALEMLERİ (satırları) eksiksiz olarak 'items' dizisine ekle.
DİKKAT: Eğer faturada İskonto (Discount) varsa "discount_amount" alanına yazmayı unutma!
DİKKAT: JSON formatının KESİNLİKLE GEÇERLİ (VALID) olduğundan emin ol. Özellikle 'items' dizisi içindeki objelerde süslü parantez '{}' kapatmayı ve aralardaki virgülleri kesinlikle unutma.
DİKKAT: "notes" alanına yazacağın metin uzunsa veya satır atlamaları (enter) içeriyorsa JSON'ı bozmaması için tüm satır atlamalarını boşluk karakteri ile değiştir (tek satır yap) ve tırnak işaretlerini '\\"' şeklinde düzgünce kaç (escape) karakteriyle yaz.
DİKKAT: Müşteri/Alıcı ünvanı her zaman "Sayın", "Müşteri" vb. etiketlerle belirtilmeyebilir. Adresin ve VKN/TCKN numarasının (genellikle 10 veya 11 haneli sayı) bulunduğu bloktaki şirket/kişi ismini alıcı ünvanı ("customer_name") olarak kabul et. Satıcı bilgilerini (genellikle en üstte veya logolu olan) alıcı ünvanına yazma!

Beklenen JSON alani:
{
  "invoice_no": "string veya null",
  "invoice_series": "Faturanin sag ust kosesinde 'Seri:' veya 'Seri No:' yazan seri numarasi string (Örn: A, GİB, AB). Faturada acikca seri numarasi yoksa KESINLIKLE null dondur, asla tahmin etme veya fatura numarasindan turetme.",
  "date": "YYYY-MM-DD veya DD.MM.YYYY",
  "time": "HH:MM veya HH:MM:SS",
  "customer_tax_id": "10 veya 11 haneli VKN/TCKN; belgede yoksa bos string",
  "customer_name": "Alicinin (Musterinin) Unvani veya Adi Soyadi (string)",
  "customer_address": "Alicinin belgede yazan acik adresinin ham, tek satir metni (varsa)",
  "customer_postal_address": {
    "street_name": "Cadde veya sokak adi; yoksa bos string",
    "building_name": "Apartman, site, plaza veya bina adi; yoksa bos string",
    "building_number": "Bina/kapi numarasi; yoksa bos string",
    "city_subdivision_name": "Ilce adi; yoksa bos string",
    "city_name": "Il/sehir adi; yoksa bos string",
    "postal_zone": "Posta kodu; yoksa bos string",
    "district": "Mahalle adi; yoksa bos string",
    "country_code": "ISO 3166-1 alpha-2 ulke kodu (TR, DE, US gibi); bilinmiyorsa bos string",
    "country_name": "Ulke adi; yoksa bos string",
    "address_lines": ["Yukaridaki alanlara kayipsiz yerlestirilemeyen ek adres satirlari; yoksa bos dizi"]
  },
  "subtotal": 0.0,
  "discount_amount": 0.0,
  "tax_amount": 0.0,
  "total_amount": 0.0,
  "currency": "TRY veya USD veya EUR veya GBP",
  "document_currency": "Uyumsoft belge para birimi; USD ifadesi varsa USD",
  "settlement_currency": "Tahsilat para birimi; USD ifadesi varsa USD",
  "accounting_currency": "Belgede kalemlerin yazildigi muhasebe para birimi; TRY veya USD veya EUR veya GBP",
  "has_usd_mention": false,
  "currency_evidence": "Para birimi kararini kanitlayan faturadaki kisa ifade; yoksa bos string",
  "exchange_rate": "faturada acikca yazan doviz kuru; yoksa null",
  "foreign_total": "Faturada acikca yazan doviz toplami; yoksa null",
  "local_subtotal": "USD tahsilatli faturada TL ara toplam; yoksa null",
  "local_discount_amount": "USD tahsilatli faturada TL iskonto; yoksa null",
  "local_tax_amount": "USD tahsilatli faturada TL vergi; yoksa null",
  "local_total": "USD tahsilatli faturada TL genel toplam; yoksa null",
  "fx_conversion_required": false,
  "fx_math_is_valid": "foreign_total * exchange_rate ile local_total uyumluysa true; kontrol edilemiyorsa null",
  "notes": "faturadaki aciklama veya not (JSON formatini bozmayacak sekilde ozel karakterlerden arindirilmis tek satir)",
  "items": [
    {
      "code": "urun/stok kodu veya bos string",
      "description": "urun veya hizmet adi (seri numaralari haric)",
      "quantity": 0.0,
      "unit_price": 0.0,
      "total_price": 0.0,
      "amount_currency": "Kalem tutarlarinin para birimi",
      "local_unit_price": "USD tahsilatli faturada orijinal TL birim fiyat; yoksa null",
      "local_total_price": "USD tahsilatli faturada orijinal TL satir toplami; yoksa null",
      "local_amount_currency": "Yerel tutarlarin para birimi; genellikle TRY",
      "tax_rate": 20.0,
      "serial_numbers": ["bu urun kalemine ait, faturada acikca yazan seri numaralarini karakterlerini degistirmeden tek tek ekle; tilda (~), virgul, noktali virgul veya satir sonuyla ayrilanlari ayri eleman yap; fatura seri numarasi, fatura numarasi, miktar, fiyat veya urun kodunu buraya yazma; yoksa bos dizi []"]
    }
  ]
}

Tum satir kalemlerini eksiksiz oku. Miktar * birim fiyat = satir toplami ve
subtotal - discount_amount + tax_amount = total_amount tutarliligini kontrol et.
Ondalikli degerleri JSON number olarak ver. JSON formatini asla bozma!
""".strip()

    _require_genai_sdk()
    input_data = [
        genai_types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
        prompt,
    ]

    client = _create_client(api_key)
    try:
        raw_json = _generate_content_with_available_model(client, input_data)
    finally:
        client.close()
    try:
        return _stringify_amount_fields(_load_json_response(raw_json))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse Gemini JSON output: {exc}\nRaw output: {raw_json}")

