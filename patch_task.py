import os

with open(r'C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\task.md', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('- [ ]', '- [x]')

with open(r'C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\task.md', 'w', encoding='utf-8') as f:
    f.write(text)
