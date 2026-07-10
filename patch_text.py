with open('integrators/uyumsoft_api.py', 'r', encoding='utf-8') as f:
    content = f.read()

func = '''
def number_to_turkish_text(amount_str, currency='TRY'):
    try:
        parts = f"{float(amount_str):.2f}".split('.')
    except (ValueError, TypeError):
        return ""
    lira = int(parts[0])
    kurus = int(parts[1]) if len(parts) > 1 else 0

    units = ['', 'Bir', 'İki', 'Üç', 'Dört', 'Beş', 'Altı', 'Yedi', 'Sekiz', 'Dokuz']
    tens = ['', 'On', 'Yirmi', 'Otuz', 'Kırk', 'Elli', 'Altmış', 'Yetmiş', 'Seksen', 'Doksan']

    def read_three(n):
        if n == 0: return ''
        h = n // 100
        t = (n % 100) // 10
        u = n % 10
        res = ''
        if h == 1: res += 'Yüz '
        elif h > 1: res += units[h] + ' Yüz '
        if t > 0: res += tens[t] + ' '
        if u > 0: res += units[u] + ' '
        return res.strip()

    def read_num(n):
        if n == 0: return 'Sıfır'
        groups = []
        while n > 0:
            groups.append(n % 1000)
            n //= 1000
        words = []
        scales = ['', 'Bin', 'Milyon', 'Milyar', 'Trilyon']
        for i, group in enumerate(groups):
            if group == 0: continue
            if i == 1 and group == 1:
                words.append('Bin')
            else:
                words.append(read_three(group) + ((' ' + scales[i]) if i > 0 else ''))
        return ' '.join(reversed(words)).strip()

    currency_names = {
        'TRY': ('Türk Lirası', 'Kuruş'),
        'USD': ('Dolar', 'Cent'),
        'EUR': ('Euro', 'Cent'),
        'GBP': ('İngiliz Sterlini', 'Penny'),
    }
    major, minor = currency_names.get(str(currency).upper(), (str(currency).upper(), 'Kuruş'))

    res = f'Yalnız #{read_num(lira)} {major}'
    if kurus > 0:
        res += f' {read_num(kurus)} {minor}#'
    else:
        res += '#'
    return res

'''
if 'def number_to_turkish_text' not in content:
    content = content.replace('def normalize_currency', func + 'def normalize_currency')
    with open('integrators/uyumsoft_api.py', 'w', encoding='utf-8') as f:
        f.write(content)
