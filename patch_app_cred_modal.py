import re

with open("ui/app.js", "r", encoding="utf-8") as f:
    text = f.read()

# Remove the credentials modal logic block
text = re.sub(r'// Credentials Modal Logic.*?\}', '', text, flags=re.DOTALL)

with open("ui/app.js", "w", encoding="utf-8") as f:
    f.write(text)
