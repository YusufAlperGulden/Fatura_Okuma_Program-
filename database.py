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
            amount_try REAL,
            currency TEXT,
            status TEXT,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Run migration to add amount_try if it doesn't exist
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN amount_try REAL DEFAULT 0.0')
    except sqlite3.OperationalError:
        pass # Column already exists
        
    conn.commit()
    conn.close()

def save_invoice(invoice_data: dict, is_valid: bool = True):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    status = "GÖNDERİLDİ" if is_valid else "HATALI"
    
    total_amount = float(invoice_data.get('total_amount') or 0.0)
    currency = str(invoice_data.get('currency') or 'TRY').upper()
    
    amount_try = total_amount
    if currency != 'TRY':
        exchange_rate = invoice_data.get('exchange_rate')
        if exchange_rate:
            try:
                rate = float(exchange_rate)
                if rate > 0:
                    amount_try = total_amount * rate
            except (ValueError, TypeError):
                pass
    
    cursor.execute('''
        INSERT INTO invoices (
            invoice_no, date, customer_name, customer_tax_id, 
            total_amount, amount_try, currency, status, raw_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        invoice_data.get('invoice_no', ''),
        invoice_data.get('date', ''),
        invoice_data.get('customer_name', ''),
        invoice_data.get('customer_tax_id', ''),
        total_amount,
        amount_try,
        currency,
        status,
        json.dumps(invoice_data, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    
    conn.commit()
    conn.close()

def get_dashboard_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Total revenue & count (only for GÖNDERİLDİ)
    cursor.execute('''
        SELECT 
            SUM(amount_try) as total_revenue,
            COUNT(*) as total_count
        FROM invoices
        WHERE status = 'GÖNDERİLDİ'
    ''')
    row = cursor.fetchone()
    total_revenue = float(row['total_revenue'] or 0.0)
    total_count = int(row['total_count'] or 0)
    
    # 2. Revenue trend by month (only for GÖNDERİLDİ)
    # Using substr(date, 1, 7) assuming date format like YYYY-MM-DD
    # If date is invalid or missing, we could fallback to created_at
    cursor.execute('''
        SELECT 
            CASE 
                WHEN date LIKE '____-__-__' THEN substr(date, 1, 7)
                ELSE substr(created_at, 1, 7)
            END as month,
            SUM(amount_try) as monthly_revenue,
            COUNT(*) as monthly_count
        FROM invoices
        WHERE status = 'GÖNDERİLDİ'
        GROUP BY month
        ORDER BY month ASC
    ''')
    monthly_data = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return {
        "total_revenue": total_revenue,
        "total_count": total_count,
        "trend": monthly_data
    }

def get_paginated_invoices(page: int = 1, limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    offset = (page - 1) * limit
    
    cursor.execute('SELECT COUNT(*) as total FROM invoices')
    total_items = cursor.fetchone()['total']
    
    cursor.execute('''
        SELECT id, invoice_no, date, customer_name, customer_tax_id, 
               total_amount, amount_try, currency, status, created_at
        FROM invoices 
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset))
    
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "items": rows,
        "total": total_items,
        "page": page,
        "limit": limit,
        "total_pages": (total_items + limit - 1) // limit
    }

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
