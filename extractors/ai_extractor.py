import os
import io
import json
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List, Optional

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
FALLBACK_GEMINI_MODELS = (
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
)

# Define the expected JSON structure using Pydantic
class InvoiceItem(BaseModel):
    description: str = Field(description="Müşteriye satılan ürün veya hizmetin tam adı / açıklaması.")
    quantity: float = Field(description="Miktar / Adet.")
    unit_price: float = Field(description="Birim Fiyat (KDV Hariç).")
    total_price: float = Field(description="Satır Toplam Fiyat (Miktar * Birim Fiyat).")
    tax_rate: float = Field(description="KDV Oranı (Örn: 20 veya 18 veya 10).")

class InvoiceData(BaseModel):
    invoice_no: Optional[str] = Field(description="Fatura Numarası (Genellikle 16 haneli harf ve rakamdan oluşur, örn: GIB2023000000012).")
    date: str = Field(description="Fatura Tarihi (Format: YYYY-MM-DD).")
    customer_tax_id: str = Field(description="Alıcının VKN (Vergi Kimlik Numarası) veya TCKN numarası (10 veya 11 haneli).")
    customer_name: str = Field(description="Alıcının Unvanı / Adı Soyadı.")
    subtotal: float = Field(description="Mal Hizmet Toplam Tutarı (Ara Toplam / KDV Hariç Toplam).")
    tax_amount: float = Field(description="Hesaplanan KDV Tutarı Toplamı.")
    total_amount: float = Field(description="Ödenecek Toplam Tutar (Genel Toplam / KDV Dahil Toplam).")
    currency: str = Field(description="Para Birimi (Örn: TRY, USD, EUR). TRY varsayılandır.")
    items: List[InvoiceItem] = Field(description="Faturadaki ürün/hizmet kalemlerinin listesi.")

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
                "response_schema": InvoiceData,
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


def extract_invoice_with_ai(file_bytes: bytes, mime_type: str = "application/pdf") -> dict:
    """
    Extracts invoice data using Google Gemini.
    Returns the parsed dict matching the InvoiceData schema.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Cannot use AI Extractor.")

    genai.configure(api_key=api_key)

    prompt = (
        "Sen uzman bir muhasebe asistanısın. Ekli fatura belgesini (PDF veya Görüntü) dikkatlice analiz et "
        "ve içerisindeki tüm bilgileri istenilen JSON şemasına uygun olarak eksiksiz bir şekilde çıkar. "
        "Matematiksel tutarlılığa (Miktar * Birim Fiyat = Satır Toplamı, Ara Toplam + KDV = Genel Toplam) çok dikkat et. "
        "Kuruşlu değerleri float olarak ver (Örn: 100.50). "
        "Eğer Müşteri VKN veya TCKN bulunmuyorsa, '11111111111' gibi geçici bir değer koyma, belgedekini bulmaya çalış."
    )

    # Prepare the input data
    input_data = [
        {"mime_type": mime_type, "data": file_bytes},
        prompt
    ]

    # Parse the JSON string back into a Python dictionary
    raw_json = _generate_content_with_available_model(input_data)
    try:
        data = json.loads(raw_json)
        
        # Convert floats back to strings to maintain compatibility with the rest of the application
        if "subtotal" in data: data["subtotal"] = str(data["subtotal"])
        if "tax_amount" in data: data["tax_amount"] = str(data["tax_amount"])
        if "total_amount" in data: data["total_amount"] = str(data["total_amount"])
        
        for item in data.get("items", []):
            if "quantity" in item: item["quantity"] = str(item["quantity"])
            if "unit_price" in item: item["unit_price"] = str(item["unit_price"])
            if "total_price" in item: item["total_price"] = str(item["total_price"])
            if "tax_rate" in item: item["tax_rate"] = str(item["tax_rate"])

        return data
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse Gemini JSON output: {e}\nRaw output: {raw_json}")
