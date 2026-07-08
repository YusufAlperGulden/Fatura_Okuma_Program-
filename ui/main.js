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
                
                // Auto-send to Uyumsoft if valid
                if (result.is_valid) {
                    document.getElementById('uyumsoft-action').value = 'draft';
                    document.getElementById('api-send-btn').click();
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
            document.getElementById('download-btn').classList.remove('hidden');
            document.getElementById('api-send-btn').classList.remove('hidden');
            document.getElementById('uyumsoft-controls').classList.remove('hidden');
        } else {
            badge.textContent = 'HATALI';
            badge.className = 'badge error';
            
            const errorBox = document.getElementById('error-box');
            errorBox.innerHTML = '<strong>Hatalar Bulundu:</strong><br>' + result.errors.join('<br>');
            errorBox.classList.remove('hidden');
        }
        
        // Ensure data exists before accessing properties
        const data = result.data || {};
        
        // Update summary cards
        // IMPORTANT: Mapped to exactly what extractors output!
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
    
    // Download logic
    document.getElementById('download-btn').addEventListener('click', () => {
        window.location.href = '/download_excel';
    });

    // API Send logic
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
});
