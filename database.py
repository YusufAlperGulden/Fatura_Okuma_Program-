import sqlite3
import json
import os
from datetime import datetime

DB_DIR = "db"
DB_PATH = os.path.join(DB_DIR, "invoices.db")

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT,
            date TEXT,
            customer_name TEXT,
            customer_tax_id TEXT,
            total_amount REAL,
            currency TEXT,
            status TEXT,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_invoice(invoice_data: dict, is_valid: bool):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    status = "GEÇERLİ" if is_valid else "HATALI"
    
    cursor.execute('''
        INSERT INTO invoices (
            invoice_no, date, customer_name, customer_tax_id, 
            total_amount, currency, status, raw_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        invoice_data.get('invoice_no', ''),
        invoice_data.get('date', ''),
        invoice_data.get('customer_name', ''),
        invoice_data.get('customer_tax_id', ''),
        invoice_data.get('total_amount', 0.0),
        invoice_data.get('currency', ''),
        status,
        json.dumps(invoice_data, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    
    conn.commit()
    conn.close()

def get_invoices(search_query: str = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if search_query:
        query = f"%{search_query}%"
        cursor.execute('''
            SELECT * FROM invoices 
            WHERE invoice_no LIKE ? OR customer_name LIKE ? OR customer_tax_id LIKE ?
            ORDER BY created_at DESC
        ''', (query, query, query))
    else:
        cursor.execute('SELECT * FROM invoices ORDER BY created_at DESC')
        
    rows = cursor.fetchall()
    conn.close()
    
    # Return raw_json as a parsed dict for easy API usage
    results = []
    for row in rows:
        item = dict(row)
        try:
            item['raw_json'] = json.loads(item['raw_json'])
        except:
            item['raw_json'] = {}
        results.append(item)
    return results
