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
let validationRevisionId = 0;
let validationTimeout = null;

function handleInputChange(e) {
    if (!currentInvoiceData) return;
    const key = e.target.getAttribute('data-key');
    if (!key) return;

    if (key.startsWith('item-')) {
        const parts = key.split('-');
        const index = parseInt(parts[1], 10);
        const field = parts.slice(2).join('-');
        if (currentInvoiceData.items && currentInvoiceData.items[index]) {
            currentInvoiceData.items[index][field] = e.target.value;
        }
    } else if (key === 'date_time') {
        const parts = e.target.value.split(' ');
        currentInvoiceData.date = parts[0] || '';
        currentInvoiceData.time = parts[1] || '';
    } else {
        currentInvoiceData[key] = e.target.value;
    }

    triggerValidation();
}

document.addEventListener('input', (e) => {
    if (e.target.classList.contains('edit-input')) {
        handleInputChange(e);
    }
});

function triggerValidation() {
    clearTimeout(validationTimeout);
    const sendBtn = document.getElementById('send-draft-btn');
    if (sendBtn) sendBtn.disabled = true;
    const badge = document.getElementById('validation-badge');
    if (badge) {
        badge.textContent = 'DOĞRULANIYOR...';
        badge.className = 'badge';
    }
    
    validationTimeout = setTimeout(async () => {
        validationRevisionId++;
        const currentRev = validationRevisionId;
        
        try {
            const response = await fetch('/api/validate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ invoice_data: currentInvoiceData })
            });
            const result = await readJsonResponse(response);
            if (validationRevisionId !== currentRev) return;
            
            currentInvoiceData = result.invoice_data;
            updateValidationUI(result);
        } catch (e) {
            console.error("Validation error:", e);
        }
    }, 500);
}

function updateInputIfNotFocused(id, value) {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) {
        el.value = value == null ? '' : String(value);
    }
}

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
        document.getElementById('res-invoice-no').textContent = '-';
        document.getElementById('res-date-time').textContent = '-';
        document.getElementById('res-vkn').textContent = '-';
        document.getElementById('res-customer-name').textContent = '-';
        document.getElementById('res-method').textContent = '-';
        document.getElementById('res-subtotal').value = '-';
        if (document.getElementById('res-tax-breakdown')) {
            document.getElementById('res-tax-breakdown').innerHTML = '-';
        }
        document.getElementById('res-total').value = '-';
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
                    
                    checklist.innerHTML += `<li class="pending">Fatura geçerli. Lütfen Taslak Olarak Gönder butonunu kullanın.</li>`;
                    document.getElementById('send-draft-btn').classList.remove('hidden');
                } else {
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Fatura okundu</li>`;
                    checklist.innerHTML += `<li class="error"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg> Fatura okundu ancak aktarım durduruldu.</li>`;
                    
                  if (!result.is_valid && result.errors && result.errors.length > 0) {
                    const errorBox = document.getElementById('error-box');
                    errorBox.innerHTML = '<div style="display: flex; align-items: center; margin-bottom: 0.5rem;"><svg style="width: 24px; height: 24px; margin-right: 8px; color: #f87171;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><strong style="font-size: 1.1rem;">Lütfen faturadaki şu eksik veya hataları giderin:</strong></div>' + 
                    '<ul style="margin-left: 2rem; list-style-type: disc;">' + result.errors.map(e => `<li style="margin-bottom: 0.25rem;">${escapeHtml(e)}</li>`).join('') + '</ul>';
                    errorBox.classList.remove('hidden');
                }
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
    
    function renderInvoice(result) {
        resultsSection.classList.remove('hidden');
        document.getElementById('split-container').classList.remove('hidden');
        document.getElementById('csv-btn').classList.remove('hidden');
        
        const data = result.data || {};
        const getSymbol = (currency) => {
            if (currency === 'USD') return '$';
            if (currency === 'EUR') return '€';
            if (currency === 'GBP') return '£';
            return '₺';
        };
        const sym = getSymbol(data.currency);
        
        document.getElementById('res-invoice-no').value = data.invoice_no || '';
        let dateTimeStr = data.date || '';
        if (data.time) dateTimeStr += ` ${data.time}`;
        document.getElementById('res-date-time').value = dateTimeStr.trim();
        document.getElementById('res-vkn').value = data.customer_tax_id || '';
        document.getElementById('res-customer-name').value = data.customer_title || data.customer_name || data.customer || '';
        document.getElementById('res-method').textContent = data._extraction_method || '-';
        document.getElementById('res-subtotal').value = data.subtotal || '';
        
        const discountCard = document.getElementById('discount-card');
        if (parseMoney(data.discount_amount) > 0) {
            document.getElementById('res-discount').value = data.discount_amount || '';
            discountCard.classList.remove('hidden');
        } else {
            discountCard.classList.add('hidden');
        }
        
        document.getElementById('res-total').value = data.total_amount || '';
        
        const notesCard = document.getElementById('notes-card');
        if (notesCard && data.notes && data.notes.trim() !== '') {
            document.getElementById('res-notes').textContent = data.notes.trim();
            notesCard.classList.remove('hidden');
        } else if (notesCard) {
            notesCard.classList.add('hidden');
        }
        
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
            items.forEach((item, idx) => {
                const tr = document.createElement('tr');
                
                const appendInputCell = (row, value, field, cellClass = '') => {
                    const td = document.createElement('td');
                    if (cellClass) td.className = cellClass;
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.className = 'edit-input cell-input';
                    input.setAttribute('data-key', `item-${idx}-${field}`);
                    input.value = value == null ? '' : String(value);
                    td.appendChild(input);
                    row.appendChild(td);
                };

                appendInputCell(tr, item.code, 'code');
                appendInputCell(tr, item.description, 'description', 'item-description-cell');
                
                const tdSerials = document.createElement('td');
                tdSerials.className = 'serial-numbers-cell';
                const inputSerials = document.createElement('input');
                inputSerials.type = 'text';
                inputSerials.className = 'edit-input cell-input';
                inputSerials.setAttribute('data-key', `item-${idx}-serial_numbers`);
                inputSerials.value = (item.serial_numbers || []).join(', ');
                tdSerials.appendChild(inputSerials);
                tr.appendChild(tdSerials);
                
                appendInputCell(tr, item.quantity, 'quantity');
                appendInputCell(tr, item.unit_price, 'unit_price');
                appendInputCell(tr, item.tax_rate, 'tax_rate');
                appendInputCell(tr, item.tax_amount || '', 'tax_amount');
                appendInputCell(tr, item.total_price, 'total_price');
                
                tbody.appendChild(tr);
            });
        }
        
        updateValidationUI({ is_valid: result.is_valid, errors: result.errors || [], invoice_data: data });
    }
    
    function updateValidationUI(result) {
        const badge = document.getElementById('validation-badge');
        const sendBtn = document.getElementById('send-draft-btn');
        sendBtn.disabled = false;
        
        const data = result.invoice_data || {};
        
        if (result.is_valid) {
            badge.textContent = 'GEÇERLİ';
            badge.className = 'badge valid';
            document.getElementById('portal-btn').classList.remove('hidden');
            sendBtn.classList.remove('hidden');
            document.getElementById('error-box').classList.add('hidden');
        } else {
            badge.textContent = 'HATALI';
            badge.className = 'badge error';
            sendBtn.classList.add('hidden');
            
            const errorBox = document.getElementById('error-box');
            if (result.errors && result.errors.length > 0) {
                errorBox.innerHTML = '<div style="display: flex; align-items: center; margin-bottom: 0.5rem;"><svg style="width: 24px; height: 24px; margin-right: 8px; color: #f87171;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><strong style="font-size: 1.1rem;">Lütfen faturadaki şu eksik veya hataları giderin:</strong></div>' + 
                '<ul style="margin-left: 2rem; list-style-type: disc;">' + result.errors.map(e => `<li style="margin-bottom: 0.25rem;">${escapeHtml(e)}</li>`).join('') + '</ul>';
                errorBox.classList.remove('hidden');
            } else {
                errorBox.classList.add('hidden');
            }
        }
        
        updateInputIfNotFocused('res-invoice-no', data.invoice_no);
        let dateTimeStr = data.date || '';
        if (data.time) dateTimeStr += ` ${data.time}`;
        updateInputIfNotFocused('res-date-time', dateTimeStr.trim());
        updateInputIfNotFocused('res-vkn', data.customer_tax_id);
        updateInputIfNotFocused('res-customer-name', data.customer_title || data.customer_name);
        updateInputIfNotFocused('res-subtotal', data.subtotal);
        updateInputIfNotFocused('res-discount', data.discount_amount);
        updateInputIfNotFocused('res-total', data.total_amount);
        
        const getSymbol = (currency) => {
            if (currency === 'USD') return '$';
            if (currency === 'EUR') return '€';
            if (currency === 'GBP') return '£';
            return '₺';
        };
        const sym = getSymbol(data.currency);
        
        const breakdownDiv = document.getElementById('res-tax-breakdown');
        if (breakdownDiv) {
            breakdownDiv.innerHTML = '';
            if (data.tax_amount) {
                breakdownDiv.textContent = `${sym}${data.tax_amount}`;
            } else {
                breakdownDiv.textContent = '-';
            }
        }
        
        // Update item inputs if they exist
        if (data.items && data.items.length > 0) {
            data.items.forEach((item, idx) => {
                updateInputIfNotFocused(`item-${idx}-code`, item.code);
                updateInputIfNotFocused(`item-${idx}-description`, item.description);
                updateInputIfNotFocused(`item-${idx}-serial_numbers`, (item.serial_numbers || []).join(', '));
                updateInputIfNotFocused(`item-${idx}-quantity`, item.quantity);
                updateInputIfNotFocused(`item-${idx}-unit_price`, item.unit_price);
                updateInputIfNotFocused(`item-${idx}-tax_rate`, item.tax_rate);
                updateInputIfNotFocused(`item-${idx}-tax_amount`, item.tax_amount);
                updateInputIfNotFocused(`item-${idx}-total_price`, item.total_price);
            });
        }
    }
    
    async function runUyumsoftAction() {
        if (!currentInvoiceData) return;
        const capturedUploadId = currentUploadId;
        const sendBtn = document.getElementById('send-draft-btn');
        sendBtn.disabled = true;
        
        const statusBox = document.getElementById('api-status-box');
        const action = 'draft';
        const actionLabel = 'Taslak Oluştur';
        statusBox.classList.remove('hidden');
        statusBox.style.backgroundColor = '#3b82f6';
        statusBox.style.color = '#fff';
        statusBox.innerHTML = `<div class="spinner" style="width:20px;height:20px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:10px;"></div> ${actionLabel} çalışıyor...`;
        
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
            const rowData = Array.from(tr.cells, cell =>
                csvCell(cell.querySelector("input") ? cell.querySelector("input").value : (cell.dataset.csvValue !== undefined ? cell.dataset.csvValue : cell.textContent))
            );
            rows.push(rowData.join(','));
        }
        
        rows.push('');
        rows.push(['Ara Toplam', '', '', '', '', '', '', document.getElementById('res-subtotal').value].map(csvCell).join(','));
        rows.push(['Genel Toplam', '', '', '', '', '', '', document.getElementById('res-total').value].map(csvCell).join(','));
        
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
