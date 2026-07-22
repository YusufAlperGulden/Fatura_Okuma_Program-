# AI Archive Search handoff

This feature is intentionally isolated on `agent/ai-archive-search`. It must not
be merged by copying this branch's `ui/index.html` over `main`: the branch was
created before the latest Dashboard work.

## Safe integration

1. Rebase/cherry-pick the feature onto the latest `main`.
2. Resolve `ui/index.html` by keeping every current Dashboard panel and adding
   only these two independent assets:
   - `<link rel="stylesheet" href="ai-history-search.css?v=1">`
   - `<script src="ai-history-search.js?v=1"></script>`
3. Keep `ui/app.js` from `main`. The AI UI is a standalone module and does not
   modify the normal archive search state or table.
4. Run the commands in **Verification** and perform a browser smoke test.

## Security model

- Gemini receives the natural-language sentence and the `QuerySpec` schema; it
  never receives invoice rows and cannot return SQL.
- Unknown fields are rejected. Sorts/statuses are allow-listed and every value
  is passed to SQLite as a bound parameter over a read-only connection.
- Gemini and result endpoints have independent per-client/global rate limits.
- Archive queries have a configurable SQLite execution deadline.
- Internal Uyumsoft document IDs, environment and messages are not returned.

The application currently has no authentication layer. Therefore this branch
must not be described as production-authorized access: before exposing the app
to untrusted users, protect the whole archive (normal and AI endpoints) with a
real login/session or an upstream access gateway.

## Environment variables

- `GEMINI_API_KEY` (required)
- `GEMINI_ARCHIVE_SEARCH_MODEL` (optional; default `gemini-2.5-flash`)
- `AI_ARCHIVE_GEMINI_TIMEOUT_MS` (default `20000`, bounded 5000–60000)
- `AI_ARCHIVE_RATE_LIMIT` / `AI_ARCHIVE_GLOBAL_RATE_LIMIT`
- `AI_ARCHIVE_RESULTS_RATE_LIMIT` / `AI_ARCHIVE_RESULTS_GLOBAL_RATE_LIMIT`
- `AI_ARCHIVE_RATE_WINDOW_SECONDS` (default `60`)
- `AI_ARCHIVE_SQL_TIMEOUT_MS` (default `2000`, bounded 100–10000)

## Verification

```powershell
python -m pytest tests/test_ai_archive_search.py tests/test_ai_history_ui_contract.py tests/test_api_contract_regressions.py tests/test_ui_contract.py -q
python -m py_compile archive_ai_search.py ai_archive_api.py api.py
node --check ui/ai-history-search.js
node tests/ai_history_search.test.js
git diff --check
```

After integration, verify in a browser that both the normal search bar and the
AI panel work independently and that the latest Dashboard graphs remain.
