import re

with open(r'C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\task.md', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('- [ ] Modify extractors/ai_extractor.py', '- [x] Modify extractors/ai_extractor.py')
text = text.replace('- [ ] Verify the application runs', '- [x] Verify the application runs')

with open(r'C:\Users\stajyer\.gemini\antigravity\brain\5c3c6925-cc04-4e2f-ad05-dba30c96b3a4\task.md', 'w', encoding='utf-8') as f:
    f.write(text)
