from copy import deepcopy
from unittest.mock import patch

from extractors.pdf_extractor import (
    _apply_mode_b_usd_conversion,
    parse_invoice_text,
)
from extractors.ocr_extractor import (
    parse_image_invoice_ocr,
    parse_pdf_invoice_ocr,
)


SETTLEMENT_SENTENCE = (
    "İŞ BU FATURA BEDELİ 4.608,00 USD OLUP, "
    "BEDELİ USD OLARAK TAHSİL EDİLECEKTİR."
)


def _local_try_invoice(raw_text=SETTLEMENT_SENTENCE, exchange_rate="47,0517"):
    return {
        "_raw_text": raw_text,
        "currency": "TRY",
        "exchange_rate": exchange_rate,
        "subtotal": "180.678,53",
        "discount_amount": "0,00",
        "tax_amount": "36.135,71",
        "total_amount": "216.814,23",
        "items": [
            {
                "quantity": "2.000,00",
                "unit_price": "90,34",
                "total_price": "180.678,53",
            }
        ],
    }


def test_any_standalone_usd_mention_overrides_try_frequency():
    text = """
    Ara Toplam 1.000,00 TL
    KDV 200,00 TL
    Genel Toplam 1.200,00 TL
    Açıklama: Tahsilat para birimi USD olacaktır.
    """

    result = parse_invoice_text(text)

    assert result["currency"] == "USD"
    assert result["document_currency"] == "USD"
    assert result["settlement_currency"] == "USD"
    assert result["accounting_currency"] == "TRY"


def test_settlement_sentence_converts_try_rows_and_preserves_local_values():
    raw_text = f"""
    Birim Fiyat ₺90,34
    Toplam Fiyat ₺180.678,53
    Ara Toplam ₺180.678,53
    KDV ₺36.135,71
    Yekün ₺216.814,23
    Döviz Kuru: 47,0517
    Döviz Toplam: $4.608,00
    {SETTLEMENT_SENTENCE}
    """
    result = _local_try_invoice(raw_text)

    _apply_mode_b_usd_conversion(result)

    assert result["has_usd_mention"] is True
    assert result["currency"] == "USD"
    assert result["document_currency"] == "USD"
    assert result["settlement_currency"] == "USD"
    assert result["accounting_currency"] == "TRY"
    assert result["subtotal"] == "3840.00"
    assert result["tax_amount"] == "768.00"
    assert result["total_amount"] == "4608.00"
    assert result["foreign_total"] == "4608.00"
    assert result["local_subtotal"] == "180.678,53"
    assert result["local_tax_amount"] == "36.135,71"
    assert result["local_total"] == "216.814,23"
    assert result["fx_conversion_required"] is False
    assert result["fx_math_is_valid"] is True

    item = result["items"][0]
    assert item["unit_price"] == "1.92"
    assert item["total_price"] == "3840.00"
    assert item["local_unit_price"] == "90,34"
    assert item["local_total_price"] == "180.678,53"
    assert item["local_amount_currency"] == "TRY"
    assert item["amount_currency"] == "USD"


def test_required_settlement_sentence_converts_unlabelled_try_rows():
    raw_text = f"""
    Ara Toplam 180.678,53
    KDV 36.135,71
    YekÃ¼n 216.814,23
    DÃ¶viz Kuru: 47,0517
    {SETTLEMENT_SENTENCE}
    """
    result = _local_try_invoice(raw_text)

    _apply_mode_b_usd_conversion(result)

    assert result["currency"] == "USD"
    assert result["accounting_currency"] == "TRY"
    assert result["subtotal"] == "3840.00"
    assert result["tax_amount"] == "768.00"
    assert result["total_amount"] == "4608.00"
    assert result["local_total"] == "216.814,23"


def test_generic_usd_mention_converts_explicit_try_amounts_without_settlement_phrase():
    raw_text = """
    Para Birimi: USD
    Birim Fiyat: 400,00 TL
    Ara Toplam: 1.000,00 TL
    KDV: 200,00 TL
    Genel Toplam: 1.200,00 TL
    Döviz Kuru: 40,00
    """
    result = {
        "_raw_text": raw_text,
        "currency": "TRY",
        "exchange_rate": "40,00",
        "subtotal": "1.000,00",
        "discount_amount": "0,00",
        "tax_amount": "200,00",
        "total_amount": "1.200,00",
        "items": [{"unit_price": "400,00", "total_price": "1.000,00"}],
    }

    _apply_mode_b_usd_conversion(result)

    assert result["currency"] == "USD"
    assert result["subtotal"] == "25.00"
    assert result["tax_amount"] == "5.00"
    assert result["total_amount"] == "30.00"
    assert result["foreign_total"] == "30.00"
    assert result["local_total"] == "1.200,00"
    assert result["items"][0]["unit_price"] == "10.00"
    assert result["items"][0]["total_price"] == "25.00"


def test_single_try_amount_with_generic_usd_note_is_converted():
    result = {
        "_raw_text": "Not: USD tahsilat. Genel Toplam 1.200,00 TL. Kur 40,00",
        "currency": "TRY",
        "exchange_rate": "40,00",
        "subtotal": "1.000,00",
        "tax_amount": "200,00",
        "total_amount": "1.200,00",
        "items": [{"unit_price": "1.000,00", "total_price": "1.000,00"}],
    }

    _apply_mode_b_usd_conversion(result)

    assert result["currency"] == "USD"
    assert result["subtotal"] == "25.00"
    assert result["tax_amount"] == "5.00"
    assert result["total_amount"] == "30.00"


def test_printed_local_and_foreign_totals_can_derive_missing_rate():
    raw_text = f"""
    Ara Toplam ₺180.678,53
    KDV ₺36.135,71
    Yekün ₺216.814,23
    Döviz Toplam: 4.608,00 USD
    {SETTLEMENT_SENTENCE}
    """
    result = _local_try_invoice(raw_text, exchange_rate=None)

    _apply_mode_b_usd_conversion(result)

    assert result["exchange_rate"] == "47.051699"
    assert result["subtotal"] == "3840.00"
    assert result["tax_amount"] == "768.00"
    assert result["total_amount"] == "4608.00"
    assert result["fx_conversion_required"] is False
    assert result["fx_math_is_valid"] is True


def test_already_usd_denominated_rows_are_not_divided_again():
    raw_text = """
    Para Birimi USD
    Birim Fiyat $100,00
    Ara Toplam $100,00
    KDV $20,00
    Genel Toplam $120,00
    Döviz Kuru: 40,00
    """
    result = {
        "_raw_text": raw_text,
        "currency": "USD",
        "exchange_rate": "40,00",
        "subtotal": "100,00",
        "tax_amount": "20,00",
        "total_amount": "120,00",
        "items": [{"unit_price": "100,00", "total_price": "100,00"}],
    }

    _apply_mode_b_usd_conversion(result)

    assert result["accounting_currency"] == "USD"
    assert result["subtotal"] == "100,00"
    assert result["tax_amount"] == "20,00"
    assert result["total_amount"] == "120,00"
    assert "local_total" not in result
    assert result["items"][0]["unit_price"] == "100,00"


def test_native_usd_header_with_one_try_equivalent_is_not_divided_again():
    raw_text = """
    Para Birimi: USD
    Birim Fiyat 100,00
    Ara Toplam 100,00
    KDV 20,00
    Genel Toplam 120,00
    TL Kar\u015f\u0131l\u0131\u011f\u0131: 4.800,00 TL
    D\u00f6viz Kuru: 40,00
    """
    result = {
        "_raw_text": raw_text,
        "currency": "USD",
        "exchange_rate": "40,00",
        "subtotal": "100,00",
        "tax_amount": "20,00",
        "total_amount": "120,00",
        "items": [{"unit_price": "100,00", "total_price": "100,00"}],
    }

    _apply_mode_b_usd_conversion(result)

    assert result["accounting_currency"] == "USD"
    assert result["subtotal"] == "100,00"
    assert result["tax_amount"] == "20,00"
    assert result["total_amount"] == "120,00"
    assert "local_total" not in result
    assert result["items"][0]["unit_price"] == "100,00"


def test_pdf_conversion_keeps_unit_price_precision_needed_by_ubl():
    result = {
        "_raw_text": "Para Birimi USD Birim Fiyat 1,00 TL Kur 40,00",
        "currency": "TRY",
        "exchange_rate": "40,00",
        "subtotal": "1.000,00",
        "tax_amount": "200,00",
        "total_amount": "1.200,00",
        "items": [
            {
                "quantity": "1.000,00",
                "unit_price": "1,00",
                "total_price": "1.000,00",
            }
        ],
    }

    _apply_mode_b_usd_conversion(result)

    assert result["items"][0]["unit_price"] == "0.025"
    assert result["items"][0]["total_price"] == "25.00"


def test_usd_conversion_is_idempotent():
    raw_text = f"""
    Ara Toplam ₺180.678,53
    KDV ₺36.135,71
    Yekün ₺216.814,23
    Döviz Kuru: 47,0517
    Döviz Toplam: $4.608,00
    {SETTLEMENT_SENTENCE}
    """
    result = _local_try_invoice(raw_text)

    _apply_mode_b_usd_conversion(result)
    once = deepcopy(result)
    _apply_mode_b_usd_conversion(result)

    assert result == once


def test_pdf_and_image_ocr_paths_apply_the_same_usd_conversion():
    raw_text = """
    Not: USD tahsilat
    Ara Toplam 1.000,00 TL
    KDV 200,00 TL
    Genel Toplam 1.200,00 TL
    DÃ¶viz Kuru 40,00
    """
    parsed = {
        "_raw_text": raw_text,
        "currency": "TRY",
        "exchange_rate": "40,00",
        "subtotal": "1.000,00",
        "tax_amount": "200,00",
        "total_amount": "1.200,00",
        "items": [
            {
                "quantity": "1",
                "unit_price": "1.000,00",
                "total_price": "1.000,00",
            }
        ],
    }

    for parser, text_reader in (
        (parse_pdf_invoice_ocr, "extractors.ocr_extractor.extract_text_via_ocr"),
        (
            parse_image_invoice_ocr,
            "extractors.ocr_extractor.extract_text_from_image_via_ocr",
        ),
    ):
        with (
            patch(text_reader, return_value=raw_text),
            patch(
                "extractors.ocr_extractor.parse_invoice_text",
                return_value=deepcopy(parsed),
            ),
        ):
            result = parser("unused-test-path")

        assert result["currency"] == "USD"
        assert result["subtotal"] == "25.00"
        assert result["tax_amount"] == "5.00"
        assert result["total_amount"] == "30.00"


def test_explicit_try_settlement_overrides_usd_footnote():
    # User's exact Suatcan OCR text pattern containing a USD footnote but a TRY settlement string
    ocr_text = """
    Ara Toplam ₺2.368,33
    KDV 18(%20) ₺473,67

    İŞ BU FATURA BEDELİ 2.842,00 TL OLUP, BEDELİ TL OLARAK TAHSİL EDİLECEKTİR. VADESİ:Peşin

    * Fatura üzerindeki iş bu döviz kuru ve TL tutarı sadece muhasebe kaydı için
    geçerli olup cari hesap ödemesi için değildir. Siparişe ilişkin ödeme
    yükümlülüğü, ilgili mevzuat doğrultusunda USD olarak veya USD ye endeksli
    şekilde ödeme günü hesaplanacak Türk Lirası cinsinden ifa edilebilir. Mevzuat
    gereğince ödemenin Türk Lirası cinsinden yapılması gerekiyor ise,
    """
    from extractors.pdf_extractor import parse_invoice_text
    
    result = parse_invoice_text(ocr_text)
    
    assert result["currency"] == "TRY"
    assert result["document_currency"] == "TRY"
    assert result["settlement_currency"] == "TRY"
    assert result["accounting_currency"] == "TRY"

def test_explicit_try_settlement_overrides_usd_footnote():
    # User's exact Suatcan OCR text pattern containing a USD footnote but a TRY settlement string
    ocr_text = """
    Ara Toplam ₺2.368,33
    KDV 18(%20) ₺473,67

    İŞ BU FATURA BEDELİ 2.842,00 TL OLUP, BEDELİ TL OLARAK TAHSİL EDİLECEKTİR. VADESİ:Peşin

    * Fatura üzerindeki iş bu döviz kuru ve TL tutarı sadece muhasebe kaydı için
    geçerli olup cari hesap ödemesi için değildir. Siparişe ilişkin ödeme
    yükümlülüğü, ilgili mevzuat doğrultusunda USD olarak veya USD ye endeksli
    şekilde ödeme günü hesaplanacak Türk Lirası cinsinden ifa edilebilir. Mevzuat
    gereğince ödemenin Türk Lirası cinsinden yapılması gerekiyor ise,
    """
    from extractors.pdf_extractor import parse_invoice_text
    
    result = parse_invoice_text(ocr_text)
    
    assert result["currency"] == "TRY"
    assert result["document_currency"] == "TRY"
    assert result["settlement_currency"] == "TRY"
    assert result["accounting_currency"] == "TRY"
