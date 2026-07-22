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
        
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN uyumsoft_document_id TEXT')
    except sqlite3.OperationalError:
        pass # Column already exists
        
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN uyumsoft_environment TEXT')
        cursor.execute('ALTER TABLE invoices ADD COLUMN uyumsoft_status TEXT')
        cursor.execute('ALTER TABLE invoices ADD COLUMN uyumsoft_status_code TEXT')
        cursor.execute('ALTER TABLE invoices ADD COLUMN uyumsoft_message TEXT')
        cursor.execute('ALTER TABLE invoices ADD COLUMN uyumsoft_checked_at TIMESTAMP')
    except sqlite3.OperationalError:
        pass # Columns already exist
        
    conn.commit()
    conn.close()

def parse_turkish_float(val):
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    # Remove thousands separators (dots) and replace decimal comma with dot
    val_str = str(val).replace('.', '').replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def save_invoice(invoice_data: dict, is_valid: bool = True, uyumsoft_document_id: str = None, uyumsoft_environment: str = None, uyumsoft_status: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    status = "Taslak" if is_valid else "HATALI"
    
    total_amount = parse_turkish_float(invoice_data.get('total_amount'))
    currency = str(invoice_data.get('currency') or 'TRY').upper()
    
    amount_try = total_amount
    if currency != 'TRY':
        exchange_rate = invoice_data.get('exchange_rate')
        if exchange_rate:
            rate = parse_turkish_float(exchange_rate)
            if rate > 0:
                amount_try = total_amount * rate
    
    cursor.execute('''
        INSERT INTO invoices (
            invoice_no, date, customer_name, customer_tax_id, 
            total_amount, amount_try, currency, status, raw_json, created_at,
            uyumsoft_document_id, uyumsoft_environment, uyumsoft_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        uyumsoft_document_id,
        uyumsoft_environment,
        uyumsoft_status
    ))
    
    conn.commit()
    conn.close()

def update_uyumsoft_status_by_id(invoice_id: int, status: str, status_code: str = None, message: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE invoices 
        SET uyumsoft_status = ?, uyumsoft_status_code = ?, uyumsoft_message = ?, uyumsoft_checked_at = ? 
        WHERE id = ?
    ''', (status, status_code, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), invoice_id))
    conn.commit()
    conn.close()

def get_uyumsoft_metadata(invoice_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT uyumsoft_document_id, uyumsoft_environment FROM invoices WHERE id = ?', (invoice_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_dashboard_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Total revenue & count (only for non-error invoices)
    cursor.execute('''
        SELECT 
            SUM(amount_try) as total_revenue,
            COUNT(*) as total_count
        FROM invoices
        WHERE status != 'HATALI'
    ''')
    row = cursor.fetchone()
    total_revenue = float(row['total_revenue'] or 0.0)
    total_count = int(row['total_count'] or 0)
    
    # 2. Revenue trend by month
    cursor.execute('''
        SELECT 
            CASE 
                WHEN date LIKE '____-__-__' THEN substr(date, 1, 7)
                ELSE substr(created_at, 1, 7)
            END as month,
            SUM(amount_try) as monthly_revenue,
            COUNT(*) as monthly_count
        FROM invoices
        WHERE status != 'HATALI'
        GROUP BY month
        ORDER BY month ASC
    ''')
    monthly_data = [dict(r) for r in cursor.fetchall()]
    
    # 3. Top customers
    cursor.execute('''
        SELECT 
            COALESCE(NULLIF(customer_name, ''), 'Bilinmeyen Müşteri') as customer_name,
            SUM(amount_try) as total_revenue
        FROM invoices
        WHERE status != 'HATALI'
        GROUP BY customer_name
        ORDER BY total_revenue DESC
        LIMIT 5
    ''')
    top_customers = [dict(r) for r in cursor.fetchall()]

    # 4. Status distribution
    cursor.execute('''
        SELECT 
            status,
            COUNT(*) as count
        FROM invoices
        GROUP BY status
    ''')
    status_distribution = [dict(r) for r in cursor.fetchall()]

    # 5. Currency distribution
    cursor.execute('''
        SELECT 
            COALESCE(NULLIF(currency, ''), 'TRY') as currency,
            SUM(total_amount) as total
        FROM invoices
        WHERE status != 'HATALI'
        GROUP BY currency
    ''')
    currency_distribution = [dict(r) for r in cursor.fetchall()]

    # 6. Tax vs Subtotal Trend
    cursor.execute('''
        SELECT 
            CASE 
                WHEN date LIKE '____-__-__' THEN substr(date, 1, 7)
                ELSE substr(created_at, 1, 7)
            END as month,
            SUM(CAST(json_extract(raw_json, '$.tax_amount') AS REAL)) as total_tax,
            SUM(CAST(json_extract(raw_json, '$.subtotal') AS REAL)) as total_subtotal
        FROM invoices
        WHERE status != 'HATALI' AND raw_json IS NOT NULL
        GROUP BY month
        ORDER BY month ASC
    ''')
    tax_vs_subtotal = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return {
        "total_revenue": total_revenue,
        "total_count": total_count,
        "trend": monthly_data,
        "top_customers": top_customers,
        "status_distribution": status_distribution,
        "currency_distribution": currency_distribution,
        "tax_vs_subtotal": tax_vs_subtotal
    }

def get_paginated_invoices(page: int = 1, limit: int = 20, search_query: str = None, date_filter: str = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    offset = (page - 1) * limit
    
    where_clauses = []
    params = []
    
    if search_query:
        search_term = f"%{search_query}%"
        where_clauses.append("(customer_name LIKE ? OR invoice_no LIKE ? OR customer_tax_id LIKE ?)")
        params.extend([search_term, search_term, search_term])
        
    if date_filter == 'this_month':
        # SQLite modifier 'start of month' goes to the 1st of the current month
        where_clauses.append("created_at >= date('now', 'start of month')")
    elif date_filter == 'last_month':
        where_clauses.append("created_at >= date('now', '-1 month', 'start of month') AND created_at < date('now', 'start of month')")
    elif date_filter == 'this_year':
        where_clauses.append("created_at >= date('now', 'start of year')")
        
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
        
    cursor.execute(f'SELECT COUNT(*) as total FROM invoices {where_sql}', params)
    total_items = cursor.fetchone()['total']
    
    query = f'''
        SELECT id, invoice_no, date, customer_name, customer_tax_id, 
               total_amount, amount_try, currency, status, created_at, 
               uyumsoft_document_id, uyumsoft_environment, uyumsoft_status, uyumsoft_message, uyumsoft_checked_at
        FROM invoices 
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    '''
    cursor.execute(query, params + [limit, offset])
    
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


