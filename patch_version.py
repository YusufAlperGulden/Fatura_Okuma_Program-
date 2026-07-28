import os

with open("ui/index.html", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace("v86", "v87")

with open("ui/index.html", "w", encoding="utf-8") as f:
    f.write(text)
