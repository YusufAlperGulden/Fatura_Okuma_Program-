from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ai_history_search_is_loaded_as_an_independent_module():
    html = (PROJECT_ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    ai_javascript = (PROJECT_ROOT / "ui" / "ai-history-search.js").read_text(encoding="utf-8")

    assert 'id="history-search-input"' in html
    assert 'src="ai-history-search.js?v=1"' in html
    assert 'href="ai-history-search.css?v=1"' in html
    assert "historyCurrentPage" not in ai_javascript
    assert "getElementById('history-table-body')" not in ai_javascript
    assert "id = 'ai-history-table-body'" in ai_javascript


def test_ai_history_search_interprets_once_and_reuses_the_validated_spec():
    ai_javascript = (PROJECT_ROOT / "ui" / "ai-history-search.js").read_text(encoding="utf-8")

    assert ai_javascript.count("/api/history/ai/interpret") == 1
    assert ai_javascript.count("/api/history/ai/results") == 1
    assert "spec: state.spec" in ai_javascript
    assert "state.spec = interpreted.spec" in ai_javascript
    assert "new AbortController()" in ai_javascript
    assert "request.revision === state.revision" in ai_javascript


def test_ai_history_search_renders_server_data_without_html_injection():
    ai_javascript = (PROJECT_ROOT / "ui" / "ai-history-search.js").read_text(encoding="utf-8")

    assert ".innerHTML" not in ai_javascript
    assert ".textContent" in ai_javascript
    assert "replaceChildren" in ai_javascript
    assert "SELECT " not in ai_javascript
    assert "customer_tax_id" in ai_javascript


def test_ai_history_search_discloses_what_is_sent_to_gemini():
    ai_javascript = (PROJECT_ROOT / "ui" / "ai-history-search.js").read_text(encoding="utf-8")

    assert "Sorunuz Gemini’ye gönderilir" in ai_javascript
    assert "fatura kayıtları gönderilmez" in ai_javascript
