import os

with open("ui/app.js", "r", encoding="utf-8") as f:
    text = f.read()

# Replace window.fetch to inject Auth header and handle 401
auth_interceptor = '''
    // Intercept fetch to add auth header and handle 401
    const originalFetch = window.fetch;
    window.fetch = async function() {
        let [resource, config] = arguments;
        if (!config) {
            config = {};
        }
        if (!config.headers) {
            config.headers = {};
        }
        const appPassword = localStorage.getItem('appPassword') || '';
        if (appPassword) {
            config.headers['x-app-password'] = appPassword;
        }
        
        try {
            const response = await originalFetch(resource, config);
            if (response.status === 401) {
                document.getElementById('auth-modal').classList.remove('hidden');
                Toastify({
                    text: "Yetkisiz Erişim! Lütfen Uygulama Şifrenizi girin.",
                    duration: 3000,
                    style: { background: "var(--fire)" }
                }).showToast();
                // Optionally return a dummy rejected promise to stop execution
                return Promise.reject("401 Unauthorized");
            }
            return response;
        } catch (error) {
            throw error;
        }
    };
    
    document.getElementById('auth-save-btn').addEventListener('click', () => {
        const pass = document.getElementById('app-password').value;
        if (pass) {
            localStorage.setItem('appPassword', pass);
            document.getElementById('auth-modal').classList.add('hidden');
            Toastify({
                text: "Şifre Kaydedildi. Lütfen işleminizi tekrarlayın.",
                duration: 3000,
                style: { background: "var(--aurora)" }
            }).showToast();
        }
    });

    // Check auth on load
    if (!localStorage.getItem('appPassword')) {
        document.getElementById('auth-modal').classList.remove('hidden');
    }
'''

if "const originalFetch" not in text:
    text = text.replace("document.addEventListener('DOMContentLoaded', () => {\n", "document.addEventListener('DOMContentLoaded', () => {\n" + auth_interceptor)

with open("ui/app.js", "w", encoding="utf-8") as f:
    f.write(text)
