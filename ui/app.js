document.addEventListener('DOMContentLoaded', () => {
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

    // Add event listener for draft send
    document.getElementById('send-draft-btn').addEventListener('click', () => {
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


    const dropZone = document.getElementById('drop-zone');


    const fileInput = document.getElementById('file-input');
    const loading = document.getElementById('loading');
    const resultsSection = document.getElementById('results-section');
    const UYUMSOFT_PORTAL_URL = 'http://portal-test.uyumsoft.com.tr/Taslak';

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
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    });
    
    let currentInvoiceData = null;
let currentUploadId = null;
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

    function textOrDash(value) {
        if (value === null || value === undefined || String(value).trim() === '') return '-';
        return String(value);
    }

    function parseMoney(value) {
        if (value === null || value === undefined || value === '') return 0;

        let text = String(value).replace(/[^0-9.,-]/g, '');
        if (text.includes(',') && text.includes('.')) {
            text = text.lastIndexOf(',') > text.lastIndexOf('.')
                ? text.replace(/\./g, '').replace(',', '.')
                : text.replace(/,/g, '');
        } else if (text.includes(',')) {
            const parts = text.split(',');
            text = parts.length > 1 && parts.slice(1).every(part => part.length === 3)
                ? text.replace(/,/g, '')
                : text.replace(',', '.');
        } else if (text.includes('.')) {
            const parts = text.split('.');
            if (parts.length > 1 && parts.slice(1).every(part => part.length === 3)) {
                text = text.replace(/\./g, '');
            }
        }

        return Number.parseFloat(text) || 0;
    }

    function appendTextCell(row, value, className = '') {
        const cell = document.createElement('td');
        if (className) cell.className = className;
        cell.textContent = textOrDash(value);
        row.appendChild(cell);
        return cell;
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

    async function readJsonResponse(response) {
        const text = await response.text();
        try {
            return JSON.parse(text);
        } catch (error) {
            throw new Error(`Sunucu JSON yerine hata sayfası döndürdü (HTTP ${response.status}). Sayfayı yenileyip tekrar deneyin.`);
        }
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
                
                // Automated UI Checklist Flow
                document.getElementById('send-draft-btn').classList.add('hidden');
                const workflowPanel = document.getElementById('workflow-progress');
                const checklist = document.getElementById('checklist');
                workflowPanel.classList.remove('hidden');
                checklist.innerHTML = ''; // Clear previous
                
                if (result.is_valid) {
                    // Show successful validation steps
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Fatura okundu</li>`;
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Toplamlar doğrulandı</li>`;
                    if (currentInvoiceData && currentInvoiceData._uyumsoft_customer_lookup === 'matched') {
                        checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Müşteri adı Uyumsoft mükellef listesinden eşleştirildi</li>`;
                    }
                    
                    checklist.innerHTML += `<li class="pending">Fatura geçerli. Uyumsoft'a göndermek için "Taslak Olarak Gönder" butonunu kullanın.</li>`;
                    document.getElementById('send-draft-btn').classList.remove('hidden');
                } else {
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Fatura okundu</li>`;
                    checklist.innerHTML += `<li class="error"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg> Fatura okundu ancak aktarım durduruldu.</li>`;
                    
                }
            } else {
                showError("Sunucu Hatası: " + (result.detail || "Bilinmeyen hata"));
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

        cell.appendChild(input);
        row.appendChild(cell);
        return cell;
    }

    let validationTimeout = null;
    let validationAbortController = null;

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
        if (!currentInvoiceData || !currentInvoiceData.items) return;
        
        if (itemIndex === -1) {
            currentInvoiceData[fieldName] = newValue;
            if (fieldName === 'customer_name') {
                // customer_name is the editable/canonical field. Keep the
                // legacy alias in sync so no downstream serializer can revive
                // the pre-edit value.
                currentInvoiceData.customer_title = newValue;
            }
        } else {
            currentInvoiceData.items[itemIndex][fieldName] = newValue;
        }
        
        document.getElementById('send-draft-btn').disabled = true;
        const badge = document.getElementById('validation-badge');
        badge.textContent = 'Doğrulanıyor...';
        badge.className = 'badge';

        clearTimeout(validationTimeout);
        validationTimeout = setTimeout(() => {
            validateCurrentData();
        }, 500);
    }

    async function validateCurrentData() {
        if (!currentInvoiceData) return;
        
        if (validationAbortController) {
            validationAbortController.abort();
        }
        validationAbortController = new AbortController();
        
        try {
            const response = await fetch('/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentInvoiceData),
                signal: validationAbortController.signal
            });
            const result = await readJsonResponse(response);
            if (response.ok) {
                updateValidationUI(result);
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error("Validasyon hatası:", err);
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
            td.colSpan = 8;
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
                appendTextCell(tr, item.tax_amount || '-'); // Tax amount is computed
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
        if (result.is_valid) {
            badge.textContent = 'GEÇERLİ';
            badge.className = 'badge valid';
            document.getElementById('portal-btn').classList.remove('hidden');
            document.getElementById('send-draft-btn').disabled = false;
        } else {
            badge.textContent = 'HATALI';
            badge.className = 'badge error';
            document.getElementById('send-draft-btn').disabled = true;
        }
        renderValidationErrors(result.is_valid ? [] : result.errors);
        document.getElementById('csv-btn').classList.remove('hidden');

        // Ensure data exists before accessing properties
        const data = result.data || {};

        const getSymbol = (currency) => {
            if (currency === 'USD') return '$';
            if (currency === 'EUR') return '€';
            if (currency === 'GBP') return '£';
            return '₺';
        };
        const sym = getSymbol(data.currency);
        const globalSubtotal = parseMoney(data.subtotal);
        const globalTax = parseMoney(data.tax_amount);
        const globalRate = globalSubtotal && globalTax ? (globalTax / globalSubtotal * 100) : 0;

        // Update summary cards
        function updateInputIfNotFocused(id, value) {
            const el = document.getElementById(id);
            if (document.activeElement !== el) {
                el.value = value || '';
            }
        }

        updateInputIfNotFocused('res-invoice-no', data.invoice_no);
        
        updateInputIfNotFocused('res-date', data.date);
        updateInputIfNotFocused('res-time', data.time);
        updateInputIfNotFocused('res-vkn', data.customer_tax_id);
        const customerName = data.customer_name || data.customer_title || data.customer || '';
        updateInputIfNotFocused('res-customer-name', customerName);
        document.getElementById('res-method').textContent = data._extraction_method || '-';
        document.getElementById('res-subtotal').textContent = data.subtotal ? `${sym}${data.subtotal}` : '-';

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
            breakdownDiv.innerHTML = '';
            if (data.items && data.items.length > 0 && data.tax_amount) {
                const breakdown = {};
                let calcSub = 0;
                data.items.forEach(item => {
                    let rate = item.tax_rate !== undefined && item.tax_rate !== null && String(item.tax_rate).trim() !== ""
                        ? parseMoney(item.tax_rate)
                        : Math.round(globalRate);
                    let total = parseMoney(item.total_price);
                    if (total === 0 && item.unit_price && item.quantity) {
                        total = parseMoney(item.unit_price) * parseMoney(item.quantity);
                    }
                    calcSub += total;
                    if (!breakdown[rate]) breakdown[rate] = { taxable: 0 };
                    breakdown[rate].taxable += total;
                });

                const discountAmt = parseMoney(data.discount_amount);
                let breakdownHtml = '';
                let totalTax = 0;
                for (let rate in breakdown) {
                    let taxable = breakdown[rate].taxable;
                    if (discountAmt > 0 && calcSub > 0) {
                        taxable -= discountAmt * (taxable / calcSub);
                    }
                    const tax = taxable * parseFloat(rate) / 100;
                    if (tax > 0 || parseFloat(rate) === 0) {
                        totalTax += tax;
                        const formattedTax = tax.toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                        breakdownHtml += `
                            <div style="color: #c0392b; margin-bottom: 2px;">%${rate} = ${formattedTax}</div>
                        `;
                    }
                }
                const formattedTotalTax = totalTax.toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                breakdownHtml += `<div style="color: #2980b9; margin-top: 4px;">Top = ${formattedTotalTax}</div>`;
                breakdownDiv.innerHTML = breakdownHtml;
            } else {
                breakdownDiv.textContent = data.tax_amount ? `${sym}${data.tax_amount}` : '-';
            }
        }

        document.getElementById('res-total').textContent = data.total_amount ? `${sym}${data.total_amount}` : '-';
        
        const notesCard = document.getElementById('notes-card');
        if (notesCard && data.notes && data.notes.trim() !== '') {
            document.getElementById('res-notes').textContent = data.notes.trim();
            notesCard.classList.remove('hidden');
        } else if (notesCard) {
            notesCard.classList.add('hidden');
        }
        

    }
    
    // Uyumsoft send logic: used automatically after validation.
            async function runUyumsoftAction() {
        if (!currentInvoiceData) return;
        const capturedUploadId = currentUploadId;
        const sendBtn = document.getElementById('send-draft-btn');
        sendBtn.disabled = true;
        
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
                body: JSON.stringify({ invoice_data: currentInvoiceData, action })
            });
            
            const result = await readJsonResponse(response);
            
                        if (result.success) {
                if (currentUploadId !== capturedUploadId) return;
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
                statusBox.style.backgroundColor = '#dc2626';
                statusBox.innerHTML = `❌ Hata: ${escapeHtml(result.message)}${details ? ` <br> <small>${escapeHtml(details)}</small>` : ''}`;
                sendBtn.disabled = false;
            }
        } catch (error) {
            if (currentUploadId !== capturedUploadId) return;
            statusBox.style.backgroundColor = '#dc2626';
            statusBox.innerHTML = `❌ Bağlantı Hatası: ${error.message}`;
            sendBtn.disabled = false;
        }
    }

    document.getElementById('portal-btn').addEventListener('click', openUyumsoftPortal);

    document.getElementById('csv-btn').addEventListener('click', () => {
        if (!currentInvoiceData || !currentInvoiceData.items) return;
        
        const headers = ['Urun Kodu', 'Urun Aciklamasi', 'Seri Numaralari', 'Miktar', 'Birim Fiyat', 'KDV Orani', 'KDV Tutari', 'Satir Toplami'];
        const rows = [headers.map(csvCell).join(',')];
        
        const tbody = document.querySelector('#items-table tbody');
        for (const tr of tbody.rows) {
            if (tr.cells.length === 1) continue; // Skip empty message
            const rowData = Array.from(tr.cells, cell => {
                const input = cell.querySelector('input');
                const val = input ? input.value : (cell.dataset.csvValue !== undefined ? cell.dataset.csvValue : cell.textContent);
                return csvCell(val);
            });
            rows.push(rowData.join(','));
        }
        
        rows.push('');
        rows.push(['Ara Toplam', '', '', '', '', '', '', document.getElementById('res-subtotal').textContent].map(csvCell).join(','));
        rows.push(['Genel Toplam', '', '', '', '', '', '', document.getElementById('res-total').textContent].map(csvCell).join(','));
        
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
    });

    function showError(msg) {
        const errorBox = document.getElementById('error-box');
        errorBox.textContent = msg;
        errorBox.classList.remove('hidden');
        resultsSection.classList.remove('hidden');
        document.getElementById('split-container').classList.remove('hidden');
    }

    document.getElementById('toggle-pdf-btn').addEventListener('click', () => {
        const pdfSection = document.getElementById('pdf-viewer-section');
        const splitContainer = document.getElementById('split-container');
        const appContainer = document.querySelector('.app-container');
        const icon = document.querySelector('#toggle-pdf-btn svg');
        
        if (pdfSection.classList.contains('hidden')) {
            pdfSection.classList.remove('hidden');
            splitContainer.classList.add('split-active');
            appContainer.classList.add('wide-mode');
            if (icon) icon.style.transform = 'rotate(0deg)';
        } else {
            pdfSection.classList.add('hidden');
            splitContainer.classList.remove('split-active');
            appContainer.classList.remove('wide-mode');
            if (icon) icon.style.transform = 'rotate(180deg)';
        }
        if (icon) icon.style.transition = 'transform 0.3s ease';
    });

    // UI event listeners initialized.
});
