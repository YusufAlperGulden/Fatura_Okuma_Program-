import os
import sqlite3
import pytest
import json
from datetime import datetime

os.environ["TESTING"] = "1"
import database

import tempfile

temp_db_fd, temp_db_path = tempfile.mkstemp(suffix='.db')
database.DB_PATH = temp_db_path

@pytest.fixture(autouse=True)
def setup_db():
    database.init_db()
    # Clear tables before each test
    conn = sqlite3.connect(database.DB_PATH)
    conn.execute("DELETE FROM invoices")
    conn.commit()
    conn.close()
    yield

def teardown_module(module):
    os.close(temp_db_fd)
    try:
        os.remove(temp_db_path)
    except:
        pass

def test_save_invoice_and_dashboard():
    # Save a valid TRY invoice
    inv1 = {
        "invoice_no": "INV-001",
        "date": "2026-07-22",
        "customer_name": "Test Company",
        "total_amount": 1000.0,
        "currency": "TRY"
    }
    database.save_invoice(inv1, is_valid=True)
    
    # Save a valid USD invoice
    inv2 = {
        "invoice_no": "INV-002",
        "date": "2026-07-22",
        "customer_name": "US Company",
        "total_amount": 100.0,
        "currency": "USD",
        "exchange_rate": 30.5
    }
    database.save_invoice(inv2, is_valid=True)
    
    # Save an invalid invoice
    inv3 = {
        "invoice_no": "INV-003",
        "date": "2026-07-22",
        "customer_name": "Bad Company",
        "total_amount": 5000.0,
        "currency": "TRY"
    }
    database.save_invoice(inv3, is_valid=False)
    
    # Check dashboard stats
    stats = database.get_dashboard_stats()
    
    # Total revenue should be 1000 + (100 * 30.5) = 4050
    # It should NOT include inv3 because it's HATALI
    assert stats["total_count"] == 2
    assert stats["total_revenue"] == 4050.0
    
    # Check trend
    assert len(stats["trend"]) == 1
    assert stats["trend"][0]["month"] == "2026-07"
    assert stats["trend"][0]["monthly_revenue"] == 4050.0
    assert stats["trend"][0]["monthly_count"] == 2

def test_missing_or_bad_data_graceful():
    inv_bad = {
        "invoice_no": "INV-004",
        "total_amount": None,
        "currency": "EUR",
        "exchange_rate": "invalid"
    }
    # Should not crash, amount_try should fallback to 0.0
    database.save_invoice(inv_bad, is_valid=True)
    
    stats = database.get_dashboard_stats()
    assert stats["total_revenue"] == 0.0
    
    # Test pagination
    paginated = database.get_paginated_invoices(1, 10)
    assert paginated["total"] == 1
    assert len(paginated["items"]) == 1
    assert paginated["items"][0]["amount_try"] == 0.0

def test_pagination():
    # Insert 25 invoices
    for i in range(25):
        database.save_invoice({"invoice_no": f"INV-{i}", "total_amount": 100, "currency": "TRY"}, is_valid=True)
        
    page1 = database.get_paginated_invoices(page=1, limit=10)
    assert page1["total"] == 25
    assert len(page1["items"]) == 10
    assert page1["total_pages"] == 3
    
    page3 = database.get_paginated_invoices(page=3, limit=10)
    assert len(page3["items"]) == 5
