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
            const icon = document.getElementById('theme-icon');
            if (icon) {
                icon.classList.remove('theme-spin-animate');
                // trigger reflow to restart animation
                void icon.offsetWidth;
                icon.classList.add('theme-spin-animate');
                setTimeout(() => icon.classList.remove('theme-spin-animate'), 400);
            }
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

    // Color theme logic
    const colorDots = document.querySelectorAll('.color-dot');
    const savedColor = localStorage.getItem('colorTheme') || 'cyan';
    
    // Set initial active state based on savedColor
    colorDots.forEach(dot => {
        if (dot.dataset.color === savedColor) {
            dot.classList.add('active');
        } else {
            dot.classList.remove('active');
        }
        
        // Add click listener
        dot.addEventListener('click', () => {
            const color = dot.dataset.color;
            
            // Set attribute and save
            if (color === 'ocean') {
                document.documentElement.removeAttribute('data-color');
            } else {
                document.documentElement.setAttribute('data-color', color);
            }
            localStorage.setItem('colorTheme', color);
            
            // Update active class
            colorDots.forEach(d => d.classList.remove('active'));
            dot.classList.add('active');
        });
    });

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
    let currentSendAbortController = null;

    // Add event listener for draft send
    document.getElementById('send-draft-btn').addEventListener('click', async () => {
        if (currentValidationState === 'pending') {
            showDraftValidationPopup(
                ['Yaptığınız değişikliklerin doğrulanması henüz tamamlanmadı. Lütfen kısa bir süre sonra tekrar deneyin.'],
                'Fatura henüz gönderilemez.'
            );
            return;
        }
        if (currentValidationState === 'invalid') {
            showDraftValidationPopup(currentValidationErrors, "Fatura hatalı.");
            return;
        }

        const proceed = await ensureUyumsoftCredentials();
        if (!proceed) return;

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
            if (response.ok) {
                const config = await response.json();
                if (config.uyumsoft_portal_url) {
                    UYUMSOFT_PORTAL_URL = config.uyumsoft_portal_url;
                }
            }
        } catch (error) {
            console.warn('Uyumsoft portal URL okunamadı.', error);
        }

        const localEnv = localStorage.getItem('uyumsoft_environment') || 'test';
        document.documentElement.dataset.uyumsoftEnvironment = localEnv;
        const selects = document.querySelectorAll('.env-dropdown');
        selects.forEach(s => s.value = localEnv);
        updateEnvironmentBadges(localEnv);
    }

    // Credentials Modal Logic
    const credModal = document.getElementById('credentials-modal');
    const credSaveBtn = document.getElementById('cred-save-btn');
    const credCancelBtn = document.getElementById('cred-cancel-btn');
    const credUser = document.getElementById('cred-username');
    const credPass = document.getElementById('cred-password');
    const envSelects = document.querySelectorAll('.env-dropdown');

    envSelects.forEach(select => {
        select.addEventListener('change', (e) => {
            const val = e.target.value;
            localStorage.setItem('uyumsoft_environment', val);
            document.documentElement.dataset.uyumsoftEnvironment = val;
            updateEnvironmentBadges(val);
            
            // Sync other dropdowns
            envSelects.forEach(s => {
                if (s !== e.target) s.value = val;
            });
        });
    });

    function ensureUyumsoftCredentials() {
        return new Promise((resolve) => {
            const env = localStorage.getItem('uyumsoft_environment') || 'test';
            if (env !== 'prod') {
                resolve(true);
                return;
            }
            const savedUser = localStorage.getItem('uyumsoft_username');
            const savedPass = localStorage.getItem('uyumsoft_password');
            if (savedUser && savedPass) {
                resolve(true);
                return;
            }
            
            // Show modal and wait for user
            credUser.value = savedUser || '';
            credPass.value = savedPass || '';
            credModal.classList.remove('hidden');

            const onSave = () => {
                localStorage.setItem('uyumsoft_username', credUser.value.trim());
                localStorage.setItem('uyumsoft_password', credPass.value.trim());
                cleanup();
                resolve(true);
            };

            const onCancel = () => {
                cleanup();
                resolve(false);
            };

            const cleanup = () => {
                credModal.classList.add('hidden');
                credSaveBtn.removeEventListener('click', onSave);
                credCancelBtn.removeEventListener('click', onCancel);
            };

            credSaveBtn.addEventListener('click', onSave);
            credCancelBtn.addEventListener('click', onCancel);
        });
    }

    function updateEnvironmentBadges(environment) {
        const isProd = environment === 'prod';
        const isTest = environment === 'test';
        const text = isProd
            ? 'Uyumsoft ortamı: GERÇEK / CANLI'
            : isTest
                ? 'Uyumsoft ortamı: TEST / ÖN KABUL'
                : 'Uyumsoft ortamı: BİLİNMİYOR — gönderim kapalı';
        document.querySelectorAll(
            '#uyumsoft-environment-badge, #batch-uyumsoft-environment-badge'
        ).forEach(badge => {
            badge.textContent = text;
            badge.classList.toggle('prod', isProd);
            badge.classList.toggle('test', isTest);
            badge.classList.toggle('unknown', !isProd && !isTest);
        });
    }

    function getRuntimeEnvironment() {
        const environment = document.documentElement.dataset.uyumsoftEnvironment;
        return environment === 'prod' || environment === 'test' ? environment : null;
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
        const icon = document.createElement('span');
        icon.setAttribute('aria-hidden', 'true');
        icon.style.flexShrink = '0';
        icon.textContent = {
            success: '✓',
            error: '✕',
            pending: '◷',
            warning: '⚠',
        }[state] || '•';
        const label = document.createElement('span');
        label.textContent = message;
        item.append(icon, label);
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

        if (state === 'send_error') {
            appendWorkflowItem(checklist, 'error', message || 'Uyumsoft gönderimi başarısız oldu. Tekrar deneyebilirsiniz.');
            return;
        }

        if (state === 'sent') {
            appendWorkflowItem(checklist, 'success', message || 'Fatura Uyumsoft taslaklarına gönderildi.');
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
        persistActiveBatchItem();
        if (!draftSendInProgress) setBatchNavigationDisabled(false);
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

    document.getElementById('cancel-btn').addEventListener('click', () => {
        if (currentAbortController) currentAbortController.abort();
    });

    async function handleFile(file) {
        if (window.location.protocol === 'file:') {
            showError("Bu sayfa dosya olarak açılmış. Lütfen uygulamayı http://127.0.0.1:7860/ui/ adresinden açın.");
            return;
        }
        
        invalidateBatchForSingleUpload();
        if (currentSendAbortController) {
            currentSendAbortController.abort();
            currentSendAbortController = null;
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
            document.getElementById('res-tax-breakdown').textContent = '-';
        }
        document.getElementById('res-total').textContent = '-';
        if (document.getElementById('notes-card')) {
            document.getElementById('notes-card').classList.add('hidden');
            document.getElementById('res-notes').textContent = '-';
        }
        document.querySelector('#items-table tbody').replaceChildren();
        
        const formData = new FormData();
        formData.append('file', file);
        
        // Set up AbortController
        if (currentAbortController) {
            currentAbortController.abort();
        }
        currentAbortController = new AbortController();
        const signal = currentAbortController.signal;
        
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
        persistActiveBatchItem();
        setBatchNavigationDisabled(true);

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
                persistActiveBatchItem();
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
        tbody.replaceChildren();
        
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
        if (!draftSendInProgress) setBatchNavigationDisabled(false);

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
    
    function renderApiProgress(statusBox, label) {
        const progressBar = document.createElement('div');
        progressBar.className = 'fake-progress-bar';
        const content = document.createElement('div');
        content.style.position = 'relative';
        content.style.zIndex = '1';
        content.style.display = 'flex';
        content.style.alignItems = 'center';
        const spinner = document.createElement('div');
        spinner.className = 'spinner';
        spinner.style.width = '20px';
        spinner.style.height = '20px';
        spinner.style.borderWidth = '2px';
        spinner.style.display = 'inline-block';
        spinner.style.marginRight = '10px';
        const text = document.createElement('span');
        text.textContent = `${label} çalışıyor...`;
        content.append(spinner, text);
        statusBox.replaceChildren(progressBar, content);
    }

    function renderApiMessage(statusBox, message, backgroundColor) {
        statusBox.style.backgroundColor = backgroundColor;
        statusBox.textContent = message;
    }

    function markActiveBatchSendResult(sent, message = '') {
        if (activeBatchIndex === null) return;
        const batchItem = batchResults[activeBatchIndex];
        if (!batchItem || batchItem.generation !== batchGenerationId) return;
        batchItem.sent = sent;
        if (sent) {
            setBatchStatus(activeBatchIndex, 'success', 'Gönderildi');
        } else if (message) {
            setBatchStatus(activeBatchIndex, 'error', 'Gönderim Hatası (Tıkla)', message);
        }
        updateBatchActions();
    }

    function setSendFailureState(message, validationErrors = null) {
        draftSendInProgress = false;
        setEditingDisabled(false);
        setBatchNavigationDisabled(false);
        const sendBtn = document.getElementById('send-draft-btn');
        sendBtn.classList.remove('hidden');
        sendBtn.disabled = false;
        document.getElementById('portal-btn').classList.add('hidden');

        if (Array.isArray(validationErrors) && validationErrors.length > 0) {
            currentInvoiceIsValid = false;
            currentValidationErrors = validationErrors;
            currentValidationState = 'invalid';
            setDraftButtonValidationState('invalid');
            setCsvValidationState('invalid');
            renderValidationErrors(validationErrors);
        }

        const badge = document.getElementById('validation-badge');
        badge.textContent = Array.isArray(validationErrors) && validationErrors.length > 0
            ? 'HATALI'
            : 'GÖNDERİM HATASI';
        badge.className = 'badge error';
        updateWorkflowUI('send_error', currentInvoiceData, message);
        markActiveBatchSendResult(false, message);
    }

    // Send only the immutable, user-reviewed snapshot after validation.
    async function runUyumsoftAction() {
        if (!currentInvoiceData || draftSendInProgress) return;
        if (currentValidationState !== 'valid' || !currentInvoiceIsValid) {
            showDraftValidationPopup();
            return;
        }

        const env = getRuntimeEnvironment();
        if (!env) {
            showDraftValidationPopup(
                ['Sunucunun Uyumsoft ortam ayarı okunamadı. Sayfayı yenileyip tekrar deneyin.'],
                'Uyumsoft ortamı doğrulanamadı.'
            );
            return;
        }
        const capturedUploadId = currentUploadId;
        const capturedValidationRevision = validationRevision;
        const invoiceSnapshot = JSON.parse(JSON.stringify(currentInvoiceData));
        const sendBtn = document.getElementById('send-draft-btn');
        draftSendInProgress = true;
        sendBtn.disabled = true;
        setEditingDisabled(true);
        setBatchNavigationDisabled(true);
        if (currentSendAbortController) currentSendAbortController.abort();
        const sendAbortController = new AbortController();
        currentSendAbortController = sendAbortController;
        
        const statusBox = document.getElementById('api-status-box');
        const action = 'draft';
        const actionLabel = 'Taslak Oluştur';
        statusBox.classList.remove('hidden');
        statusBox.style.position = 'relative';
        statusBox.style.overflow = 'hidden';
        statusBox.style.backgroundColor = '#3b82f6';
        statusBox.style.color = '#fff';
        renderApiProgress(statusBox, actionLabel);
        
        try {
            const response = await fetch('/send-uyumsoft', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    invoice_data: invoiceSnapshot,
                    action: action,
                    environment: localStorage.getItem('uyumsoft_environment') || 'test',
                    username: localStorage.getItem('uyumsoft_username') || null,
                    password: localStorage.getItem('uyumsoft_password') || null
                }),
                signal: sendAbortController.signal
            });
            
            const result = await readJsonResponse(response);
            
            if (response.ok && result.success === true) {
                if (
                    currentUploadId !== capturedUploadId
                    || validationRevision !== capturedValidationRevision
                ) return;
                document.getElementById('send-draft-btn').classList.add('hidden');
                draftSendInProgress = false;
                setBatchNavigationDisabled(false);
                renderApiMessage(statusBox, `✓ ${result.message || 'Taslak oluşturuldu.'} (HTTP ${result.response_code || response.status})`, '#059669');
                updateWorkflowUI('sent', currentInvoiceData);
                markActiveBatchSendResult(true);
                
                if (window.Notification && Notification.permission === 'granted') {
                    const notification = new Notification("Uyumsoft Entegrasyonu", {
                        body: "Fatura başarıyla Uyumsoft'a aktarıldı. Portalı açmak için tıklayın."
                    });
                    notification.addEventListener('click', () => {
                        window.focus();
                        openUyumsoftPortal();
                        notification.close();
                    });
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
                const message = `Uyumsoft gönderimi başarısız: ${result.message || 'Bilinmeyen hata'}${details ? ` — ${details}` : ''}`;
                renderApiMessage(statusBox, `❌ ${message}`, '#dc2626');
                const validationErrors = Number(result.response_code || response.status) === 400 && Array.isArray(result.details)
                    ? result.details
                    : null;
                setSendFailureState(message, validationErrors);
                if (validationErrors) showDraftValidationPopup(validationErrors, 'Fatura doğrulama hataları nedeniyle taslak gönderilemedi.');
            }
        } catch (error) {
            if (currentUploadId !== capturedUploadId) return;
            if (error.name === 'AbortError') return;
            const message = `Bağlantı Hatası: ${error && error.message ? error.message : 'Bilinmeyen hata'}`;
            renderApiMessage(statusBox, `❌ ${message}`, '#dc2626');
            setSendFailureState(message);
        } finally {
            if (currentSendAbortController === sendAbortController) {
                currentSendAbortController = null;
            }
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

    // UI event listeners initialized.

// --- BATCH PROCESSING LOGIC ---
let batchResults = [];
let batchProcessing = false;
let batchGenerationId = null;
let batchUploadAbortController = null;
let batchSendAbortController = null;
let activeBatchIndex = null;
let batchDetailRevision = 0;

function isCurrentBatchGeneration(generation) {
    return Boolean(generation) && batchGenerationId === generation;
}

function setBatchNavigationDisabled(disabled) {
    const batchBackButton = document.getElementById('batch-back-btn');
    const detailBackButton = document.getElementById('back-to-batch-btn');
    if (batchBackButton) batchBackButton.disabled = disabled;
    if (detailBackButton) detailBackButton.disabled = disabled;
}

function cancelBatchRequests() {
    if (batchUploadAbortController) batchUploadAbortController.abort();
    if (batchSendAbortController) batchSendAbortController.abort();
    batchUploadAbortController = null;
    batchSendAbortController = null;
}

function invalidateBatchForSingleUpload() {
    cancelBatchRequests();
    batchGenerationId = null;
    batchProcessing = false;
    activeBatchIndex = null;
    batchResults = [];
    document.getElementById('batch-section').classList.add('hidden');
    document.getElementById('back-to-batch-btn').classList.add('hidden');
    document.getElementById('batch-table-body').replaceChildren();
    document.getElementById('send-all-btn').style.display = 'none';
    document.getElementById('send-all-success-text').style.display = 'none';
    const loadingText3 = document.getElementById('send-all-loading-text');
    if (loadingText3) loadingText3.style.display = 'none';
    setBatchNavigationDisabled(false);
}

function resetSingleViewForBatch(generation) {
    if (currentAbortController) currentAbortController.abort();
    if (currentSendAbortController) currentSendAbortController.abort();
    if (validationAbortController) validationAbortController.abort();
    currentAbortController = null;
    currentSendAbortController = null;
    validationAbortController = null;
    clearTimeout(validationTimeout);
    validationRevision += 1;
    currentUploadId = `batch:${generation}`;
    currentInvoiceData = null;
    currentInvoiceIsValid = false;
    currentValidationErrors = [];
    currentValidationState = 'idle';
    draftSendInProgress = false;
    activeBatchIndex = null;
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    pdfObjectUrl = null;
    document.getElementById('pdf-iframe').src = '';
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('split-container').classList.add('hidden');
    document.getElementById('split-container').classList.remove('split-active');
    document.getElementById('results-section').classList.add('hidden');
    document.getElementById('back-to-batch-btn').classList.add('hidden');
    document.getElementById('send-draft-btn').classList.add('hidden');
    document.getElementById('portal-btn').classList.add('hidden');
    document.getElementById('csv-btn').classList.add('hidden');
    document.getElementById('api-status-box').classList.add('hidden');
    document.getElementById('error-box').classList.add('hidden');
    document.getElementById('workflow-progress').classList.add('hidden');
    document.querySelector('.app-container').classList.remove('wide-mode');
}

function createBatchCell(className, value = '-') {
    const cell = document.createElement('td');
    cell.className = className;
    cell.textContent = value;
    return cell;
}

function createBatchRow(file, index, generation) {
    const row = document.createElement('tr');
    row.id = `batch-row-${index}`;
    row.dataset.batchGeneration = generation;
    row.append(
        createBatchCell('b-file', file.name),
        createBatchCell('b-inv-no'),
        createBatchCell('b-date'),
        createBatchCell('b-vkn'),
        createBatchCell('b-name'),
        createBatchCell('b-amount'),
        createBatchCell('b-status', ''),
    );
    row.addEventListener('click', () => {
        if (!isCurrentBatchGeneration(generation) || batchProcessing) return;
        const item = batchResults[index];
        if (item && item.success) openSingleResultFromBatch(index);
    });
    setBatchStatus(index, 'pending', 'Bekliyor...', '', row);
    return row;
}

function setBatchStatus(index, state, label, details = '', suppliedRow = null) {
    const row = suppliedRow || document.getElementById(`batch-row-${index}`);
    if (!row || row.dataset.batchGeneration !== batchGenerationId) return;
    const cell = row.querySelector('.b-status');
    const badge = document.createElement('span');
    badge.className = `status-badge status-${state}`;
    if (label === 'Gönderildi') {
        badge.innerHTML = `<svg style="width: 14px; height: 14px; margin-right: 4px;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>${label}`;
        badge.style.display = 'inline-flex';
        badge.style.alignItems = 'center';
    } else {
        badge.textContent = label;
    }
    if (details) {
        badge.title = details;
        badge.style.cursor = 'help';
        badge.style.textDecoration = 'underline dotted';
        badge.addEventListener('click', event => {
            event.stopPropagation();
            window.alert(details);
        });
    }
    cell.replaceChildren(badge);

    const progRow = document.getElementById(`batch-progress-${index}`);
    if (progRow) {
        if (state === 'pending' && (label.includes('kunuyor') || label.includes('nderiliyor'))) {
            progRow.style.display = 'table-row';
        } else {
            progRow.style.display = 'none';
        }
    }
}

function formatBatchAmount(data) {
    const amount = parseLocaleNumber(data && data.total_amount);
    const currency = data && ['TRY', 'USD', 'EUR', 'GBP'].includes(data.currency)
        ? data.currency
        : 'TRY';
    if (amount === null) return '-';
    return new Intl.NumberFormat('tr-TR', { style: 'currency', currency }).format(amount);
}

function updateBatchRow(index) {
    const item = batchResults[index];
    const row = document.getElementById(`batch-row-${index}`);
    if (!item || !row || item.generation !== batchGenerationId) return;
    const data = item.result && item.result.data;
    if (data) {
        row.querySelector('.b-inv-no').textContent = data.invoice_no || '-';
        row.querySelector('.b-date').textContent = data.date || '-';
        row.querySelector('.b-vkn').textContent = data.customer_tax_id || '-';
        row.querySelector('.b-name').textContent = (data.customer_name || data.customer_title || '-').substring(0, 20);
        row.querySelector('.b-amount').textContent = formatBatchAmount(data);
    }

    if (item.sent) {
        setBatchStatus(index, 'success', 'Gönderildi');
    } else if (!item.success) {
        setBatchStatus(index, 'error', 'Hata (Tıkla)', item.errorMessage || 'Dosya işlenemedi.');
    } else if (item.validationPending) {
        setBatchStatus(index, 'pending', 'Doğrulanıyor...');
    } else if (item.result.is_valid === false) {
        const details = (item.result.errors || ['Fatura verileri eksik veya hatalı.']).join('\n');
        setBatchStatus(index, 'pending', 'İnceleme (Tıkla)', details);
    } else {
        setBatchStatus(index, 'success', 'Gönderime Hazır');
    }
}

function updateBatchActions() {
    const sendAllButton = document.getElementById('send-all-btn');
    const successText = document.getElementById('send-all-success-text');
    const loadingText = document.getElementById('send-all-loading-text');
    const liveItems = batchResults.filter(item => item && item.generation === batchGenerationId);
    const retryableItems = liveItems.filter(item => (
        item.success && !item.sent && !item.validationPending && item.result.is_valid !== false
    ));
    const sentCount = liveItems.filter(item => item.sent).length;
    const allRowsSent = liveItems.length > 0 && liveItems.every(item => (
        item.success && item.result.is_valid !== false && item.sent
    ));

    if (successText) {
        successText.style.display = allRowsSent ? 'flex' : 'none';
    }

    if (batchProcessing && typeof batchSendAbortController !== 'undefined' && batchSendAbortController) {
        sendAllButton.style.display = 'none';
        if (loadingText) loadingText.style.display = 'flex';
    } else {
        if (loadingText) loadingText.style.display = 'none';
        sendAllButton.style.display = !batchProcessing && retryableItems.length > 0 ? 'inline-flex' : 'none';
        sendAllButton.disabled = batchProcessing || retryableItems.length === 0;
        sendAllButton.innerHTML = sentCount > 0
            ? '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style="width: 20px; height: 20px;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Kalanları Uyumsoft\'a Gönder'
            : '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style="width: 20px; height: 20px;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Tümünü Uyumsoft\'a Gönder';
    }
}

function persistActiveBatchItem() {
    if (activeBatchIndex === null || !currentInvoiceData) return;
    const batchItem = batchResults[activeBatchIndex];
    if (!batchItem || batchItem.generation !== batchGenerationId || !batchItem.result) return;
    batchItem.result.data = currentInvoiceData;
    batchItem.result.is_valid = currentValidationState === 'valid';
    batchItem.result.errors = [...currentValidationErrors];
    batchItem.validationPending = currentValidationState === 'pending';
    if (currentValidationState === 'pending') batchItem.sent = false;
    updateBatchRow(activeBatchIndex);
    updateBatchActions();
}

async function handleBatchFiles(files) {
    if (window.location.protocol === 'file:') {
        showError('Bu sayfa dosya olarak açılmış. Lütfen uygulamayı sunucu üzerinden açın.');
        return;
    }
    if (!Array.isArray(files) || files.length === 0) return;

    cancelBatchRequests();
    const capturedBatchGeneration = crypto.randomUUID();
    batchGenerationId = capturedBatchGeneration;
    resetSingleViewForBatch(capturedBatchGeneration);
    document.querySelector('.upload-section').classList.add('hidden');
    document.getElementById('batch-section').classList.remove('hidden');
    const tbody = document.getElementById('batch-table-body');
    tbody.replaceChildren();
    batchResults = files.map(file => ({
        file,
        result: null,
        success: false,
        sent: false,
        validationPending: false,
        generation: capturedBatchGeneration,
        errorMessage: '',
    }));
    files.forEach((file, index) => {
        tbody.appendChild(createBatchRow(file, index, capturedBatchGeneration));
        const progTr = document.createElement('tr');
        progTr.className = 'progress-row';
        progTr.id = `batch-progress-${index}`;
        progTr.style.display = 'none';
        const progTd = document.createElement('td');
        progTd.colSpan = 7;
        const barContainer = document.createElement('div');
        barContainer.className = 'batch-progress-container';
        const bar = document.createElement('div');
        bar.className = 'batch-progress-bar';
        barContainer.appendChild(bar);
        progTd.appendChild(barContainer);
        progTr.appendChild(progTd);
        tbody.appendChild(progTr);
    });

    batchProcessing = true;
    batchUploadAbortController = new AbortController();
    setBatchNavigationDisabled(true);
    updateBatchActions();

    try {
        for (let index = 0; index < files.length; index += 1) {
            if (!isCurrentBatchGeneration(capturedBatchGeneration)) return;
            const item = batchResults[index];
            setBatchStatus(index, 'pending', 'Okunuyor...');
            const formData = new FormData();
            formData.append('file', item.file);

            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData,
                    signal: batchUploadAbortController.signal,
                });
                const result = await readJsonResponse(response);
                if (!isCurrentBatchGeneration(capturedBatchGeneration)) return;
                if (!response.ok || !result || !result.data) {
                    item.success = false;
                    item.result = result || null;
                    item.errorMessage = formatApiError(result) || `Sunucu Hatası (HTTP ${response.status})`;
                } else {
                    item.success = true;
                    item.result = result;
                    item.errorMessage = '';
                }
            } catch (error) {
                console.warn('Batch process suspended or error', error);
                batchProcessing = false;
                break;
            }
            updateBatchRow(index);
        }
    } finally {
        if (isCurrentBatchGeneration(capturedBatchGeneration)) {
            batchProcessing = false;
            batchUploadAbortController = null;
            setBatchNavigationDisabled(false);
            updateBatchActions();
        }
    }
}

function openSingleResultFromBatch(index) {
    const item = batchResults[index];
    if (!item || !item.success || item.generation !== batchGenerationId || batchProcessing) return;

    activeBatchIndex = index;
    batchDetailRevision += 1;
    currentUploadId = `batch-detail:${batchGenerationId}:${index}:${batchDetailRevision}`;
    validationRevision += 1;
    clearTimeout(validationTimeout);
    if (validationAbortController) validationAbortController.abort();
    validationAbortController = null;
    currentInvoiceData = JSON.parse(JSON.stringify(item.result.data));
    draftSendInProgress = false;

    document.getElementById('batch-section').classList.add('hidden');
    document.getElementById('split-container').classList.remove('hidden');
    document.getElementById('split-container').classList.add('split-active');
    document.getElementById('back-to-batch-btn').classList.remove('hidden');
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    pdfObjectUrl = null;

    if (item.file.type === 'application/pdf' || ['image/jpeg', 'image/png', 'image/webp'].includes(item.file.type)) {
        pdfObjectUrl = URL.createObjectURL(item.file);
        document.getElementById('pdf-iframe').src = pdfObjectUrl;
        document.getElementById('pdf-viewer-section').classList.remove('hidden');
        document.querySelector('.app-container').classList.add('wide-mode');
        document.getElementById('toggle-pdf-btn').style.display = 'flex';
    } else {
        document.getElementById('pdf-iframe').src = '';
        document.getElementById('pdf-viewer-section').classList.add('hidden');
        document.querySelector('.app-container').classList.remove('wide-mode');
        document.getElementById('toggle-pdf-btn').style.display = 'none';
    }

    const detailResult = { ...item.result, data: currentInvoiceData };
    renderInvoice(detailResult);
    updateValidationUI(detailResult);
    if (item.sent) {
        setEditingDisabled(true);
        document.getElementById('send-draft-btn').classList.add('hidden');
        updateWorkflowUI('sent', currentInvoiceData, 'Bu fatura Uyumsoft taslaklarına gönderildi.');
    } else {
        setEditingDisabled(false);
        document.getElementById('send-draft-btn').classList.remove('hidden');
    }
    document.getElementById('results-section').classList.remove('hidden');
    setBatchNavigationDisabled(false);
}

document.getElementById('back-to-batch-btn').addEventListener('click', () => {
    if (batchProcessing || draftSendInProgress || currentValidationState === 'pending') return;
    persistActiveBatchItem();
    validationRevision += 1;
    if (validationAbortController) validationAbortController.abort();
    validationAbortController = null;
    currentUploadId = `batch:${batchGenerationId}:${crypto.randomUUID()}`;
    activeBatchIndex = null;
    document.getElementById('split-container').classList.add('hidden');
    document.getElementById('split-container').classList.remove('split-active');
    if (batchGenerationId && batchResults.length > 0) {
        document.getElementById('batch-section').classList.remove('hidden');
    }
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    pdfObjectUrl = null;
    document.getElementById('pdf-iframe').src = '';
    updateBatchActions();
});

document.getElementById('send-all-btn').addEventListener('click', async () => {
    if (batchProcessing || !batchGenerationId) return;
    if (!getRuntimeEnvironment()) {
        window.alert('Sunucunun Uyumsoft ortam ayarı okunamadı. Sayfayı yenileyip tekrar deneyin.');
        return;
    }
    const eligibleIndexes = batchResults
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => item && item.success && !item.sent && !item.validationPending && item.result.is_valid !== false)
        .map(({ index }) => index);
    if (eligibleIndexes.length === 0) {
        updateBatchActions();
        return;
    }
    if (!confirm(`${eligibleIndexes.length} geçerli faturayı Uyumsoft'a taslak olarak göndermek istediğinize emin misiniz?`)) return;

    const proceed = await ensureUyumsoftCredentials();
    if (!proceed) return;

    const capturedBatchGeneration = batchGenerationId;
    batchProcessing = true;
    batchSendAbortController = new AbortController();
    setBatchNavigationDisabled(true);
    updateBatchActions();
    try {
        for (const index of eligibleIndexes) {
            if (!isCurrentBatchGeneration(capturedBatchGeneration)) return;
            const item = batchResults[index];
            setBatchStatus(index, 'pending', 'Gönderiliyor...');
            try {
                const response = await fetch('/send-uyumsoft', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        invoice_data: item.result.data, 
                        action: 'draft',
                        environment: localStorage.getItem('uyumsoft_environment') || 'test',
                        username: localStorage.getItem('uyumsoft_username') || null,
                        password: localStorage.getItem('uyumsoft_password') || null
                    }),
                    signal: batchSendAbortController.signal,
                });
                const result = await readJsonResponse(response);
                if (!isCurrentBatchGeneration(capturedBatchGeneration)) return;
                if (response.ok && result.success === true) {
                    item.sent = true;
                    item.errorMessage = '';
                } else {
                    item.sent = false;
                    item.errorMessage = `Uyumsoft Hatası: ${formatApiError(result)}`;
                }
            } catch (error) {
                if (error.name === 'AbortError' || !isCurrentBatchGeneration(capturedBatchGeneration)) return;
                item.sent = false;
                item.errorMessage = error.message || 'Ağ Hatası';
            }
            if (item.sent) setBatchStatus(index, 'success', 'Gönderildi');
            else setBatchStatus(index, 'error', 'Gönderim Hatası (Tıkla)', item.errorMessage);
        }
    } finally {
        if (isCurrentBatchGeneration(capturedBatchGeneration)) {
            batchProcessing = false;
            batchSendAbortController = null;
            setBatchNavigationDisabled(false);
            updateBatchActions();
        }
    }
});

document.getElementById('batch-back-btn').addEventListener('click', () => {
    if (batchProcessing || draftSendInProgress) return;
    cancelBatchRequests();
    batchGenerationId = null;
    batchResults = [];
    activeBatchIndex = null;
    document.getElementById('batch-section').classList.add('hidden');
    document.getElementById('batch-table-body').replaceChildren();
    document.querySelector('.upload-section').classList.remove('hidden');
    document.getElementById('send-all-btn').style.display = 'none';
    document.getElementById('send-all-success-text').style.display = 'none';
    const loadingText2 = document.getElementById('send-all-loading-text');
    if (loadingText2) loadingText2.style.display = 'none';
    setBatchNavigationDisabled(false);
});

document.getElementById('batch-uyumsoft-btn').addEventListener('click', openUyumsoftPortal);

window.addEventListener('beforeunload', () => {
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    if (currentAbortController) currentAbortController.abort();
    if (currentSendAbortController) currentSendAbortController.abort();
    cancelBatchRequests();
});

// --- History & Dashboard Logic ---
const historyToggleBtn = document.getElementById('history-toggle');
const closeHistoryBtn = document.getElementById('close-history-btn');
const historySection = document.getElementById('history-section');
const uploadSection = document.querySelector('.upload-section');
const splitContainer = document.getElementById('split-container');
const batchSection = document.getElementById('batch-section');

let historyCurrentPage = 1;
let historyChartInstance = null;

if (historyToggleBtn) {
    historyToggleBtn.addEventListener('click', () => {
        const icon = document.getElementById('history-icon');
        if (icon) {
            icon.classList.remove('history-rewind-animate');
            void icon.offsetWidth; // trigger reflow
            icon.classList.add('history-rewind-animate');
            setTimeout(() => icon.classList.remove('history-rewind-animate'), 500);
        }
        if (!historySection.classList.contains('hidden')) {
            historySection.classList.add('hidden');
            uploadSection.classList.remove('hidden');
            return;
        }
        
        // Hide other sections
        uploadSection.classList.add('hidden');
        splitContainer.classList.add('hidden');
        batchSection.classList.add('hidden');
        document.querySelector('.app-container').classList.remove('wide-mode');
        
        // Show history
        historySection.classList.remove('hidden');
        loadHistoryDashboard();
        loadHistoryTable(1);
    });
}

if (closeHistoryBtn) {
    closeHistoryBtn.addEventListener('click', () => {
        historySection.classList.add('hidden');
        uploadSection.classList.remove('hidden');
    });
}

document.getElementById('history-prev-page')?.addEventListener('click', () => {
    if (historyCurrentPage > 1) loadHistoryTable(historyCurrentPage - 1);
});
document.getElementById('history-next-page')?.addEventListener('click', () => {
    loadHistoryTable(historyCurrentPage + 1);
});

async function loadHistoryDashboard() {
    try {
        const res = await fetch('/api/history/dashboard');
        const json = await res.json();
        
        if (json.success && json.data) {
            // Format numbers
            const formatter = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            document.getElementById('history-total-revenue').textContent = formatter.format(json.data.total_revenue) + ' TL';
            document.getElementById('history-total-count').textContent = json.data.total_count;
            
            // Draw chart
            renderHistoryChart(json.data.trend);
            renderTopCustomersChart(json.data.top_customers);
        }
    } catch (e) {
        console.error('Error loading history dashboard', e);
    }
}

let topCustomersChartInstance = null;

function renderTopCustomersChart(topCustomersData) {
    const ctx = document.getElementById('topCustomersChart').getContext('2d');
    
    if (topCustomersChartInstance) {
        topCustomersChartInstance.destroy();
    }
    
    if (!topCustomersData || topCustomersData.length === 0) {
        return;
    }
    
    const labels = topCustomersData.map(item => item.customer_name);
    const dataPoints = topCustomersData.map(item => item.total_revenue);
    
    const colors = [
        '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'
    ];
    
    topCustomersChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataPoints,
                backgroundColor: colors,
                borderWidth: 1,
                borderColor: '#1e293b'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#94a3b8' } },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return new Intl.NumberFormat('tr-TR').format(context.raw) + ' ₺';
                        }
                    }
                }
            }
        }
    });
}

function renderHistoryChart(trendData) {
    const ctx = document.getElementById('historyChart').getContext('2d');
    
    if (historyChartInstance) {
        historyChartInstance.destroy();
    }
    
    if (!trendData || trendData.length === 0) {
        return; // Empty state handles gracefully in chart.js if no data, or we just don't draw
    }
    
    const labels = trendData.map(item => item.month); // e.g. "2026-07"
    const dataPoints = trendData.map(item => item.monthly_revenue);
    
    const computedStyle = getComputedStyle(document.documentElement);
    const accentColor = computedStyle.getPropertyValue('--accent-color').trim() || '#10b981';
    
    historyChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Aylık Ciro (TL)',
                data: dataPoints,
                borderColor: accentColor,
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return new Intl.NumberFormat('tr-TR').format(value) + ' ₺';
                        }
                    }
                }
            }
        }
    });
}

let searchTimeout = null;

document.getElementById('history-search-input')?.addEventListener('input', (e) => {
    if (searchTimeout) clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        loadHistoryTable(1);
    }, 500); // Debounce search
});

document.getElementById('history-date-filter')?.addEventListener('change', () => {
    loadHistoryTable(1);
});

async function loadHistoryTable(page) {
    const tbody = document.getElementById('history-table-body');
    const prevBtn = document.getElementById('history-prev-page');
    const nextBtn = document.getElementById('history-next-page');
    const pageInfo = document.getElementById('history-page-info');
    
    const searchInput = document.getElementById('history-search-input');
    const dateFilter = document.getElementById('history-date-filter');
    const searchVal = searchInput ? searchInput.value.trim() : '';
    const dateVal = dateFilter ? dateFilter.value : 'all';
    
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 2rem; color: var(--text-secondary);">Yükleniyor...</td></tr>';
    prevBtn.disabled = true;
    nextBtn.disabled = true;
    
    try {
        let url = `/api/history/invoices?page=${page}&limit=10`;
        if (searchVal) url += `&search=${encodeURIComponent(searchVal)}`;
        if (dateVal && dateVal !== 'all') url += `&date_filter=${encodeURIComponent(dateVal)}`;
        
        const res = await fetch(url);
        const json = await res.json();
        
        if (json.success && json.data) {
            const data = json.data;
            historyCurrentPage = data.page;
            
            pageInfo.textContent = `Sayfa ${data.page} / ${Math.max(1, data.total_pages)}`;
            prevBtn.disabled = data.page <= 1;
            nextBtn.disabled = data.page >= data.total_pages;
            
            if (data.items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 2rem; color: var(--text-secondary);">Henüz hiç fatura gönderilmemiş.</td></tr>';
                return;
            }
            
            const formatter = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            tbody.innerHTML = '';
            
            data.items.forEach(item => {
                const tr = document.createElement('tr');
                
                // Determine display status based on Uyumsoft or Local status
                let badgeClass = "badge-neutral";
                let statusText = item.uyumsoft_status || item.status || "Bilinmiyor";
                const exactStatus = statusText;
                
                // Exact status mapping per Uyumsoft specifications
                const blueStatuses = ['Queued', 'Processing', 'SentToGib', 'WaitingForAprovement'];
                const greenStatuses = ['Approved', 'Kabul Edildi'];
                const redStatuses = ['Declined', 'Return', 'Error', 'HATALI', 'Reddedildi'];
                const yellowStatuses = ['Draft', 'Taslak'];
                
                if (redStatuses.includes(exactStatus)) {
                    badgeClass = "badge-danger";
                } else if (greenStatuses.includes(exactStatus)) {
                    badgeClass = "badge-success";
                } else if (yellowStatuses.includes(exactStatus)) {
                    badgeClass = "badge-warning";
                } else if (blueStatuses.includes(exactStatus)) {
                    badgeClass = "badge-info";
                }
                
                // 1. Date column
                const tdDate = document.createElement('td');
                tdDate.textContent = item.date || item.created_at.split(' ')[0];
                tr.appendChild(tdDate);
                
                // 2. Invoice No column
                const tdNo = document.createElement('td');
                const noStrong = document.createElement('strong');
                noStrong.textContent = item.invoice_no || '-';
                tdNo.appendChild(noStrong);
                tr.appendChild(tdNo);
                
                // 3. Customer column
                const tdCustomer = document.createElement('td');
                tdCustomer.style.maxWidth = '250px';
                tdCustomer.style.overflow = 'hidden';
                tdCustomer.style.textOverflow = 'ellipsis';
                tdCustomer.style.whiteSpace = 'nowrap';
                tdCustomer.title = item.customer_name || '-';
                tdCustomer.textContent = item.customer_name || '-';
                tr.appendChild(tdCustomer);
                
                // 4. Amount column
                const tdAmount = document.createElement('td');
                tdAmount.style.textAlign = 'right';
                tdAmount.style.fontWeight = '600';
                tdAmount.textContent = `${formatter.format(item.amount_try || 0)} TL`;
                tr.appendChild(tdAmount);
                
                // 5. Status column
                const tdStatus = document.createElement('td');
                tdStatus.style.display = 'flex';
                tdStatus.style.alignItems = 'center';
                tdStatus.style.gap = '8px';
                
                const badge = document.createElement('span');
                badge.className = `badge ${badgeClass}`;
                badge.id = `status-badge-${item.id}`;
                badge.textContent = statusText;
                
                // Optionally show error message on hover if it's an error
                if (item.uyumsoft_message && badgeClass === 'badge-danger') {
                    badge.title = item.uyumsoft_message;
                    badge.style.cursor = 'help';
                }
                
                tdStatus.appendChild(badge);
                
                if (item.uyumsoft_document_id) {
                    const refreshBtn = document.createElement('button');
                    refreshBtn.className = 'btn btn-icon';
                    refreshBtn.style.padding = '4px';
                    refreshBtn.style.fontSize = '14px';
                    refreshBtn.title = 'Durumu Güncelle';
                    refreshBtn.textContent = '🔄';
                    refreshBtn.onclick = () => updateInvoiceStatus(item.id);
                    tdStatus.appendChild(refreshBtn);
                }
                
                tr.appendChild(tdStatus);
                tbody.appendChild(tr);
            });
        }
    } catch (e) {
        console.error("Error loading history:", e);
        tbody.innerHTML = \'<tr><td colspan="5" style="text-align: center; padding: 2rem; color: #ef4444;">Kayıtlar yüklenirken hata oluştu.</td></tr>\';
    }
}

});
