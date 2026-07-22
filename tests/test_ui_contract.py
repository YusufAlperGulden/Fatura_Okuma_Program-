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

    assert "if (currentValidationState !== 'valid' || !currentInvoiceIsValid)" in javascript
    assert "showDraftValidationPopup();" in javascript
    assert "window.alert(`${title}\\n\\n${detail}`);" in javascript
    assert "currentValidationState !== 'valid'" in javascript
    assert "validationRevision += 1" in javascript
    assert "capturedValidationRevision !== validationRevision" in javascript


def test_edit_state_is_canonicalized_and_sent_as_an_immutable_snapshot():
    javascript = (PROJECT_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "recalculateEditedAmounts(itemIndex, fieldName);" in javascript
    assert "currentInvoiceData = result.data;" in javascript
    assert "const invoiceSnapshot = JSON.parse(JSON.stringify(currentInvoiceData));" in javascript
    assert "invoice_data: invoiceSnapshot" in javascript
    assert "setEditingDisabled(true);" in javascript
    assert "draftSendInProgress" in javascript
    assert "input.dataset.fieldName = fieldName;" in javascript
    assert "input.dataset.itemIndex = String(itemIndex);" in javascript


def test_uyumsoft_portal_and_environment_are_loaded_from_runtime_config():
    html = (PROJECT_ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert 'id="environment-select"' in html
    assert "fetch('/runtime-config')" in javascript
    assert "config.uyumsoft_portal_url" in javascript
    assert "Uyumsoft ortamı: GERÇEK / CANLI" in javascript
    assert "http://portal-test.uyumsoft.com.tr/Taslak" not in javascript


def test_batch_upload_times_out_one_file_without_canceling_the_batch():
    javascript = (PROJECT_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert "const BATCH_FILE_TIMEOUT_MS = 2 * 60 * 1000;" in javascript
    assert "fetchWithTimeout(" in javascript
    assert "capturedBatchUploadController.signal" in javascript
    assert "if (error.name === 'TimeoutError')" in javascript
    assert "item.timedOut = true;" in javascript
    assert "Zaman Aşımı (Geçildi)" in javascript
    assert "if (capturedBatchUploadController.signal.aborted)" in javascript
