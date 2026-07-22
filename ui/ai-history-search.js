(function (root, factory) {
    'use strict';

    const api = factory();

    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }

    root.AiHistorySearch = api;

    if (typeof document !== 'undefined') {
        const start = () => api.mount(document);
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', start, { once: true });
        } else {
            start();
        }
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    const PAGE_SIZE = 10;

    const SORT_LABELS = {
        invoice_date: 'Fatura tarihi',
        archive_date: 'Arşiv tarihi',
        amount_try: 'Tutar',
        customer: 'Cari',
        created_at: 'Arşiv tarihi',
        invoice_no: 'Fatura numarası',
    };

    const LOCAL_STATUS_LABELS = {
        error: 'Hatalı',
        valid: 'Başarılı',
    };

    const UYUMSOFT_STATUS_LABELS = {
        approved: 'Onaylandı',
        canceled: 'İptal edildi',
        declined: 'Reddedildi',
        draft: 'Taslak',
        earchive_canceled: 'E-Arşiv iptal edildi',
        error: 'Hata',
        processing: 'İşleniyor',
        queued: 'Sırada',
        returned: 'İade edildi',
        sent_to_gib: 'GİB’e gönderildi',
        unknown: 'Bilinmiyor',
        waiting_for_approval: 'Onay bekliyor',
    };

    function hasValue(value) {
        return value !== null && value !== undefined && value !== '';
    }

    function buildFilterChipEntries(spec) {
        if (!spec || typeof spec !== 'object' || Array.isArray(spec)) return [];

        const chips = [];
        const add = (label, value) => {
            if (hasValue(value)) chips.push({ label, value: String(value) });
        };

        add('Metin', spec.search_text);
        add('Cari', spec.customer);
        add('VKN/TCKN', spec.tax_id);
        add('Fatura No', spec.invoice_no);
        add('Fatura başlangıç', spec.invoice_date_from);
        add('Fatura bitiş', spec.invoice_date_to);
        add('Arşiv başlangıç', spec.archive_date_from);
        add('Arşiv bitiş', spec.archive_date_to);
        add('En az', hasValue(spec.min_amount_try) ? `${formatNumber(spec.min_amount_try)} TL` : null);
        add('En fazla', hasValue(spec.max_amount_try) ? `${formatNumber(spec.max_amount_try)} TL` : null);
        add('Para birimi', spec.currency);
        add(
            'Yerel durum',
            hasValue(spec.local_status)
                ? (LOCAL_STATUS_LABELS[spec.local_status] || spec.local_status)
                : null,
        );
        add(
            'Uyumsoft durumu',
            hasValue(spec.uyumsoft_status)
                ? (UYUMSOFT_STATUS_LABELS[spec.uyumsoft_status] || spec.uyumsoft_status)
                : null,
        );

        if (typeof spec.has_uyumsoft_document === 'boolean') {
            add('Uyumsoft', spec.has_uyumsoft_document ? 'Gönderilmiş' : 'Gönderilmemiş');
        }

        if (hasValue(spec.sort_by)) {
            const direction = String(spec.sort_direction || 'desc').toLowerCase() === 'asc'
                ? 'artan'
                : 'azalan';
            add('Sıralama', `${SORT_LABELS[spec.sort_by] || spec.sort_by} · ${direction}`);
        }

        add('Sonuç sınırı', spec.result_limit);
        return chips;
    }

    function formatNumber(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return String(value ?? '-');
        return new Intl.NumberFormat('tr-TR', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
        }).format(numeric);
    }

    function formatAmount(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return '-';
        return `${new Intl.NumberFormat('tr-TR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(numeric)} TL`;
    }

    function formatDate(value) {
        if (!hasValue(value)) return '-';
        const text = String(value);
        return text.includes('T') ? text.split('T')[0] : text.split(' ')[0];
    }

    function extractErrorMessage(payload, fallback) {
        if (!payload) return fallback;
        if (typeof payload.message === 'string') return payload.message;
        if (typeof payload.detail === 'string') return payload.detail;
        if (payload.detail && typeof payload.detail.message === 'string') return payload.detail.message;
        if (Array.isArray(payload.detail)) {
            const messages = payload.detail
                .map(item => item && (item.msg || item.message))
                .filter(Boolean);
            if (messages.length) return messages.join(' ');
        }
        return fallback;
    }

    async function requestJson(url, body, signal) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal,
        });

        let payload = null;
        try {
            payload = await response.json();
        } catch (_error) {
            // A non-JSON proxy/error response is handled by the HTTP status below.
        }

        if (!response.ok || !payload || payload.success === false) {
            throw new Error(extractErrorMessage(payload, 'Yapay zekâ araması tamamlanamadı.'));
        }

        return payload.data || payload;
    }

    function element(documentRef, tagName, className, text) {
        const node = documentRef.createElement(tagName);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function makeButton(documentRef, text, className) {
        const button = element(documentRef, 'button', className, text);
        button.type = 'button';
        return button;
    }

    function mount(documentRef) {
        const historySection = documentRef.getElementById('history-section');
        const normalSearch = documentRef.getElementById('history-search-input');
        const normalHistoryPanel = normalSearch && normalSearch.closest('.glass-panel');

        if (!historySection || !normalHistoryPanel || documentRef.getElementById('ai-history-search-panel')) {
            return null;
        }

        const panel = element(documentRef, 'section', 'ai-history-panel glass-panel');
        panel.id = 'ai-history-search-panel';
        panel.setAttribute('aria-labelledby', 'ai-history-title');

        const glow = element(documentRef, 'div', 'ai-history-glow');
        glow.setAttribute('aria-hidden', 'true');
        panel.appendChild(glow);

        const header = element(documentRef, 'div', 'ai-history-header');
        const headingBlock = element(documentRef, 'div', 'ai-history-heading');
        const eyebrow = element(documentRef, 'div', 'ai-history-eyebrow');
        eyebrow.appendChild(element(documentRef, 'span', 'ai-history-sparkle', '✦'));
        eyebrow.appendChild(element(documentRef, 'span', '', 'GÜVENLİ AI FİLTRESİ'));
        const title = element(documentRef, 'h3', '', 'Yapay Zekâ ile Arşivde Ara');
        title.id = 'ai-history-title';
        const description = element(
            documentRef,
            'p',
            '',
            'Sorunuz Gemini’ye gönderilir; fatura kayıtları gönderilmez. AI yalnızca doğrulanmış filtreler oluşturur ve SQL üretemez.',
        );
        headingBlock.append(eyebrow, title, description);

        const independentNote = element(documentRef, 'div', 'ai-history-independent-note');
        independentNote.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--ai-color, #a855f7);"><path d="M21 12c-2.76 0-5.46-1.12-7.41-3.08A10.5 10.5 0 0 1 12 3c0 2.76-1.12 5.46-3.08 7.41A10.5 10.5 0 0 1 3 12c2.76 0 5.46 1.12 7.41 3.08A10.5 10.5 0 0 1 12 21c0-2.76 1.12-5.46 3.08-7.41A10.5 10.5 0 0 1 21 12Z"/></svg>';
        header.append(headingBlock, independentNote);
        panel.appendChild(header);

        const form = element(documentRef, 'form', 'ai-history-form');
        form.id = 'ai-history-form';
        const inputLabel = element(documentRef, 'label', 'ai-history-sr-only', 'Arşivde doğal dille ara');
        inputLabel.htmlFor = 'ai-history-query';
        const inputWrap = element(documentRef, 'div', 'ai-history-input-wrap');
        const inputIcon = element(documentRef, 'span', 'ai-history-input-icon', '✦');
        inputIcon.setAttribute('aria-hidden', 'true');
        const input = element(documentRef, 'input', 'ai-history-input');
        input.id = 'ai-history-query';
        input.type = 'search';
        input.autocomplete = 'off';
        input.maxLength = 500;
        input.placeholder = 'Örn. Temmuz ayındaki 50.000 TL üzeri faturaları göster';
        input.setAttribute('aria-describedby', 'ai-history-help');
        inputWrap.append(inputIcon, input);

        const submitButton = makeButton(documentRef, 'AI ile Ara', 'ai-history-submit');
        submitButton.type = 'submit';
        const clearButton = makeButton(documentRef, 'Temizle', 'ai-history-clear');
        clearButton.hidden = true;
        form.append(inputLabel, inputWrap, submitButton, clearButton);
        panel.appendChild(form);

        const help = element(documentRef, 'div', 'ai-history-help');
        help.id = 'ai-history-help';
        help.appendChild(element(documentRef, 'span', '', 'Örnekler:'));
        [
            'Bu ay 50.000 TL üzeri faturalar',
            'En yüksek tutarlı 5 fatura',
        ].forEach(example => {
            const exampleButton = makeButton(documentRef, example, 'ai-history-example');
            exampleButton.addEventListener('click', () => {
                input.value = example;
                form.requestSubmit();
            });
            help.appendChild(exampleButton);
        });
        panel.appendChild(help);

        const liveStatus = element(documentRef, 'div', 'ai-history-live');
        liveStatus.setAttribute('role', 'status');
        liveStatus.setAttribute('aria-live', 'polite');
        panel.appendChild(liveStatus);

        const errorBox = element(documentRef, 'div', 'ai-history-error');
        errorBox.setAttribute('role', 'alert');
        errorBox.hidden = true;
        panel.appendChild(errorBox);

        const results = element(documentRef, 'div', 'ai-history-results');
        results.hidden = true;
        const summary = element(documentRef, 'div', 'ai-history-summary');
        const explanation = element(documentRef, 'p', 'ai-history-explanation');
        const resultCount = element(documentRef, 'span', 'ai-history-result-count');
        summary.append(explanation, resultCount);
        const chips = element(documentRef, 'div', 'ai-history-chips');
        chips.setAttribute('aria-label', 'AI tarafından uygulanan filtreler');

        const tableWrap = element(documentRef, 'div', 'ai-history-table-wrap table-container');
        const table = element(documentRef, 'table', 'ai-history-table data-table');
        const caption = element(documentRef, 'caption', 'ai-history-sr-only', 'Yapay zekâ arama sonuçları');
        const thead = documentRef.createElement('thead');
        const headerRow = documentRef.createElement('tr');
        ['Tarih', 'Fatura No', 'Cari İsim', 'VKN/TCKN', 'Tutar (TL)', 'Durum'].forEach(label => {
            const th = element(documentRef, 'th', '', label);
            if (label === 'Tutar (TL)') th.className = 'ai-history-amount';
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        const tbody = documentRef.createElement('tbody');
        tbody.id = 'ai-history-table-body';
        table.append(caption, thead, tbody);
        tableWrap.appendChild(table);

        const pagination = element(documentRef, 'div', 'ai-history-pagination');
        const previousButton = makeButton(documentRef, 'Önceki', 'ai-history-page-button');
        const pageInfo = element(documentRef, 'span', 'ai-history-page-info', 'Sayfa 1 / 1');
        const nextButton = makeButton(documentRef, 'Sonraki', 'ai-history-page-button');
        previousButton.disabled = true;
        nextButton.disabled = true;
        pagination.append(previousButton, pageInfo, nextButton);

        results.append(summary, chips, tableWrap, pagination);
        panel.appendChild(results);
        normalHistoryPanel.parentNode.insertBefore(panel, normalHistoryPanel);

        const state = {
            controller: null,
            explanation: '',
            page: 1,
            query: '',
            revision: 0,
            spec: null,
            totalPages: 1,
        };

        function cancelActiveRequest() {
            if (state.controller) state.controller.abort();
            state.controller = null;
            state.revision += 1;
        }

        function beginRequest() {
            cancelActiveRequest();
            state.controller = new AbortController();
            return {
                controller: state.controller,
                revision: state.revision,
            };
        }

        function isCurrent(request) {
            return request.revision === state.revision && request.controller === state.controller;
        }

        function setBusy(message) {
            const busy = Boolean(message);
            submitButton.disabled = busy;
            previousButton.disabled = busy || state.page <= 1;
            nextButton.disabled = busy || state.page >= state.totalPages;
            submitButton.classList.toggle('is-loading', busy);
            submitButton.textContent = busy ? 'Aranıyor…' : 'AI ile Ara';
            liveStatus.textContent = message || '';
            panel.setAttribute('aria-busy', busy ? 'true' : 'false');
        }

        function showError(message) {
            errorBox.textContent = message;
            errorBox.hidden = false;
            liveStatus.textContent = '';
        }

        function clearError() {
            errorBox.textContent = '';
            errorBox.hidden = true;
        }

        function renderChips() {
            chips.replaceChildren();
            buildFilterChipEntries(state.spec).forEach(({ label, value }) => {
                const chip = element(documentRef, 'span', 'ai-history-chip');
                chip.appendChild(element(documentRef, 'span', 'ai-history-chip-label', label));
                chip.appendChild(element(documentRef, 'span', 'ai-history-chip-value', value));
                chips.appendChild(chip);
            });
        }

        function renderMessageRow(message, className) {
            const row = documentRef.createElement('tr');
            const cell = element(documentRef, 'td', className, message);
            cell.colSpan = 6;
            row.appendChild(cell);
            tbody.replaceChildren(row);
        }

        function renderLoadingRows() {
            tbody.replaceChildren();
            for (let index = 0; index < 3; index += 1) {
                const row = element(documentRef, 'tr', 'ai-history-skeleton-row');
                for (let column = 0; column < 6; column += 1) {
                    const cell = documentRef.createElement('td');
                    cell.appendChild(element(documentRef, 'span', 'ai-history-skeleton'));
                    row.appendChild(cell);
                }
                tbody.appendChild(row);
            }
        }

        function itemCell(text, className) {
            return element(documentRef, 'td', className || '', text);
        }

        function renderItems(data) {
            const items = Array.isArray(data.items) ? data.items : [];
            state.page = Number(data.page) || 1;
            state.totalPages = Math.max(1, Number(data.total_pages) || 1);

            pageInfo.textContent = `Sayfa ${state.page} / ${state.totalPages}`;
            previousButton.disabled = state.page <= 1;
            nextButton.disabled = state.page >= state.totalPages;

            const total = Number(data.total);
            resultCount.textContent = Number.isFinite(total)
                ? `${new Intl.NumberFormat('tr-TR').format(total)} sonuç`
                : `${items.length} sonuç`;

            if (!items.length) {
                renderMessageRow('Bu filtrelerle eşleşen fatura bulunamadı.', 'ai-history-empty');
                return;
            }

            tbody.replaceChildren();
            items.forEach((item, index) => {
                const row = element(documentRef, 'tr', 'ai-history-result-row');
                row.style.setProperty('--ai-row-index', String(Math.min(index, 8)));
                row.appendChild(itemCell(formatDate(item.date || item.invoice_date || item.created_at)));
                row.appendChild(itemCell(item.invoice_no || '-', 'ai-history-invoice-no'));

                const customerCell = itemCell(item.customer_name || item.customer || '-');
                customerCell.title = item.customer_name || item.customer || '-';
                row.appendChild(customerCell);
                row.appendChild(itemCell(
                    item.customer_tax_id || item.customer_vkn || item.tax_id || item.vkn || '-',
                ));
                row.appendChild(itemCell(
                    formatAmount(item.amount_try ?? item.total_amount ?? item.amount),
                    'ai-history-amount',
                ));

                const statusCell = documentRef.createElement('td');
                const status = item.uyumsoft_status || item.status || '-';
                statusCell.appendChild(element(documentRef, 'span', 'ai-history-status', status));
                row.appendChild(statusCell);
                tbody.appendChild(row);
            });
        }

        async function loadResultPage(page, request) {
            results.hidden = false;
            renderLoadingRows();
            setBusy('Arşiv, oluşturulan güvenli filtrelerle taranıyor…');

            const data = await requestJson('/api/history/ai/results', {
                spec: state.spec,
                page,
                limit: PAGE_SIZE,
            }, request.controller.signal);

            if (!isCurrent(request)) return;
            if (!Array.isArray(data.items)) {
                throw new Error('Sunucu geçerli bir sonuç listesi döndürmedi.');
            }
            renderItems(data);
            setBusy('');
            liveStatus.textContent = `AI araması tamamlandı. ${resultCount.textContent}.`;
        }

        async function submitQuery() {
            const query = input.value.trim();
            if (query.length < 3) {
                showError('Lütfen en az 3 karakterlik bir arama cümlesi yazın.');
                input.focus();
                return;
            }

            const request = beginRequest();
            state.query = query;
            state.spec = null;
            state.explanation = '';
            state.page = 1;
            state.totalPages = 1;
            clearError();
            clearButton.hidden = false;
            results.hidden = false;
            explanation.textContent = '';
            resultCount.textContent = '';
            chips.replaceChildren();
            renderLoadingRows();
            setBusy('Sorunuz güvenli arşiv filtrelerine çevriliyor…');

            try {
                const interpreted = await requestJson('/api/history/ai/interpret', { query }, request.controller.signal);
                if (!isCurrent(request)) return;
                if (!interpreted.spec || typeof interpreted.spec !== 'object' || Array.isArray(interpreted.spec)) {
                    throw new Error('AI geçerli bir filtre oluşturamadı.');
                }

                state.spec = interpreted.spec;
                state.explanation = interpreted.explanation || 'İsteğiniz güvenli arşiv filtrelerine dönüştürüldü.';
                explanation.textContent = state.explanation;
                renderChips();
                await loadResultPage(1, request);
            } catch (error) {
                if (error && error.name === 'AbortError') return;
                if (!isCurrent(request)) return;
                setBusy('');
                showError(error && error.message ? error.message : 'Yapay zekâ araması tamamlanamadı.');
                renderMessageRow('Sonuçlar yüklenemedi.', 'ai-history-empty');
            }
        }

        async function goToPage(page) {
            if (!state.spec || page < 1 || page > state.totalPages || page === state.page) return;
            const request = beginRequest();
            clearError();
            try {
                await loadResultPage(page, request);
            } catch (error) {
                if (error && error.name === 'AbortError') return;
                if (!isCurrent(request)) return;
                setBusy('');
                showError(error && error.message ? error.message : 'Sonuç sayfası yüklenemedi.');
                renderMessageRow('Sonuçlar yüklenemedi.', 'ai-history-empty');
            }
        }

        function clearSearch() {
            cancelActiveRequest();
            state.query = '';
            state.spec = null;
            state.explanation = '';
            state.page = 1;
            state.totalPages = 1;
            input.value = '';
            clearButton.hidden = true;
            results.hidden = true;
            explanation.textContent = '';
            resultCount.textContent = '';
            chips.replaceChildren();
            tbody.replaceChildren();
            pageInfo.textContent = 'Sayfa 1 / 1';
            previousButton.disabled = true;
            nextButton.disabled = true;
            clearError();
            setBusy('');
            input.focus();
        }

        form.addEventListener('submit', event => {
            event.preventDefault();
            submitQuery();
        });
        clearButton.addEventListener('click', clearSearch);
        previousButton.addEventListener('click', () => goToPage(state.page - 1));
        nextButton.addEventListener('click', () => goToPage(state.page + 1));

        return {
            clear: clearSearch,
            getState: () => ({
                page: state.page,
                query: state.query,
                revision: state.revision,
                spec: state.spec,
                totalPages: state.totalPages,
            }),
        };
    }

    return {
        buildFilterChipEntries,
        formatAmount,
        formatDate,
        mount,
    };
}));
