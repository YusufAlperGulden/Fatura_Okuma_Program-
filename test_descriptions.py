# -*- coding: utf-8 -*-
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')
from extractors.pdf_extractor import parse_pdf_invoice
from extractors.pdf_extractor import parse_pdf_invoice

def test_invoice(filename, expected_substring, not_expected_substring=None):
    filepath = rf'C:\Users\tps\Downloads\{filename}'
    print(f'\n--- Testing {filename} ---')
    data = parse_pdf_invoice(filepath)
    if not data.get('items'):
        print('NO ITEMS FOUND!')
        return False
    
    # Just print the descriptions
    success = False
    for item in data['items']:
        desc = item.get('description', '')
        print(f'Description: {desc}')
        if expected_substring in desc:
            if not_expected_substring and not_expected_substring in desc:
                print('FAILED: Found not expected substring!')
            else:
                success = True
    
    if success:
        print('PASS')
    else:
        print('FAIL')

if __name__ == '__main__':
    test_invoice('asyaport.pdf', 'Standart Pvc, 2K Bit')
    test_invoice('taylan.pdf', 'NFC Black Kart', 'Fiyatı Fiyat')
    test_invoice('cahit.pdf', 'NFC Silver Kart', 'DSM GRUP')
    test_invoice('gaye.pdf', 'NFC Ntag213 Silikon')
