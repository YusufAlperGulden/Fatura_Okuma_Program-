# Public Invoice Application Roadmap

## Product access decision

- The website, static UI, API documentation, `/upload`, and `/send-uyumsoft` are intentionally public.
- Anonymous visitors may upload invoices and create Uyumsoft drafts.
- The project will not require login, Basic Auth, API keys, CAPTCHA, IP allowlists, or request rate limits.
- Third-party service credentials such as `GEMINI_API_KEY` and Uyumsoft credentials remain server-side because those services require them; visitors do not provide credentials.
- Uyumsoft operations remain limited to `draft`, matching the product requirement that visitors create drafts rather than finalize invoices.
- Invoice validation, XSS escaping, CSV formula escaping, supported-file checks, and duplicate-click protection remain data-integrity safeguards rather than access restrictions.

## Phase 0 — Public application foundation — Completed

- Removed server-side SQLite history storage and `/api/history`.
- Removed site-wide Basic Auth and ADMIN environment requirements.
- Kept the UI and API publicly accessible without user credentials.
- Removed automatic Uyumsoft submission; visitors explicitly confirm draft creation.
- Forced the backend Uyumsoft action to `draft` regardless of client input.

## Phase 1 — Backend contract and validation

- Introduce explicit Pydantic request and response models.
- Add a side-effect-free `/validate` endpoint.
- Return accurate HTTP status codes and stable error payloads.
- Keep all application endpoints anonymously accessible.
- Do not add authentication, authorization, CAPTCHA, IP restrictions, or rate limiting.

## Phase 2: "Edit Before Send" Implementation (Simple)

We will implement the "Edit Before Send" feature using a standard, straightforward approach. We will drop the overly strict architectural rules (like complex Pydantic models and AbortControllers) but will still fix the critical bugs that caused the previous crash.

### 1. Fix UI Crash & DOM Focus
- Implement the missing `appendInputCell()` function so the table renders correctly.
- Split `showResults()` into two parts: one to build the inputs initially, and one to update the validation badges/totals. This prevents the inputs from being rebuilt while the user is typing, solving the "cursor focus loss" bug.

### 2. State & Send Button
- Bind the input fields to update `currentInvoiceData` immediately when typed.
- Wait 500ms after typing to call the `/api/validate` endpoint in the background.
- Keep the "Send" button disabled while the validation is loading to prevent sending stale data.

### 3. CSV Export
- Fix the CSV exporter so it reads the `.value` from the active input fields, rather than reading empty text content.

### 4. Simple Backend Validation
- Keep the backend validation simple as it currently is. We will not force strict nested Pydantic models, but we will ensure the `/api/validate` endpoint safely handles edits without returning 500 errors.

## Phase 3 — Data rendering and export correctness

- Render invoice-derived text with `textContent` and `createElement`.
- Preserve spreadsheet-formula escaping and RFC 4180 CSV quoting.
- Preserve the PDF/JPEG/PNG/WebP preview allowlist.

## Phase 4 — Browser-local history

- Store optional history in IndexedDB in each visitor's browser profile.
- Use `crypto.randomUUID()` for record identifiers and `issuerVkn|invoiceNo` as a deduplication key.
- Support optional JSON export and import for browser-local backups.
- Do not migrate legacy server-side SQLite history.

## Phase 5 — Production tests

- Verify anonymous access to the UI, upload flow, validation, and Uyumsoft draft endpoint.
- Test malformed invoice payloads and stable validation errors.
- Test invoice-derived XSS payload rendering and CSV formula escaping.
- Test concurrent uploads, cancellation, double-click protection, and stale-response handling.
- Verify that client-supplied actions cannot change the backend operation from `draft` to final submission.

## Confirmed scope

This roadmap intentionally permits unrestricted anonymous access and anonymous Uyumsoft draft creation. Future phases must not add user authentication or traffic limits unless the product owner explicitly changes this requirement.
