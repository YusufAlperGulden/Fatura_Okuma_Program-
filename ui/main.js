document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const loading = document.getElementById('loading');
    const resultsSection = document.getElementById('results-section');
    
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

    async function handleFile(file) {
        // Reset UI
        dropZone.classList.add('hidden');
        loading.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        document.getElementById('error-box').classList.add('hidden');
        document.getElementById('download-btn').classList.add('hidden');
        document.getElementById('api-send-btn').classList.add('hidden');
        document.getElementById('uyumsoft-controls').classList.add('hidden');
        document.getElementById('api-status-box').classList.add('hidden');
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            // Because we are serving from /ui, the API endpoint is at /upload
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
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
                    
                    // Simulate UI matching checks (per user request)
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Cari eşleşti</li>`;
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Stok/Hizmet eşleşti</li>`;
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Depo eşleşti</li>`;
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Mükerrer değil</li>`;
                    
                    const progressLi = document.createElement('li');
                    progressLi.className = 'pending';
                    progressLi.innerHTML = `<div class="spinner" style="width:16px;height:16px;border-width:2px;margin:0;"></div> → Uyumsoft Taslak oluşturuluyor...`;
                    checklist.appendChild(progressLi);
                    
                    // Auto-send to Uyumsoft
                    autoSendToUyumsoft(currentInvoiceData, progressLi);
                } else {
                    checklist.innerHTML += `<li class="success"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Fatura okundu</li>`;
                    checklist.innerHTML += `<li class="error"><svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg> Fatura okundu ancak aktarım durduruldu.</li>`;
                    
                    const errorBox = document.getElementById('error-box');
                    errorBox.innerHTML = '<strong>Eksikler:</strong><br>' + result.errors.map(e => `- ${e}`).join('<br>');
                    errorBox.classList.remove('hidden');
                }
            } else {
                showError("Sunucu Hatası: " + (result.detail || "Bilinmeyen hata"));
            }
            
        } catch (error) {
            loading.classList.add('hidden');
            dropZone.classList.remove('hidden');
            showError("Bağlantı hatası: " + error.message);
        }
    }
    
    function showResults(result) {
        resultsSection.classList.remove('hidden');
        
        // Badge
        const badge = document.getElementById('validation-badge');
        if (result.is_valid) {
            badge.textContent = 'GEÇERLİ';
            badge.className = 'badge valid';
        } else {
            badge.textContent = 'HATALI';
            badge.className = 'badge error';
        }
        
        // Ensure data exists before accessing properties
        const data = result.data || {};
        
        // Update summary cards
        document.getElementById('res-date').textContent = data.date || '-';
        document.getElementById('res-vkn').textContent = data.customer_tax_id || '-';
        document.getElementById('res-subtotal').textContent = data.subtotal ? `₺${data.subtotal}` : '-';
        document.getElementById('res-tax').textContent = data.tax_amount ? `₺${data.tax_amount}` : '-';
        document.getElementById('res-total').textContent = data.total_amount ? `₺${data.total_amount}` : '-';
        
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
                tr.innerHTML = `
                    <td>${item.code || '-'}</td>
                    <td>${item.description || '-'}</td>
                    <td>${item.quantity || '-'}</td>
                    <td>${item.unit_price ? `₺${item.unit_price}` : '-'}</td>
                    <td>${item.total_price ? `₺${item.total_price}` : '-'}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    }
    
    // Auto Send Logic
    async function autoSendToUyumsoft(invoiceData, progressElement) {
        try {
            const response = await fetch('/send-uyumsoft', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ invoice_data: invoiceData, action: 'draft' })
            });
            
            const result = await response.json();
            
            if (result.success) {
                progressElement.className = 'success';
                progressElement.innerHTML = `<svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Taslak başarıyla oluşturuldu <a href="http://portal-test.uyumsoft.com.tr/Taslak" target="_blank" style="margin-left:10px; color:var(--accent-color); text-decoration:none;">(Portala Git ↗)</a>`;
            } else {
                const details = formatDetails(result.details);
                progressElement.className = 'error';
                progressElement.innerHTML = `<svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg> Taslak oluşturulamadı: ${escapeHtml(result.message)}`;
                
                const errorBox = document.getElementById('error-box');
                errorBox.innerHTML = `<strong>Uyumsoft Hatası:</strong><br>${escapeHtml(result.message)}${details ? `<br><small>${escapeHtml(details)}</small>` : ''}`;
                errorBox.classList.remove('hidden');
            }
        } catch (error) {
            progressElement.className = 'error';
            progressElement.innerHTML = `<svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg> Bağlantı Hatası`;
            
            const errorBox = document.getElementById('error-box');
            errorBox.innerHTML = `<strong>Bağlantı Hatası:</strong><br>${error.message}`;
            errorBox.classList.remove('hidden');
        }
    }

    // Admin Manual Send logic
    document.getElementById('api-send-btn').addEventListener('click', async () => {
        if (!currentInvoiceData) return;
        
        const statusBox = document.getElementById('api-status-box');
        const action = document.getElementById('uyumsoft-action').value;
        const actionLabel = document.getElementById('uyumsoft-action').selectedOptions[0].textContent;
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
            
            const result = await response.json();
            
            if (result.success) {
                statusBox.style.backgroundColor = '#059669';
                statusBox.innerHTML = `✅ ${escapeHtml(result.message)} (HTTP ${escapeHtml(result.response_code)}) 
                <br> <a href="http://portal-test.uyumsoft.com.tr/Taslak" target="_blank" style="display:inline-block; margin-top:10px; padding:5px 10px; background-color:white; color:#059669; text-decoration:none; border-radius:4px; font-weight:bold; font-size:14px;">Uyumsoft Portalına Git ↗</a>`;
            } else {
                const details = formatDetails(result.details);
                statusBox.style.backgroundColor = '#dc2626';
                statusBox.innerHTML = `❌ Hata: ${escapeHtml(result.message)}${details ? ` <br> <small>${escapeHtml(details)}</small>` : ''}`;
            }
        } catch (error) {
            statusBox.style.backgroundColor = '#dc2626';
            statusBox.innerHTML = `❌ Bağlantı Hatası: ${error.message}`;
        }
    });

    // Download logic
    document.getElementById('download-btn').addEventListener('click', () => {
        window.location.href = '/download_excel';
    });

    function showError(msg) {
        const errorBox = document.getElementById('error-box');
        errorBox.textContent = msg;
        errorBox.classList.remove('hidden');
        resultsSection.classList.remove('hidden');
    }
});
