from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_line_tax_amount_column_is_not_rendered_or_exported():
    html = (PROJECT_ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "<th>KDV Tutarı</th>" not in html
    assert "'KDV Tutari'" not in javascript
    assert "item.tax_amount" not in javascript
    assert "td.colSpan = 7" in javascript


def test_invalid_draft_action_has_a_popup_and_send_guard():
    javascript = (PROJECT_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "if (!currentInvoiceIsValid)" in javascript
    assert "showDraftValidationPopup();" in javascript
    assert "window.alert(`${title}\\n\\n${detail}`);" in javascript
    assert "currentValidationState !== 'valid'" in javascript
    assert "validationRevision += 1" in javascript
    assert "capturedValidationRevision !== validationRevision" in javascript
