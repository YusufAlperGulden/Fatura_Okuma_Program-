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
    let pdfObjectUrl = null;

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
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
        
        if (file.type === 'application/pdf' || file.type.startsWith('image/')) {
            pdfObjectUrl = URL.createObjectURL(file);
            document.getElementById('pdf-iframe').src = pdfObjectUrl;
            document.getElementById('pdf-viewer-section').classList.remove('hidden');
            document.getElementById('split-container').classList.add('split-active');
        } else {
            document.getElementById('pdf-viewer-section').classList.add('hidden');
            document.getElementById('split-container').classList.remove('split-active');
        }

        dropZone.classList.add('hidden');
        loading.classList.remove('hidden');
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
                currentAbortController.abort('user_cancelled');
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
            
            loading.classList.add('hidden');
            dropZone.classList.remove('hidden');
            
            if (response.ok) {
                currentInvoiceData = result.data;
                showResults(result);
                
                // Automated UI Checklist Flow
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
                    
                    checklist.innerHTML += `<li class="pending">Uyumsoft islemi otomatik baslatildi.</li>`;
                    runUyumsoftAction();
                } else {
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Fatura okundu</li>`;
                    checklist.innerHTML += `<li class="error"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg> Fatura okundu ancak aktarım durduruldu.</li>`;
                    
                  if (!result.is_valid && result.errors && result.errors.length > 0) {
                    const errorBox = document.getElementById('error-box');
                    errorBox.innerHTML = '<div style="display: flex; align-items: center; margin-bottom: 0.5rem;"><svg style="width: 24px; height: 24px; margin-right: 8px; color: #f87171;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><strong style="font-size: 1.1rem;">Lütfen faturadaki şu eksik veya hataları giderin:</strong></div>' + 
                    '<ul style="margin-left: 2rem; list-style-type: disc;">' + result.errors.map(e => `<li style="margin-bottom: 0.25rem;">${e}</li>`).join('') + '</ul>';
                    errorBox.classList.remove('hidden');
                }
                }
            } else {
                showError("Sunucu Hatası: " + (result.detail || "Bilinmeyen hata"));
            }
            
        } catch (error) {
            loading.classList.add('hidden');
            dropZone.classList.remove('hidden');
            
            if (error.name === 'AbortError') {
                showError("İşlem sizin tarafınızdan iptal edildi.");
            } else {
                showError("Bağlantı hatası: " + error.message);
            }
        } finally {
            currentAbortController = null;
        }
    }
    
    function showResults(result) {
        resultsSection.classList.remove('hidden');
        document.getElementById('split-container').classList.remove('hidden');
        
        // Badge
        const badge = document.getElementById('validation-badge');
        if (result.is_valid) {
            badge.textContent = 'GEÇERLİ';
            badge.className = 'badge valid';
            document.getElementById('portal-btn').classList.remove('hidden');
        } else {
            badge.textContent = 'HATALI';
            badge.className = 'badge error';
        }
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
        
        // Update summary cards
        document.getElementById('res-invoice-no').textContent = data.invoice_no || '-';
        let dateTimeStr = data.date || '-';
        if (data.time) {
            dateTimeStr += ` ${data.time}`;
        }
        document.getElementById('res-date-time').textContent = dateTimeStr;
        document.getElementById('res-vkn').textContent = data.customer_tax_id || '-';
        const customerName = data.customer_title || data.customer_name || data.customer || '';
        if (customerName) {
            document.getElementById('res-customer-name').textContent = customerName;
        } else {
            document.getElementById('res-customer-name').textContent = '-';
        }
        document.getElementById('res-method').textContent = data._extraction_method || '-';
        document.getElementById('res-subtotal').textContent = data.subtotal ? `${sym}${data.subtotal}` : '-';
        
        const discountCard = document.getElementById('discount-card');
        if (data.discount_amount && parseFloat(data.discount_amount.replace(/\./g, '').replace(',', '.')) > 0) {
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
                const parseMoney = (val) => {
                    if (!val) return 0;
                    let str = String(val).replace(/[^0-9.,-]/g, '');
                    if (str.includes(',') && str.includes('.')) {
                        if (str.lastIndexOf(',') > str.lastIndexOf('.')) {
                            str = str.replace(/\./g, '').replace(',', '.');
                        } else {
                            str = str.replace(/,/g, '');
                        }
                    } else if (str.includes(',')) {
                        const parts = str.split(',');
                        if (parts.length === 2 && parts[1].length !== 3) {
                            str = str.replace(',', '.');
                        } else if (parts.length > 1 && parts.slice(1).every(p => p.length === 3)) {
                            str = str.replace(/,/g, '');
                        } else {
                            str = str.replace(',', '.');
                        }
                    } else if (str.includes('.')) {
                        const parts = str.split('.');
                        if (parts.length > 1 && parts.slice(1).every(p => p.length === 3)) {
                            str = str.replace(/\./g, '');
                        }
                    }
                    return parseFloat(str) || 0;
                };

                const gSub = parseMoney(data.subtotal);
                const gTax = parseMoney(data.tax_amount);
                const globalRate = (gTax && gSub) ? (gTax / gSub * 100) : 0;
                
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
                breakdownDiv.innerHTML = data.tax_amount ? `${sym}${data.tax_amount}` : '-';
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
        
        // Render items
        const tbody = document.querySelector('#items-table tbody');
        tbody.innerHTML = '';
        
        const items = data.items || [];
        if (items.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="5" style="text-align:center; color: var(--text-secondary)">Herhangi bir kalem bulunamadı.</td>`;
            tbody.appendChild(tr);
        } else {
            items.forEach(item => {
                const tr = document.createElement('tr');
                let rate = item.tax_rate !== undefined && item.tax_rate !== null && String(item.tax_rate).trim() !== "" ? String(item.tax_rate).replace('%', '').trim() : Math.round(globalRate);
                let formattedRate = `%${rate}`;
                
                let parseVal = (val) => {
                    if (!val) return 0;
                    let str = String(val).replace(/[^0-9.,-]/g, '');
                    if (str.includes(',') && str.includes('.')) {
                        if (str.lastIndexOf(',') > str.lastIndexOf('.')) {
                            str = str.replace(/\./g, '').replace(',', '.');
                        } else {
                            str = str.replace(/,/g, '');
                        }
                    } else if (str.includes(',')) {
                        const pts = str.split(',');
                        if (pts.length === 2 && pts[1].length !== 3) {
                            str = str.replace(',', '.');
                        } else if (pts.length > 1 && pts.slice(1).every(p => p.length === 3)) {
                            str = str.replace(/,/g, '');
                        } else {
                            str = str.replace(',', '.');
                        }
                    } else if (str.includes('.')) {
                        const pts = str.split('.');
                        if (pts.length > 1 && pts.slice(1).every(p => p.length === 3)) {
                            str = str.replace(/\./g, '');
                        }
                    }
                    return parseFloat(str) || 0;
                };

                let lineTotal = item.total_price ? parseVal(item.total_price) : (item.unit_price && item.quantity ? parseVal(item.unit_price) * parseVal(item.quantity) : 0);
                let lineTax = (lineTotal * parseFloat(rate) / 100);
                let formattedTax = lineTax > 0 ? `${sym}${lineTax.toLocaleString('tr-TR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : '-';

                tr.innerHTML = `
                    <td>${item.code || '-'}</td>
                    <td>${item.description || '-'}</td>
                    <td>${item.quantity || '-'}</td>
                    <td>${item.unit_price ? `${sym}${item.unit_price}` : '-'}</td>
                    <td>${formattedRate}</td>
                    <td>${formattedTax}</td>
                    <td>${item.total_price ? `${sym}${item.total_price}` : '-'}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    }
    
    // Uyumsoft send logic: used automatically after validation.
    async function runUyumsoftAction() {
        if (!currentInvoiceData) return;
        
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
                statusBox.style.backgroundColor = '#059669';
                statusBox.innerHTML = `✅ ${escapeHtml(result.message)} (HTTP ${escapeHtml(result.response_code)})`;
                
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
                statusBox.style.backgroundColor = '#dc2626';
                statusBox.innerHTML = `❌ Hata: ${escapeHtml(result.message)}${details ? ` <br> <small>${escapeHtml(details)}</small>` : ''}`;
            }
        } catch (error) {
            statusBox.style.backgroundColor = '#dc2626';
            statusBox.innerHTML = `❌ Bağlantı Hatası: ${error.message}`;
        }
    }

    document.getElementById('portal-btn').addEventListener('click', openUyumsoftPortal);

    document.getElementById('csv-btn').addEventListener('click', () => {
        if (!currentInvoiceData || !currentInvoiceData.items) return;
        
        const headers = ['Urun Kodu', 'Urun Aciklamasi', 'Miktar', 'Birim Fiyat', 'KDV Orani', 'KDV Tutari', 'Satir Toplami'];
        const rows = [headers.join(',')];
        
        const tbody = document.querySelector('#items-table tbody');
        for (const tr of tbody.rows) {
            if (tr.cells.length === 1) continue; // Skip empty message
            const rowData = [];
            for (const cell of tr.cells) {
                let text = cell.textContent.replace(/"/g, '""');
                rowData.push(`"${text}"`);
            }
            rows.push(rowData.join(','));
        }
        
        rows.push('');
        rows.push(`"Ara Toplam",,"","","","","${document.getElementById('res-subtotal').textContent}"`);
        rows.push(`"Genel Toplam",,"","","","","${document.getElementById('res-total').textContent}"`);
        
        const csvContent = "\uFEFF" + rows.join('\n');
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
        if (pdfSection.classList.contains('hidden')) {
            pdfSection.classList.remove('hidden');
            splitContainer.classList.add('split-active');
        } else {
            pdfSection.classList.add('hidden');
            splitContainer.classList.remove('split-active');
        }
    });
});
