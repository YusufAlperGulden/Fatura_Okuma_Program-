import io
import json
import os

import google.generativeai as genai


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
FALLBACK_GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)


def _is_model_selection_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "404" in text
        or "not found" in text
        or "not supported" in text
        or "unsupported" in text
    )


def _candidate_model_names() -> list[str]:
    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    candidates: list[str] = []

    for model_name in (configured_model, *FALLBACK_GEMINI_MODELS):
        if model_name and model_name not in candidates:
            candidates.append(model_name)

    try:
        for model_info in genai.list_models():
            methods = getattr(model_info, "supported_generation_methods", [])
            if "generateContent" not in methods:
                continue

            model_name = getattr(model_info, "name", "")
            if model_name.startswith("models/"):
                model_name = model_name.split("/", 1)[1]
            if model_name and model_name not in candidates:
                candidates.append(model_name)
    except Exception:
        pass

    return candidates


def _generate_content_with_available_model(input_data: list) -> str:
    last_model_error: Exception | None = None

    for model_name in _candidate_model_names():
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0,
            },
        )

        try:
            response = model.generate_content(input_data)
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
    for key in ("subtotal", "discount_amount", "tax_amount", "total_amount", "exchange_rate"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])

    for item in data.get("items", []):
        for key in ("quantity", "unit_price", "total_price", "tax_rate"):
            if key in item and item[key] is not None:
                item[key] = str(item[key])

    return data


def extract_invoice_with_ai(file_bytes: bytes, mime_type: str = "application/pdf") -> dict:
    """
    Extract invoice data using Gemini. The response schema is described in the
    prompt instead of generation_config because Render/Gemini package versions
    can reject Pydantic schema fields such as "default".
    """
    api_key = os.environ.get("GEMINI_API_KEY")

    if api_key:
        genai.configure(api_key=api_key)
    else:
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

    prompt = """
Sen uzman bir muhasebe asistanisin. Ekli fatura belgesini dikkatlice analiz et
ve sadece gecerli JSON dondur. Markdown, aciklama, kod blogu veya ek metin yazma.

DİKKAT: Faturadaki TÜM KALEMLERİ (satırları) eksiksiz olarak 'items' dizisine ekle.
DİKKAT: Eğer faturada İskonto (Discount) varsa "discount_amount" alanına yazmayı unutma!
DİKKAT: JSON formatının KESİNLİKLE GEÇERLİ (VALID) olduğundan emin ol. Özellikle 'items' dizisi içindeki objelerde süslü parantez '{}' kapatmayı ve aralardaki virgülleri kesinlikle unutma.
DİKKAT: "notes" alanına yazacağın metin uzunsa veya satır atlamaları (enter) içeriyorsa JSON'ı bozmaması için tüm satır atlamalarını boşluk karakteri ile değiştir (tek satır yap) ve tırnak işaretlerini '\\"' şeklinde düzgünce kaçış (escape) karakteriyle yaz.

Beklenen JSON alani:
{
  "invoice_no": "string veya null",
  "invoice_series": "Faturanin sag ust kosesinde 'Seri:' veya 'Seri No:' yazan seri numarasi string veya null",
  "date": "YYYY-MM-DD veya DD.MM.YYYY",
  "time": "HH:MM veya HH:MM:SS",
  "customer_tax_id": "10 veya 11 haneli VKN/TCKN; belgede yoksa bos string",
  "customer_name": "string",
  "subtotal": 0.0,
  "discount_amount": 0.0,
  "tax_amount": 0.0,
  "total_amount": 0.0,
  "currency": "TRY veya USD veya EUR veya GBP",
  "exchange_rate": "faturada acikca yazan doviz kuru; yoksa null",
  "notes": "faturadaki aciklama veya not (JSON formatini bozmayacak sekilde ozel karakterlerden arindirilmis tek satir)",
  "items": [
    {
      "code": "urun/stok kodu veya bos string",
      "description": "urun veya hizmet adi",
      "quantity": 0.0,
      "unit_price": 0.0,
      "total_price": 0.0,
      "tax_rate": 20.0
    }
  ]
}

Tum satir kalemlerini eksiksiz oku. Miktar * birim fiyat = satir toplami ve
subtotal - discount_amount + tax_amount = total_amount tutarliligini kontrol et.
Ondalikli degerleri JSON number olarak ver. JSON formatini asla bozma!
""".strip()

    input_data = [
        {"mime_type": mime_type, "data": file_bytes},
        prompt,
    ]

    raw_json = _generate_content_with_available_model(input_data)
    try:
        return _stringify_amount_fields(_load_json_response(raw_json))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse Gemini JSON output: {exc}\nRaw output: {raw_json}")
