import os

with open("ui/index.html", "r", encoding="utf-8") as f:
    text = f.read()

replacement = '''    <!-- Auth Modal -->
    <div id="auth-modal" class="modal hidden">
        <div class="modal-content" style="max-width: 400px; padding: 2rem; margin: auto;">
            <h2 style="margin-top: 0; margin-bottom: 1.5rem; text-align: center;">Güvenli Giriş</h2>
            <div style="margin-bottom: 1.5rem; text-align: left;">
                <label for="app-password" style="display: block; margin-bottom: 0.5rem; font-weight: 600;">Uygulama Şifresi</label>
                <input type="password" id="app-password" placeholder="Şifreniz" style="width: 100%; padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 8px; background: var(--input-bg); color: var(--text-primary);">
            </div>
            <div class="modal-actions" style="display: flex; justify-content: flex-end; gap: 1rem;">
                <button id="auth-save-btn" class="primary-btn">Giriş Yap</button>
            </div>
        </div>
    </div>'''

import re
text = re.sub(r'<!-- Credentials Modal -->.*?</div>\s+</div>', replacement, text, flags=re.DOTALL)

with open("ui/index.html", "w", encoding="utf-8") as f:
    f.write(text)
