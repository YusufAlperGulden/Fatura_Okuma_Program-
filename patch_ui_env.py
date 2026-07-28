import re
with open("ui/index.html", "r", encoding="utf-8") as f:
    text = f.read()

# Find and remove the environment select container
text = re.sub(r'<div style="margin-bottom: 1rem;">\s*<label for="uyumsoft-env".*?</select>\s*</div>', '', text, flags=re.DOTALL)

with open("ui/index.html", "w", encoding="utf-8") as f:
    f.write(text)
