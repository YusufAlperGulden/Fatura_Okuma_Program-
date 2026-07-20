document.addEventListener('DOMContentLoaded', () => {
    const {
        calculateTaxBreakdown,
        formatCentsTr,
        parseLocaleNumber,
    } = window.InvoiceUiHelpers;

    // Theme toggle logic
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const isLight = document.documentElement.getAttribute('data-theme') === 'light';
            if (isLight) {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('theme', 'dark');
            } else {
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('theme', 'light');
            }
        });
    }

    // Request notification permission for Uyumsoft alerts
    if (window.Notification && Notification.permission !== 'granted' && Notification.permission !== 'denied') {
        Notification.requestPermission();
    }

    let currentInvoiceData = null;
    let currentUploadId = null;
    let currentInvoiceIsValid = false;
    let currentValidationErrors = [];
    let currentValidationState = 'idle';
    let draftSendInProgress = false;

    // Add event listener for draft send
    document.getElementById('send-draft-btn').addEventListener('click', () => {
        if (currentValidationState === 'pending') {
            showDraftValidationPopup(
                ['Yaptığınız değişikliklerin doğrulanması henüz tamamlanmadı. Lütfen kısa bir süre sonra tekrar deneyin.'],
                'Fatura henüz gönderilemez.'
            );
            return;
        }
        if (!currentInvoiceIsValid) {
            showDraftValidationPopup();
            return;
        }
        if (confirm("Bu faturayı Uyumsoft'a taslak olarak göndermek istediğinize emin misiniz?")) {
            runUyumsoftAction();
        }
    });



    document.getElementById('res-invoice-no').addEventListener('input', (e) => {
        handleEdit(-1, 'invoice_no', e.target.value);
    });
    
    document.getElementById('res-date').addEventListener('input', (e) => {
        handleEdit(-1, 'date', e.target.value);
    });
    
    document.getElementById('res-time').addEventListener('input', (e) => {
        handleEdit(-1, 'time', e.target.value);
    });

    document.getElementById('res-vkn').addEventListener('input', (e) => {
        handleEdit(-1, 'customer_tax_id', e.target.value);
    });

    document.getElementById('res-customer-name').addEventListener('input', (e) => {
        handleEdit(-1, 'customer_name', e.target.value);
    });

    document.querySelectorAll('.edit-input-top').forEach(input => {
        input.addEventListener('blur', () => {
            syncCanonicalInputs(currentInvoiceData);
        });
    });


    const dropZone = document.getElementById('drop-zone');


    const fileInput = document.getElementById('file-input');
    const loading = document.getElementById('loading');
    const resultsSection = document.getElementById('results-section');
    let UYUMSOFT_PORTAL_URL = 'https://www.uyumsoft.com/kullanici-girisi';

    async function loadRuntimeConfig() {
        try {
            const response = await fetch('/runtime-config');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const config = await response.json();
            if (config.uyumsoft_portal_url) {
                UYUMSOFT_PORTAL_URL = config.uyumsoft_portal_url;
            }
            const environment = config.uyumsoft_environment === 'prod' ? 'prod' : 'test';
            document.documentElement.dataset.uyumsoftEnvironment = environment;
            const select = document.getElementById('environment-select');
            if (select) {
                select.value = environment;
            }
        } catch (error) {
            console.warn('Uyumsoft ortam ayarı okunamadı.', error);
        }
    }

    const environmentSelect = document.getElementById('environment-select');
    if (environmentSelect) {
        environmentSelect.addEventListener('change', (e) => {
            document.documentElement.dataset.uyumsoftEnvironment = e.target.value;
            // Clear cached prod credentials if switching back to test just in case, though optional
            if (e.target.value === 'test') {
                sessionStorage.removeItem('uyumsoft_prod_username');
                sessionStorage.removeItem('uyumsoft_prod_password');
            }
        });
    }

    loadRuntimeConfig();

    function openUyumsoftPortal() {
        window.open(UYUMSOFT_PORTAL_URL, '_blank', 'noopener');
    }
    
    // Upload handlers
    dropZone.addEventListener('click', () => fileInput.click());
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 1) {
            handleBatchFiles(Array.from(e.dataTransfer.files));
        } else if (e.dataTransfer.files.length === 1) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files && files.length > 1) {
            handleBatchFiles(Array.from(files));
        } else if (files && files.length === 1) {
            handleFile(files[0]);
        }
        e.target.value = '';
    });
    
    let pdfObjectUrl = null;

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function normalizeSerialNumbers(value) {
        const serials = Array.isArray(value)
            ? value
            : (typeof value === 'string' ? value.split(/[~,;\r\n]+/) : []);

        return serials
            .map(serial => String(serial).trim())
            .filter(Boolean);
    }

    function csvCell(value) {
        let text = value == null ? '' : String(value);

        // Prevent spreadsheet applications from evaluating invoice text as a formula.
        if (/^[\u0000-\u0020\u007F\u00A0]*[=+\-@]/.test(text)) {
            text = `'${text}`;
        }

        return `"${text.replace(/"/g, '""')}"`;
    }

    function parseMoney(value) {
        const parsed = parseLocaleNumber(value);
        return parsed === null ? 0 : parsed;
    }

    function parseEditableNumber(value) {
        return parseLocaleNumber(value);
    }

    function hasNumericValue(value) {
        return parseEditableNumber(value) !== null;
    }

    function roundMoney(value) {
        return Math.round((value + Number.EPSILON) * 100) / 100;
    }

    function formatEditedMoney(value) {
        return roundMoney(value).toFixed(2).replace('.', ',');
    }

    function formatEditedDecimal(value) {
        if (!Number.isFinite(value)) return '';
        return value.toLocaleString('tr-TR', {
            useGrouping: false,
            maximumFractionDigits: 8,
        });
    }

    function syncItemInput(itemIndex, fieldName, value) {
        const input = document.querySelector(
            `#items-table input[data-item-index="${itemIndex}"][data-field-name="${fieldName}"]`
        );
        if (input && document.activeElement !== input) {
            input.value = value;
        }
    }

    function updateInputIfNotFocused(id, value) {
        const input = document.getElementById(id);
        if (input && document.activeElement !== input) {
            input.value = value === null || value === undefined ? '' : value;
        }
    }

    function syncCanonicalInputs(data) {
        if (!data || typeof data !== 'object') return;

        updateInputIfNotFocused('res-invoice-no', data.invoice_no);
        updateInputIfNotFocused('res-date', data.date);
        updateInputIfNotFocused('res-time', data.time);
        updateInputIfNotFocused('res-vkn', data.customer_tax_id);
        updateInputIfNotFocused(
            'res-customer-name',
            data.customer_name || data.customer_title || data.customer || '',
        );

        if (!Array.isArray(data.items)) return;
        const editableFields = [
            'code',
            'description',
            'quantity',
            'unit_price',
            'tax_rate',
            'total_price',
        ];
        data.items.forEach((item, itemIndex) => {
            editableFields.forEach(fieldName => {
                syncItemInput(itemIndex, fieldName, item && item[fieldName]);
            });
        });
    }

    function recalculateEditedAmounts(itemIndex, fieldName) {
        if (
            itemIndex < 0
            || !currentInvoiceData
            || !Array.isArray(currentInvoiceData.items)
            || !currentInvoiceData.items[itemIndex]
            || !['quantity', 'unit_price', 'tax_rate', 'total_price'].includes(fieldName)
        ) {
            return;
        }

        const item = currentInvoiceData.items[itemIndex];
        const quantity = parseEditableNumber(item.quantity);
        const unitPrice = parseEditableNumber(item.unit_price);
        const lineTotal = parseEditableNumber(item.total_price);

        if (
            ['quantity', 'unit_price'].includes(fieldName)
            && quantity !== null
            && unitPrice !== null
        ) {
            item.total_price = formatEditedMoney(quantity * unitPrice);
            syncItemInput(itemIndex, 'total_price', item.total_price);
        } else if (
            fieldName === 'total_price'
            && quantity !== null
            && quantity > 0
            && lineTotal !== null
        ) {
            item.unit_price = formatEditedDecimal(lineTotal / quantity);
            syncItemInput(itemIndex, 'unit_price', item.unit_price);
        }

        const canRecalculateTotals = currentInvoiceData.items.every(line => (
            hasNumericValue(line.total_price) && hasNumericValue(line.tax_rate)
        ));
        if (!canRecalculateTotals) return;

        const subtotal = currentInvoiceData.items.reduce(
            (sum, line) => sum + parseEditableNumber(line.total_price),
            0
        );
        const discount = hasNumericValue(currentInvoiceData.discount_amount)
            ? parseMoney(currentInvoiceData.discount_amount)
            : 0;
        let taxAmount = 0;
        let allocatedDiscount = 0;

        currentInvoiceData.items.forEach((line, index) => {
            const total = parseEditableNumber(line.total_price);
            const rate = parseEditableNumber(line.tax_rate);
            let discountShare = 0;
            if (subtotal > 0 && discount > 0) {
                discountShare = index === currentInvoiceData.items.length - 1
                    ? roundMoney(discount - allocatedDiscount)
                    : roundMoney(discount * total / subtotal);
                allocatedDiscount = roundMoney(allocatedDiscount + discountShare);
            }
            taxAmount += roundMoney((total - discountShare) * rate / 100);
        });

        currentInvoiceData.subtotal = formatEditedMoney(subtotal);
        currentInvoiceData.tax_amount = formatEditedMoney(taxAmount);
        currentInvoiceData.total_amount = formatEditedMoney(subtotal - discount + taxAmount);
    }

    function setEditingDisabled(disabled) {
        document.querySelectorAll('.edit-input-top, .edit-input').forEach(input => {
            input.disabled = disabled;
        });
    }

    function appendSerialNumbersCell(row, value) {
        const cell = document.createElement('td');
        cell.className = 'serial-numbers-cell';
        const serials = normalizeSerialNumbers(value);
        cell.dataset.csvValue = serials.join('~');

        if (serials.length === 0) {
            cell.textContent = '-';
        } else {
            const list = document.createElement('div');
            list.className = 'serial-number-list';

            serials.forEach(serial => {
                const chip = document.createElement('span');
                chip.className = 'serial-number-chip';
                chip.textContent = serial;
                list.appendChild(chip);
            });

            cell.appendChild(list);
        }

        row.appendChild(cell);
    }

    function formatDetails(details) {
        if (!details) return '';
        if (Array.isArray(details)) return details.join(', ');
        if (typeof details === 'object') return JSON.stringify(details);
        return String(details);
    }

    function setDraftButtonValidationState(state) {
        const sendBtn = document.getElementById('send-draft-btn');
        sendBtn.classList.toggle('validation-blocked', state === 'invalid');
        sendBtn.classList.toggle('validation-pending', state === 'pending');
        sendBtn.title = state === 'invalid'
            ? 'Faturadaki hataları görmek için tıklayın.'
            : state === 'pending'
                ? 'Değişiklikler doğrulanıyor.'
                : '';
                
        const svgPath = sendBtn.querySelector('svg path');
        if (svgPath) {
            if (state === 'invalid') {
                svgPath.setAttribute('d', 'M6 18L18 6M6 6l12 12');
            } else {
                svgPath.setAttribute('d', 'M5 13l4 4L19 7');
            }
        }
    }

    function setCsvValidationState(state) {
        const csvButton = document.getElementById('csv-btn');
        const exportAllowed = state === 'valid';
        csvButton.disabled = !exportAllowed;
        csvButton.setAttribute('aria-disabled', exportAllowed ? 'false' : 'true');
        csvButton.title = state === 'pending'
            ? 'Değişikliklerin doğrulanması tamamlandıktan sonra CSV indirilebilir.'
            : state === 'invalid'
                ? 'Hatalı fatura CSV olarak indirilemez.'
                : '';
    }

    function appendWorkflowItem(list, state, message) {
        const item = document.createElement('li');
        item.className = state;
        let iconHtml = '';
        if (state === 'success') {
            iconHtml = `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="20" height="20" style="flex-shrink:0;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`;
        } else if (state === 'error') {
            iconHtml = `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="20" height="20" style="flex-shrink:0;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>`;
        } else if (state === 'pending') {
            iconHtml = `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="20" height="20" style="flex-shrink:0;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`;
        } else if (state === 'warning') {
            iconHtml = `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="20" height="20" style="flex-shrink:0;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>`;
        }
        item.innerHTML = `${iconHtml}<span>${message}</span>`;
        list.appendChild(item);
    }

    function updateWorkflowUI(state, data = currentInvoiceData, message = '') {
        const workflowPanel = document.getElementById('workflow-progress');
        const checklist = document.getElementById('checklist');
        if (!data) {
            workflowPanel.classList.add('hidden');
            checklist.replaceChildren();
            return;
        }

        workflowPanel.classList.remove('hidden');
        checklist.replaceChildren();
        appendWorkflowItem(checklist, 'success', 'Fatura okundu');

        if (state === 'pending') {
            appendWorkflowItem(checklist, 'pending', 'Düzenlemeler doğrulanıyor...');
            return;
        }
        if (state === 'valid') {
            appendWorkflowItem(checklist, 'success', 'Toplamlar doğrulandı');
            if (data._uyumsoft_customer_lookup === 'matched') {
                appendWorkflowItem(
                    checklist,
                    'success',
                    'Müşteri adı Uyumsoft mükellef listesinden eşleştirildi',
                );
            }
            appendWorkflowItem(
                checklist,
                'pending',
                'Fatura geçerli. Uyumsoft\'a göndermek için "Taslak Olarak Gönder" butonunu kullanın.',
            );
            return;
        }

        appendWorkflowItem(
            checklist,
            'error',
            message || 'Fatura okundu ancak doğrulama hataları nedeniyle aktarım durduruldu.',
        );
    }

    function setValidationFailure(message) {
        currentInvoiceIsValid = false;
        currentValidationErrors = [message];
        currentValidationState = 'invalid';
        const badge = document.getElementById('validation-badge');
        badge.textContent = 'DOĞRULAMA HATASI';
        badge.className = 'badge error';
        document.getElementById('portal-btn').classList.add('hidden');
        document.getElementById('send-draft-btn').disabled = false;
        setDraftButtonValidationState('invalid');
        setCsvValidationState('invalid');
        renderValidationErrors(currentValidationErrors);
        updateWorkflowUI('invalid', currentInvoiceData, message);
    }

    function showDraftValidationPopup(errors = currentValidationErrors, title = 'Taslak gönderilemedi.') {
        const messages = Array.isArray(errors)
            ? errors.filter(message => typeof message === 'string' && message.trim())
            : (errors ? [String(errors)] : []);
        const detail = messages.length > 0
            ? messages.map(message => `• ${message}`).join('\n')
            : 'Fatura doğrulama hataları içeriyor. Lütfen kırmızı hata alanındaki bilgileri düzeltin.';

        window.alert(`${title}\n\n${detail}`);

        const errorBox = document.getElementById('error-box');
        if (errorBox && !errorBox.classList.contains('hidden')) {
            errorBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    async function readJsonResponse(response) {
        const text = await response.text();
        try {
            return JSON.parse(text);
        } catch (error) {
            throw new Error(`Sunucu JSON yerine hata sayfası döndürdü (HTTP ${response.status}). Sayfayı yenileyip tekrar deneyin.`);
        }
    }

    function formatApiError(result) {
        if (!result) return "";
        if (result.errors && Array.isArray(result.errors) && result.errors.length > 0) {
            return result.errors.join(", ");
        }
        if (result.message) {
            let msg = result.message;
            if (result.details && Array.isArray(result.details) && result.details.length > 0) {
                msg += " - " + result.details.join(", ");
            }
            return msg;
        }
        if (result.detail) {
            return typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail);
        }
        return "Sunucu bilinmeyen bir hata döndürdü.";
    }

    let currentAbortController = null;

    async function handleFile(file) {
        if (window.location.protocol === 'file:') {
            showError("Bu sayfa dosya olarak açılmış. Lütfen uygulamayı http://127.0.0.1:7860/ui/ adresinden açın.");
            return;
        }

        // Reset UI
        if (pdfObjectUrl) {
            URL.revokeObjectURL(pdfObjectUrl);
            pdfObjectUrl = null;
        }
        document.getElementById('pdf-iframe').src = '';
        
        if (file.type === 'application/pdf' || ['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
            pdfObjectUrl = URL.createObjectURL(file);
            document.getElementById('pdf-iframe').src = pdfObjectUrl;
            document.getElementById('pdf-viewer-section').classList.remove('hidden');
            document.getElementById('split-container').classList.add('split-active');
            document.querySelector('.app-container').classList.add('wide-mode');
            document.getElementById('toggle-pdf-btn').style.display = 'flex';
        } else {
            document.getElementById('pdf-viewer-section').classList.add('hidden');
            document.getElementById('split-container').classList.remove('split-active');
            document.querySelector('.app-container').classList.remove('wide-mode');
            document.getElementById('toggle-pdf-btn').style.display = 'none';
        }

        dropZone.classList.add('hidden');
                loading.classList.remove('hidden');
        document.getElementById('send-draft-btn').classList.add('hidden');
        document.getElementById('send-draft-btn').disabled = false;
        currentUploadId = crypto.randomUUID();
        const capturedUploadId = currentUploadId;
        currentInvoiceData = null;
        validationRevision += 1;
        clearTimeout(validationTimeout);
        if (validationAbortController) {
            validationAbortController.abort();
            validationAbortController = null;
        }
        currentInvoiceIsValid = false;
        currentValidationErrors = [];
        currentValidationState = 'idle';
        draftSendInProgress = false;
        setEditingDisabled(false);
        setDraftButtonValidationState('idle');
        setCsvValidationState('idle');
        document.getElementById('csv-btn').classList.add('hidden');
        document.getElementById('workflow-progress').classList.add('hidden');
        document.getElementById('validation-badge').className = 'badge';
        document.getElementById('validation-badge').textContent = 'Bekliyor';
        document.getElementById('discount-card').classList.add('hidden');
        resultsSection.classList.add('hidden');
        document.getElementById('split-container').classList.add('hidden');
        document.getElementById('error-box').classList.add('hidden');
        document.getElementById('portal-btn').classList.add('hidden');
        document.getElementById('api-status-box').classList.add('hidden');
        document.getElementById('loading-text').textContent = 'Fatura işleniyor...';
        

        // Clear old results data visually
        document.getElementById('res-invoice-no').value = '';
                document.getElementById('res-date').value = '';
        document.getElementById('res-time').value = '';
        document.getElementById('res-vkn').value = '';
        document.getElementById('res-customer-name').value = '';
        document.getElementById('res-method').textContent = '-';

        document.getElementById('res-subtotal').textContent = '-';
        if (document.getElementById('res-tax-breakdown')) {
            document.getElementById('res-tax-breakdown').innerHTML = '-';
        }
        document.getElementById('res-total').textContent = '-';
        if (document.getElementById('notes-card')) {
            document.getElementById('notes-card').classList.add('hidden');
            document.getElementById('res-notes').textContent = '-';
        }
        document.querySelector('#items-table tbody').innerHTML = '';
        
        const formData = new FormData();
        formData.append('file', file);
        
        // Set up AbortController
        if (currentAbortController) {
            currentAbortController.abort();
        }
        currentAbortController = new AbortController();
        const signal = currentAbortController.signal;
        
        document.getElementById('cancel-btn').onclick = () => {
            if (currentAbortController) {
                currentAbortController.abort();
            }
        };
        
        try {
            // Because we are serving from /ui, the API endpoint is at /upload
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData,
                signal: signal
            });
            
                        const result = await readJsonResponse(response);
            if (currentUploadId !== capturedUploadId) return;
            loading.classList.add('hidden');
            dropZone.classList.remove('hidden');
            
            if (response.ok) {
                currentInvoiceData = result.data;
                renderInvoice(result);
                updateValidationUI(result);
                document.getElementById('send-draft-btn').classList.remove('hidden');
            } else {
                showError("Sunucu Hatası: " + formatApiError(result));
            }
            
        } catch (error) {
            if (currentUploadId !== capturedUploadId) return;
            loading.classList.add('hidden');
            dropZone.classList.remove('hidden');
            
            if (error.name === 'AbortError' || (currentAbortController && currentAbortController.signal.aborted)) {
                showError("İşlem sizin tarafınızdan iptal edildi.");
            } else {
                showError("Bağlantı hatası: " + error.message);
            }
        } finally {
            if (currentUploadId === capturedUploadId) {
                currentAbortController = null;
            }
        }
    }


    function appendInputCell(row, value, fieldName, itemIndex, className = '') {
        const cell = document.createElement('td');
        if (className) cell.className = className;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = value == null ? '' : value;
        input.className = 'edit-input';
        input.dataset.fieldName = fieldName;
        input.dataset.itemIndex = String(itemIndex);
        input.style.width = '100%';
        input.style.boxSizing = 'border-box';
        input.style.padding = '4px';
        input.style.border = '1px solid var(--border-color)';
        input.style.borderRadius = '4px';
        input.style.background = 'var(--card-bg)';
        input.style.color = 'var(--text-primary)';
        
        input.addEventListener('input', (e) => {
            handleEdit(itemIndex, fieldName, e.target.value);
        });
        input.addEventListener('blur', () => {
            const canonicalItem = currentInvoiceData
                && Array.isArray(currentInvoiceData.items)
                && currentInvoiceData.items[itemIndex];
            if (canonicalItem) {
                syncItemInput(itemIndex, fieldName, canonicalItem[fieldName]);
            }
        });

        cell.appendChild(input);
        row.appendChild(cell);
        return cell;
    }

    let validationTimeout = null;
    let validationAbortController = null;
    let validationRevision = 0;

    function renderValidationErrors(errors) {
        const errorBox = document.getElementById('error-box');
        const taxInput = document.getElementById('res-vkn');
        const taxCard = document.getElementById('customer-tax-card');
        const messages = Array.isArray(errors)
            ? errors.filter(message => typeof message === 'string' && message.trim())
            : [];
        const hasTaxError = messages.some(message => /VKN|TCKN/i.test(message));

        taxInput.setAttribute('aria-invalid', hasTaxError ? 'true' : 'false');
        taxCard.classList.toggle('field-invalid', hasTaxError);
        errorBox.replaceChildren();

        if (messages.length === 0) {
            errorBox.classList.add('hidden');
            return;
        }

        const heading = document.createElement('strong');
        heading.textContent = 'Lütfen şu eksik veya hatalı alanları düzeltin:';
        const list = document.createElement('ul');
        list.style.margin = '0.5rem 0 0 1.5rem';
        list.style.listStyleType = 'disc';

        messages.forEach(message => {
            const item = document.createElement('li');
            item.textContent = message;
            item.style.marginBottom = '0.25rem';
            list.appendChild(item);
        });

        errorBox.append(heading, list);
        errorBox.classList.remove('hidden');
    }

    function handleEdit(itemIndex, fieldName, newValue) {
        if (!currentInvoiceData || draftSendInProgress) return;
        
        if (itemIndex === -1) {
            currentInvoiceData[fieldName] = newValue;
            if (fieldName === 'customer_name') {
                // customer_name is the editable/canonical field. Keep the
                // legacy alias in sync so no downstream serializer can revive
                // the pre-edit value.
                currentInvoiceData.customer_title = newValue;
            }
        } else if (
            Array.isArray(currentInvoiceData.items)
            && currentInvoiceData.items[itemIndex]
        ) {
            currentInvoiceData.items[itemIndex][fieldName] = newValue;
            recalculateEditedAmounts(itemIndex, fieldName);
        } else {
            return;
        }

        validationRevision += 1;
        if (validationAbortController) {
            validationAbortController.abort();
            validationAbortController = null;
        }
        currentInvoiceIsValid = false;
        currentValidationErrors = [];
        currentValidationState = 'pending';
        document.getElementById('send-draft-btn').disabled = false;
        setDraftButtonValidationState('pending');
        setCsvValidationState('pending');
        const badge = document.getElementById('validation-badge');
        badge.textContent = 'Doğrulanıyor...';
        badge.className = 'badge';
        updateWorkflowUI('pending');

        clearTimeout(validationTimeout);
        validationTimeout = setTimeout(() => {
            validateCurrentData();
        }, 500);
    }

    async function validateCurrentData() {
        if (!currentInvoiceData) return;

        const capturedValidationRevision = validationRevision;
        if (validationAbortController) {
            validationAbortController.abort();
        }
        const abortController = new AbortController();
        validationAbortController = abortController;

        try {
            const response = await fetch('/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentInvoiceData),
                signal: abortController.signal
            });
            const result = await readJsonResponse(response);
            if (capturedValidationRevision !== validationRevision) return;
            if (response.ok) {
                if (result.data && typeof result.data === 'object') {
                    currentInvoiceData = result.data;
                }
                updateValidationUI(result);
            } else {
                setValidationFailure(formatApiError(result) || 'Fatura doğrulaması tamamlanamadı.');
            }
        } catch (err) {
            if (err.name === 'AbortError' || capturedValidationRevision !== validationRevision) return;
            console.error("Validasyon hatası:", err);
            setValidationFailure('Fatura doğrulaması sırasında bağlantı hatası oluştu.');
        } finally {
            if (validationAbortController === abortController) {
                validationAbortController = null;
            }
        }
    }

    function renderInvoice(result) {
        const data = result.data || {};
        const tbody = document.querySelector('#items-table tbody');
        tbody.innerHTML = '';
        
        const items = data.items || [];
        if (items.length === 0) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 7;
            td.className = 'empty-items-cell';
            td.textContent = 'Herhangi bir kalem bulunamadı.';
            tr.appendChild(td);
            tbody.appendChild(tr);
        } else {
            items.forEach((item, index) => {
                const tr = document.createElement('tr');
                appendInputCell(tr, item.code, 'code', index);
                appendInputCell(tr, item.description, 'description', index, 'item-description-cell');
                appendSerialNumbersCell(tr, item.serial_numbers); // Serial numbers are currently complex to input inline, keep as cell
                appendInputCell(tr, item.quantity, 'quantity', index);
                appendInputCell(tr, item.unit_price, 'unit_price', index);
                appendInputCell(tr, item.tax_rate, 'tax_rate', index);
                appendInputCell(tr, item.total_price, 'total_price', index);
                tbody.appendChild(tr);
            });
        }
    }

    function updateValidationUI(result) {

        resultsSection.classList.remove('hidden');
        document.getElementById('split-container').classList.remove('hidden');

        // Badge
        const badge = document.getElementById('validation-badge');
        currentInvoiceIsValid = Boolean(result.is_valid);
        currentValidationErrors = Array.isArray(result.errors) ? result.errors : [];
        currentValidationState = currentInvoiceIsValid ? 'valid' : 'invalid';
        const sendDraftBtn = document.getElementById('send-draft-btn');
        sendDraftBtn.disabled = false;
        setDraftButtonValidationState(currentValidationState);
        setCsvValidationState(currentValidationState);
        if (result.is_valid) {
            badge.textContent = 'GEÇERLİ';
            badge.className = 'badge valid';
            document.getElementById('portal-btn').classList.remove('hidden');
        } else {
            badge.textContent = 'HATALI';
            badge.className = 'badge error';
            document.getElementById('portal-btn').classList.add('hidden');
        }
        renderValidationErrors(result.is_valid ? [] : result.errors);
        document.getElementById('csv-btn').classList.remove('hidden');
        updateWorkflowUI(currentValidationState, result.data || currentInvoiceData);

        // Ensure data exists before accessing properties
        const data = result.data || {};

        const getSymbol = (currency) => {
            if (currency === 'USD') return '$';
            if (currency === 'EUR') return '€';
            if (currency === 'GBP') return '£';
            return '₺';
        };
        const sym = getSymbol(data.currency);

        // Canonical validation values update every non-focused input. If an
        // input is still active, its blur handler performs this sync later.
        syncCanonicalInputs(data);
        document.getElementById('res-method').textContent = data._extraction_method || '-';
        document.getElementById('res-subtotal').textContent = data.subtotal !== null && data.subtotal !== undefined && data.subtotal !== ''
            ? `${sym}${data.subtotal}`
            : '-';

        const discountCard = document.getElementById('discount-card');
        if (parseMoney(data.discount_amount) > 0) {
            document.getElementById('res-discount').textContent = `-${sym}${data.discount_amount}`;
            discountCard.classList.remove('hidden');
        } else {
            discountCard.classList.add('hidden');
        }

        // Calculate tax breakdown
        const breakdownDiv = document.getElementById('res-tax-breakdown');
        if (breakdownDiv) {
            breakdownDiv.replaceChildren();
            if (Array.isArray(data.items) && data.items.length > 0 && data.tax_amount !== null && data.tax_amount !== undefined && data.tax_amount !== '') {
                const breakdown = calculateTaxBreakdown({
                    items: data.items,
                    discountAmount: data.discount_amount,
                    canonicalTaxAmount: data.tax_amount,
                });
                if (breakdown.groups.length > 0) {
                    breakdown.groups.forEach(group => {
                        const row = document.createElement('div');
                        row.className = 'tax-breakdown-row';
                        row.textContent = `%${group.rate} = ${formatCentsTr(group.taxCents)}`;
                        breakdownDiv.appendChild(row);
                    });
                    const totalRow = document.createElement('div');
                    totalRow.className = 'tax-breakdown-total';
                    totalRow.textContent = `Top = ${formatCentsTr(breakdown.totalTaxCents)}`;
                    breakdownDiv.appendChild(totalRow);
                } else {
                    breakdownDiv.textContent = `${sym}${data.tax_amount}`;
                }
            } else {
                breakdownDiv.textContent = data.tax_amount !== null && data.tax_amount !== undefined && data.tax_amount !== ''
                    ? `${sym}${data.tax_amount}`
                    : '-';
            }
        }

        document.getElementById('res-total').textContent = data.total_amount !== null && data.total_amount !== undefined && data.total_amount !== ''
            ? `${sym}${data.total_amount}`
            : '-';
        
        const notesCard = document.getElementById('notes-card');
        if (notesCard && data.notes && data.notes.trim() !== '') {
            document.getElementById('res-notes').textContent = data.notes.trim();
            notesCard.classList.remove('hidden');
        } else if (notesCard) {
            notesCard.classList.add('hidden');
        }
        

    }
    
    // Send only the immutable, user-reviewed snapshot after validation.
    async function runUyumsoftAction() {
        if (!currentInvoiceData || draftSendInProgress) return;
        if (currentValidationState !== 'valid' || !currentInvoiceIsValid) {
            showDraftValidationPopup();
            return;
        }

        const env = document.documentElement.dataset.uyumsoftEnvironment || 'test';
        let prodUsername = null;
        let prodPassword = null;
        
        if (env === 'prod') {
            const storedUser = sessionStorage.getItem('uyumsoft_prod_username');
            const storedPass = sessionStorage.getItem('uyumsoft_prod_password');
            if (!storedUser || !storedPass) {
                document.getElementById('prod-credentials-modal').classList.remove('hidden');
                return; // Stop here, modal submit will call this again
            }
            prodUsername = storedUser;
            prodPassword = storedPass;
        }
        const capturedUploadId = currentUploadId;
        const capturedValidationRevision = validationRevision;
        const invoiceSnapshot = JSON.parse(JSON.stringify(currentInvoiceData));
        const sendBtn = document.getElementById('send-draft-btn');
        draftSendInProgress = true;
        sendBtn.disabled = true;
        setEditingDisabled(true);
        
        const statusBox = document.getElementById('api-status-box');
        const action = 'draft';
        const actionLabel = 'Taslak Oluştur';
        statusBox.classList.remove('hidden');
        statusBox.style.position = 'relative';
        statusBox.style.overflow = 'hidden';
        statusBox.style.backgroundColor = '#3b82f6';
        statusBox.style.color = '#fff';
        statusBox.innerHTML = `
            <div class="fake-progress-bar"></div>
            <div style="position: relative; z-index: 1; display: flex; align-items: center;">
                <div class="spinner" style="width:20px;height:20px;border-width:2px;display:inline-block;margin-right:10px;"></div> 
                ${actionLabel} çalışıyor...
            </div>
        `;
        
        try {
            const response = await fetch('/send-uyumsoft', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    invoice_data: invoiceSnapshot,
                    action: action,
                    environment: env,
                    prod_username: prodUsername,
                    prod_password: prodPassword
                })
            });
            
            const result = await readJsonResponse(response);
            
                        if (result.success) {
                if (
                    currentUploadId !== capturedUploadId
                    || validationRevision !== capturedValidationRevision
                ) return;
                document.getElementById('send-draft-btn').classList.add('hidden');
                statusBox.style.backgroundColor = '#059669';
                statusBox.innerHTML = `✓  ${escapeHtml(result.message)} (HTTP ${escapeHtml(result.response_code)})`;
                
                if (window.Notification && Notification.permission === 'granted') {
                    const notification = new Notification("Uyumsoft Entegrasyonu", {
                        body: "Fatura başarıyla Uyumsoft'a aktarıldı. Portalı açmak için tıklayın."
                    });
                    notification.onclick = () => {
                        window.focus();
                        openUyumsoftPortal();
                        notification.close();
                    };
                }
                
                // In-app Toast Notification as a guaranteed fallback
                if (window.Toastify) {
                    Toastify({
                        text: "Fatura başarıyla Uyumsoft'a aktarıldı! Portalı açmak için tıklayın.",
                        duration: 5000,
                        gravity: "top", 
                        position: "right", 
                        onClick: openUyumsoftPortal,
                        style: {
                            background: "linear-gradient(to right, #059669, #10b981)",
                            borderRadius: "8px",
                            fontWeight: "bold",
                            cursor: "pointer",
                            boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)"
                        }
                    }).showToast();
                }
            } else {
                const details = formatDetails(result.details);
                if (currentUploadId !== capturedUploadId) return;
                draftSendInProgress = false;
                setEditingDisabled(false);
                statusBox.style.backgroundColor = '#dc2626';
                statusBox.innerHTML = `❌ Hata: ${escapeHtml(result.message)}${details ? ` <br> <small>${escapeHtml(details)}</small>` : ''}`;
                sendBtn.disabled = false;
                if (Number(result.response_code) === 400) {
                    currentInvoiceIsValid = false;
                    currentValidationErrors = Array.isArray(result.details) ? result.details : [];
                    currentValidationState = 'invalid';
                    setDraftButtonValidationState('invalid');
                    showDraftValidationPopup(
                        result.details,
                        'Fatura doğrulama hataları nedeniyle taslak gönderilemedi.'
                    );
                }
            }
        } catch (error) {
            if (currentUploadId !== capturedUploadId) return;
            draftSendInProgress = false;
            setEditingDisabled(false);
            statusBox.style.backgroundColor = '#dc2626';
            statusBox.textContent = `❌ Bağlantı Hatası: ${error && error.message ? error.message : 'Bilinmeyen hata'}`;
            sendBtn.disabled = false;
        }
    }

    document.getElementById('portal-btn').addEventListener('click', openUyumsoftPortal);

    document.getElementById('csv-btn').addEventListener('click', () => {
        if (currentValidationState !== 'valid' || !currentInvoiceIsValid) {
            const message = currentValidationState === 'pending'
                ? 'Değişikliklerin doğrulanması henüz tamamlanmadı.'
                : 'Hatalı bir fatura CSV olarak indirilemez.';
            window.alert(message);
            return;
        }
        if (!currentInvoiceData || !Array.isArray(currentInvoiceData.items)) return;
        
        const headers = ['Urun Kodu', 'Urun Aciklamasi', 'Seri Numaralari', 'Miktar', 'Birim Fiyat', 'KDV Orani', 'Satir Toplami'];
        const rows = [headers.map(csvCell).join(',')];

        currentInvoiceData.items.forEach(item => {
            rows.push([
                item.code,
                item.description,
                normalizeSerialNumbers(item.serial_numbers).join('~'),
                item.quantity,
                item.unit_price,
                item.tax_rate,
                item.total_price,
            ].map(csvCell).join(','));
        });
        
        rows.push('');
        const summaryRow = (label, value) => [label, ...Array(headers.length - 2).fill(''), value];
        rows.push(summaryRow('Ara Toplam', currentInvoiceData.subtotal).map(csvCell).join(','));
        rows.push(summaryRow('KDV Toplamı', currentInvoiceData.tax_amount).map(csvCell).join(','));
        rows.push(summaryRow('Genel Toplam', currentInvoiceData.total_amount).map(csvCell).join(','));
        
        const csvContent = "\uFEFF" + rows.join('\r\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        const fileName = currentInvoiceData.invoice_no ? `fatura_${currentInvoiceData.invoice_no}.csv` : 'fatura_sonuclari.csv';
        link.setAttribute('download', fileName);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => URL.revokeObjectURL(url), 0);
    });

    function showError(msg) {
        const errorBox = document.getElementById('error-box');
        errorBox.textContent = msg;
        errorBox.classList.remove('hidden');
        resultsSection.classList.remove('hidden');
        document.getElementById('split-container').classList.remove('hidden');
    }

    document.getElementById('toggle-pdf-btn').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const pdfSection = document.getElementById('pdf-viewer-section');
        const splitContainer = document.getElementById('split-container');
        const appContainer = document.querySelector('.app-container');
        const icon = btn.querySelector('svg');
        
        if (pdfSection.classList.contains('hidden')) {
            pdfSection.classList.remove('hidden');
            splitContainer.classList.add('split-active');
            appContainer.classList.add('wide-mode');
            btn.title = 'PDF Önizlemesini Gizle';
            if (icon) icon.style.transform = 'rotate(0deg)';
        } else {
            pdfSection.classList.add('hidden');
            splitContainer.classList.remove('split-active');
            appContainer.classList.remove('wide-mode');
            btn.title = 'PDF Önizlemesini Göster';
            if (icon) icon.style.transform = 'rotate(180deg)';
        }
        if (icon) icon.style.transition = 'transform 0.3s ease';
    });

    const submitProdCredsBtn = document.getElementById('submit-prod-credentials');
    const cancelProdCredsBtn = document.getElementById('cancel-prod-credentials');
    const prodModal = document.getElementById('prod-credentials-modal');

    if (submitProdCredsBtn) {
        submitProdCredsBtn.addEventListener('click', () => {
            const user = document.getElementById('prod-username').value.trim();
            const pass = document.getElementById('prod-password').value.trim();
            if (user && pass) {
                sessionStorage.setItem('uyumsoft_prod_username', user);
                sessionStorage.setItem('uyumsoft_prod_password', pass);
                prodModal.classList.add('hidden');
                runUyumsoftAction();
            } else {
                alert('Lütfen kullanıcı adı ve şifre girin.');
            }
        });
    }
    
    if (cancelProdCredsBtn) {
        cancelProdCredsBtn.addEventListener('click', () => {
            prodModal.classList.add('hidden');
        });
    }

    // UI event listeners initialized.

// --- BATCH PROCESSING LOGIC ---
let batchResults = [];
let batchProcessing = false;

async function handleBatchFiles(files) {
    if (window.location.protocol === 'file:') {
        showError("Bu sayfa dosya olarak açılmış. Lütfen uygulamayı sunucu üzerinden açın.");
        return;
    }

    document.querySelector('.upload-section').classList.add('hidden');
    document.getElementById('batch-section').classList.remove('hidden');
    
    const tbody = document.getElementById('batch-table-body');
    tbody.innerHTML = '';
    batchResults = [];
    
    files.forEach((file, index) => {
        const tr = document.createElement('tr');
        tr.id = 'batch-row-' + index;
        tr.innerHTML = `
            <td>${file.name}</td>
            <td class="b-inv-no">-</td>
            <td class="b-date">-</td>
            <td class="b-vkn">-</td>
            <td class="b-name">-</td>
            <td class="b-amount">-</td>
            <td class="b-status"><span class="status-badge status-pending">Bekliyor...</span></td>
        `;
        tbody.appendChild(tr);
    });
    
    batchProcessing = true;
    const sendAllBtn = document.getElementById('send-all-btn');
    sendAllBtn.style.display = 'none';
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const row = document.getElementById('batch-row-' + i);
        
        try {
            row.querySelector('.b-status').innerHTML = '<span class="status-badge status-pending">Okunuyor...</span>';
            
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch('/upload', { method: 'POST', body: formData });
            
            if (!response.ok) {
                batchResults[i] = { file, success: false };
                row.querySelector('.b-status').innerHTML = '<span class="status-badge status-error" title="Sunucu yanıt vermedi veya API hatası oluştu." onclick="alert(\'Sunucu yanıt vermedi veya API hatası oluştu.\')" style="cursor:help; text-decoration: underline dotted;">Hata (Tıkla)</span>';
                continue;
            }
            
            const result = await readJsonResponse(response);

            if (result && result.data) {
                const data = result.data;
                batchResults[i] = { file, result, success: true };
                
                row.querySelector('.b-inv-no').textContent = data.invoice_no || '-';
                row.querySelector('.b-date').textContent = data.date || '-';
                row.querySelector('.b-vkn').textContent = data.customer_tax_id || '-';
                row.querySelector('.b-name').textContent = (data.customer_name || '-').substring(0, 20);
                
                let numTotal = data.total_amount || 0;
                    if (typeof numTotal === 'string') {
                        numTotal = window.InvoiceUiHelpers ? window.InvoiceUiHelpers.parseLocaleNumber(numTotal) : parseFloat(numTotal.replace(/\./g, '').replace(',', '.'));
                        if (isNaN(numTotal)) numTotal = 0;
                    }
                    const currencyCode = data.currency || 'TRY';
                    const formattedTotal = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: currencyCode }).format(numTotal);
                row.querySelector('.b-amount').textContent = formattedTotal;
                
                row.querySelector('.b-status').innerHTML = '<span class="status-badge status-success">Başarılı</span>';
                
                row.addEventListener('click', () => {
                    openSingleResultFromBatch(i);
                });
            } else {
                batchResults[i] = { file, result, success: false };
                const errorMsg = (result && result.message) ? result.message : 'Dosya okunamadı veya bilinmeyen hata';
                const fullError = errorMsg.replace(/"/g, '&quot;');
                const alertEscaped = fullError.replace(/'/g, '\\\'').replace(/\n/g, '\\n');
                row.querySelector('.b-status').innerHTML = `<span class="status-badge status-error" title="${fullError}" onclick="alert('${alertEscaped}')" style="cursor:help; text-decoration: underline dotted;">Hata (Tıkla)</span>`;
            }
        } catch (error) {
            batchResults[i] = { file, error, success: false };
            const errMsg = error.message || 'Bağlantı Hatası';
            row.querySelector('.b-status').innerHTML = `<span class="status-badge status-error" title="${errMsg}" onclick="alert('${errMsg}')" style="cursor:help; text-decoration: underline dotted;">Bağlantı Hatası</span>`;
        }
    }
    
    batchProcessing = false;
    
    if (batchResults.some(r => r && r.success)) {
        sendAllBtn.style.display = 'inline-flex';
    }
}

function openSingleResultFromBatch(index) {
    const item = batchResults[index];
    if (!item || !item.success) return;
    
    document.getElementById('batch-section').classList.add('hidden');
    document.getElementById('split-container').classList.remove('hidden');
    document.getElementById('split-container').classList.add('split-active');
    document.getElementById('back-to-batch-btn').classList.remove('hidden');
    
    if (pdfObjectUrl) {
        URL.revokeObjectURL(pdfObjectUrl);
        pdfObjectUrl = null;
    }
    
    if (item.file.type === 'application/pdf' || ['image/jpeg', 'image/png', 'image/webp'].includes(item.file.type)) {
        pdfObjectUrl = URL.createObjectURL(item.file);
        document.getElementById('pdf-iframe').src = pdfObjectUrl;
        document.getElementById('pdf-viewer-section').classList.remove('hidden');
        document.querySelector('.app-container').classList.add('wide-mode');
        document.getElementById('toggle-pdf-btn').style.display = 'flex';
    } else {
        document.getElementById('pdf-viewer-section').classList.add('hidden');
        document.querySelector('.app-container').classList.remove('wide-mode');
        document.getElementById('toggle-pdf-btn').style.display = 'none';
    }
    
    currentInvoiceData = item.result.data;
    renderInvoice(item.result);
    updateValidationUI(item.result);
    document.getElementById('send-draft-btn').classList.remove('hidden');
    document.getElementById('results-section').classList.remove('hidden');
}

const backBtn = document.getElementById('back-to-batch-btn');
if (backBtn) {
    backBtn.addEventListener('click', () => {
        document.getElementById('split-container').classList.add('hidden');
        document.getElementById('split-container').classList.remove('split-active');
        document.getElementById('batch-section').classList.remove('hidden');
        
        if (pdfObjectUrl) {
            URL.revokeObjectURL(pdfObjectUrl);
            pdfObjectUrl = null;
        }
        document.getElementById('pdf-iframe').src = '';
    });
}

const sendAllBtn = document.getElementById('send-all-btn');
if (sendAllBtn) {
    sendAllBtn.addEventListener('click', async () => {
        if (batchProcessing) return;
        
        if (!confirm("Listedeki başarılı tüm faturaları Uyumsoft'a taslak olarak göndermek istediğinize emin misiniz?")) {
            return;
        }
        
        sendAllBtn.disabled = true;
        sendAllBtn.textContent = 'Gönderiliyor...';
        
        for (let i = 0; i < batchResults.length; i++) {
            const item = batchResults[i];
            if (!item || !item.success || item.sent) continue;
            
            const row = document.getElementById('batch-row-' + i);
            row.querySelector('.b-status').innerHTML = '<span class="status-badge status-pending">Gönderiliyor...</span>';
            
            try {
                const response = await fetch('/api/uyumsoft/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ invoice_data: item.result.data, action: 'draft', environment: document.documentElement.dataset.uyumsoftEnvironment || 'test' })
                });
                const resData = await response.json();
                
                if (response.ok && resData.success !== false) {
                    row.querySelector('.b-status').innerHTML = '<span class="status-badge status-success">Gönderildi</span>';
                    item.sent = true;
                } else {
                    const errorMsg = resData.message || 'Uyumsoft Hatası';
                    const errorDetails = resData.details || '';
                    const fullError = (errorMsg + (errorDetails ? '\nDetaylar: ' + errorDetails : '')).replace(/"/g, '&quot;');
                    const alertEscaped = fullError.replace(/'/g, '\\\'').replace(/\n/g, '\\n');
                    row.querySelector('.b-status').innerHTML = `<span class="status-badge status-error" title="${fullError}" onclick="alert('${alertEscaped}')" style="cursor:help; text-decoration: underline dotted;">Hata (Tıkla)</span>`;
                }
            } catch (e) {
                const errMsg = e.message || 'Ağ Hatası';
                row.querySelector('.b-status').innerHTML = `<span class="status-badge status-error" title="${errMsg}" onclick="alert('${errMsg}')" style="cursor:help; text-decoration: underline dotted;">Ağ Hatası</span>`;
            }
        }
        
        sendAllBtn.disabled = false;
        sendAllBtn.textContent = "Tümünü Gönderildi";
    });
}
});
