"""
Run this ONCE after replacing backend files.
Safely adds ALL missing columns to your existing database.
Safe to run multiple times - skips already-existing columns.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.db.session import engine
from sqlalchemy import text

def add_col(conn, table, col, typ, default=None):
    try:
        sql = f"ALTER TABLE `{table}` ADD COLUMN `{col}` {typ}"
        if default is not None:
            sql += f" DEFAULT {default}"
        conn.execute(text(sql))
        conn.commit()
        print(f"  ✅ {table}.{col}")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print(f"  ✓  {table}.{col}")
        else:
            print(f"  ⚠️  {table}.{col}: {e}")

print("\n🔧 Running full database migration...\n")

with engine.connect() as c:

    # ── users ─────────────────────────────────────────────────
    print("users:")
    add_col(c,"users","last_login","DATETIME",None)
    add_col(c,"users","is_locked","BOOLEAN NOT NULL","FALSE")
    add_col(c,"users","failed_login_count","INT NOT NULL",0)
    add_col(c,"users","two_fa_enabled","BOOLEAN NOT NULL","FALSE")
    add_col(c,"users","two_fa_secret","VARCHAR(32)",None)
    add_col(c,"users","refresh_token","TEXT",None)
    add_col(c,"users","created_by","INT",None)
    add_col(c,"users","updated_by","INT",None)
    add_col(c,"users","updated_at","DATETIME",None)

    # ── active_sessions ───────────────────────────────────────
    print("\nactive_sessions:")
    add_col(c,"active_sessions","location","VARCHAR(100)",None)
    add_col(c,"active_sessions","token_hash","VARCHAR(255)",None)
    add_col(c,"active_sessions","login_time","DATETIME",None)
    add_col(c,"active_sessions","last_seen","DATETIME",None)
    add_col(c,"active_sessions","device_info","VARCHAR(200)",None)

    # ── categories ────────────────────────────────────────────
    print("\ncategories:")
    add_col(c,"categories","prefix","VARCHAR(10)",None)
    add_col(c,"categories","default_hsn","VARCHAR(8)",None)
    add_col(c,"categories","default_gst_percent","DECIMAL(5,2)",18)
    add_col(c,"categories","sequence_counter","INT NOT NULL",0)
    add_col(c,"categories","description","TEXT",None)
    add_col(c,"categories","created_by","INT",None)
    add_col(c,"categories","updated_by","INT",None)
    add_col(c,"categories","updated_at","DATETIME",None)

    # ── products ──────────────────────────────────────────────
    print("\nproducts:")
    add_col(c,"products","serial_tracking","BOOLEAN NOT NULL","FALSE")
    add_col(c,"products","cost_alert_threshold_pct","DECIMAL(5,2)",5.00)
    add_col(c,"products","min_margin_pct","DECIMAL(5,2)",10.00)
    add_col(c,"products","image_path","VARCHAR(255)",None)
    add_col(c,"products","description","TEXT",None)
    add_col(c,"products","floor_price","DECIMAL(12,2)",0)
    add_col(c,"products","created_by","INT",None)
    add_col(c,"products","updated_by","INT",None)
    add_col(c,"products","updated_at","DATETIME",None)

    # ── stock_entries ─────────────────────────────────────────
    print("\nstock_entries:")
    add_col(c,"stock_entries","remaining_qty","DECIMAL(12,3)",None)
    add_col(c,"stock_entries","batch_date","DATE",None)
    add_col(c,"stock_entries","unit_cost","DECIMAL(12,2)",None)
    add_col(c,"stock_entries","serial_number","VARCHAR(100)",None)

    # ── cost_alerts ───────────────────────────────────────────
    print("\ncost_alerts:")
    add_col(c,"cost_alerts","old_value","DECIMAL(12,2)",None)
    add_col(c,"cost_alerts","new_value","DECIMAL(12,2)",None)
    add_col(c,"cost_alerts","suggested_price","DECIMAL(12,2)",None)
    add_col(c,"cost_alerts","is_resolved","BOOLEAN NOT NULL","FALSE")
    add_col(c,"cost_alerts","resolved_by","INT",None)
    add_col(c,"cost_alerts","resolved_at","DATETIME",None)

    # ── product_cost_history ──────────────────────────────────
    print("\nproduct_cost_history:")
    add_col(c,"product_cost_history","vendor_id","INT",None)
    add_col(c,"product_cost_history","recorded_at","DATETIME",None)
    add_col(c,"product_cost_history","financial_year","VARCHAR(7)",None)
    # Make effective_date nullable if it exists (old schema remnant)
    try:
        c.execute(text("ALTER TABLE `product_cost_history` MODIFY COLUMN `effective_date` DATE NULL"))
        c.commit()
        print("  ✅ product_cost_history.effective_date made nullable")
    except Exception as _e:
        if "Unknown column" in str(_e) or "doesn't exist" in str(_e):
            pass  # column doesn't exist, that's fine
        else:
            print(f"  ✓  effective_date: {_e}")

    # ── vendors ───────────────────────────────────────────────
    print("\nvendors:")
    add_col(c,"vendors","gst_registration_date","DATE",None)
    add_col(c,"vendors","nature_of_business","VARCHAR(100)",None)
    add_col(c,"vendors","bank_name","VARCHAR(100)",None)
    add_col(c,"vendors","bank_account","VARCHAR(20)",None)
    add_col(c,"vendors","bank_ifsc","VARCHAR(11)",None)
    add_col(c,"vendors","pan_number","VARCHAR(10)",None)
    add_col(c,"vendors","state_code","SMALLINT",None)
    add_col(c,"vendors","credit_days","INT",0)
    add_col(c,"vendors","created_by","INT",None)
    add_col(c,"vendors","updated_by","INT",None)
    add_col(c,"vendors","updated_at","DATETIME",None)

    # ── warehouses ────────────────────────────────────────────
    print("\nwarehouses:")
    add_col(c,"warehouses","created_by","INT",None)
    add_col(c,"warehouses","updated_by","INT",None)
    add_col(c,"warehouses","updated_at","DATETIME",None)

    # ── stock_transfers ───────────────────────────────────────
    print("\nstock_transfers:")
    add_col(c,"stock_transfers","transfer_number","VARCHAR(30)",None)
    add_col(c,"stock_transfers","created_by","INT",None)
    add_col(c,"stock_transfers","updated_by","INT",None)
    add_col(c,"stock_transfers","updated_at","DATETIME",None)

    # ── stock_adjustments ─────────────────────────────────────
    print("\nstock_adjustments:")
    add_col(c,"stock_adjustments","unit_cost","DECIMAL(12,2)",None)
    add_col(c,"stock_adjustments","notes","TEXT",None)
    add_col(c,"stock_adjustments","created_by","INT",None)
    add_col(c,"stock_adjustments","updated_by","INT",None)
    add_col(c,"stock_adjustments","updated_at","DATETIME",None)

    # ── stock_writeoffs ───────────────────────────────────────
    print("\nstock_writeoffs:")
    add_col(c,"stock_writeoffs","status","VARCHAR(20)","'pending'")
    add_col(c,"stock_writeoffs","approved_by","INT",None)
    add_col(c,"stock_writeoffs","approved_at","DATETIME",None)
    add_col(c,"stock_writeoffs","admin_notes","TEXT",None)
    add_col(c,"stock_writeoffs","notes","TEXT",None)
    add_col(c,"stock_writeoffs","created_by","INT",None)
    add_col(c,"stock_writeoffs","updated_by","INT",None)
    add_col(c,"stock_writeoffs","updated_at","DATETIME",None)

    # ── purchases ─────────────────────────────────────────────
    print("\npurchases:")
    add_col(c,"purchases","created_by","INT",None)
    add_col(c,"purchases","updated_by","INT",None)
    add_col(c,"purchases","updated_at","DATETIME",None)

    # ── invoices ──────────────────────────────────────────────
    print("\ninvoices:")
    add_col(c,"invoices","irn","VARCHAR(200)",None)
    add_col(c,"invoices","irn_status","VARCHAR(20)",None)
    add_col(c,"invoices","qr_code","TEXT",None)
    add_col(c,"invoices","eway_bill_number","VARCHAR(50)",None)
    add_col(c,"invoices","salesperson_id","INT",None)
    add_col(c,"invoices","original_invoice_id","INT",None)
    add_col(c,"invoices","cancelled_reason","TEXT",None)
    add_col(c,"invoices","cancelled_at","DATETIME",None)
    add_col(c,"invoices","created_by","INT",None)
    add_col(c,"invoices","updated_by","INT",None)
    add_col(c,"invoices","updated_at","DATETIME",None)

    # ── customers ─────────────────────────────────────────────
    print("\ncustomers:")
    add_col(c,"customers","created_by","INT",None)
    add_col(c,"customers","updated_by","INT",None)
    add_col(c,"customers","updated_at","DATETIME",None)

    # ── bank_stock_statements ─────────────────────────────────
    print("\nbank_stock_statements:")
    add_col(c,"bank_stock_statements","stock_items_json","TEXT",None)
    add_col(c,"bank_stock_statements","debtor_items_json","TEXT",None)
    add_col(c,"bank_stock_statements","financial_year","VARCHAR(10)",None)
    add_col(c,"bank_stock_statements","created_by","INT",None)
    add_col(c,"bank_stock_statements","updated_by","INT",None)
    add_col(c,"bank_stock_statements","updated_at","DATETIME",None)


    # ── customers ────────────────────────────────────────────
    print("\ncustomers (extra columns):")
    add_col(c,"customers","gst_registration_date","DATE",None)
    add_col(c,"customers","state_code","SMALLINT",None)
    add_col(c,"customers","credit_limit","DECIMAL(12,2)",0)
    add_col(c,"customers","credit_days","INT",0)
    add_col(c,"customers","is_b2b","BOOLEAN NOT NULL","TRUE")

    # ── customer_addresses ────────────────────────────────────
    print("\ncustomer_addresses:")
    add_col(c,"customer_addresses","state_code","SMALLINT",None)
    add_col(c,"customer_addresses","address_type","VARCHAR(20)","'both'")
    add_col(c,"customer_addresses","is_preferred_billing","BOOLEAN NOT NULL","FALSE")
    add_col(c,"customer_addresses","is_preferred_shipping","BOOLEAN NOT NULL","FALSE")

    # ── vendor_addresses ──────────────────────────────────────
    print("\nvendor_addresses:")
    add_col(c,"vendor_addresses","state_code","SMALLINT",None)
    add_col(c,"vendor_addresses","address_type","VARCHAR(20)","'both'")
    add_col(c,"vendor_addresses","is_preferred","BOOLEAN NOT NULL","FALSE")

    # ── customer_payments ─────────────────────────────────────
    print("\ncustomer_payments:")
    add_col(c,"customer_payments","tds_amount","DECIMAL(12,2)",0)
    add_col(c,"customer_payments","is_advance","BOOLEAN NOT NULL","FALSE")
    add_col(c,"customer_payments","notes","TEXT",None)

    # ── vendor_payments ───────────────────────────────────────
    print("\nvendor_payments:")
    add_col(c,"vendor_payments","is_advance","BOOLEAN NOT NULL","FALSE")
    add_col(c,"vendor_payments","notes","TEXT",None)
    add_col(c,"vendor_payments","financial_year","VARCHAR(7)",None)

    # ── invoices (extra) ──────────────────────────────────────
    print("\ninvoices (extra columns):")
    add_col(c,"invoices","billing_address_id","INT",None)
    add_col(c,"invoices","shipping_address_id","INT",None)
    add_col(c,"invoices","item_discount","DECIMAL(12,2)",0)
    add_col(c,"invoices","outstanding_amount","DECIMAL(12,2)",0)
    add_col(c,"invoices","paid_amount","DECIMAL(12,2)",0)
    add_col(c,"invoices","gst_type","VARCHAR(20)",None)
    add_col(c,"invoices","qr_code_path","VARCHAR(255)",None)
    add_col(c,"invoices","eway_bill_status","VARCHAR(20)",None)

    # ── purchases (extra) ─────────────────────────────────────
    print("\npurchases (extra columns):")
    add_col(c,"purchases","payment_due_date","DATE",None)
    add_col(c,"purchases","gst_type","VARCHAR(20)",None)
    add_col(c,"purchases","is_cancelled","BOOLEAN NOT NULL","FALSE")
    add_col(c,"purchases","notes","TEXT",None)
    add_col(c,"purchases","financial_year","VARCHAR(7)",None)

    # ── ledger_entries ────────────────────────────────────────
    print("\nledger_entries:")
    add_col(c,"ledger_entries","vendor_id","INT",None)
    add_col(c,"ledger_entries","financial_year","VARCHAR(7)",None)

    # ── product_cost_history (effective_date fix) ─────────────
    print("\nproduct_cost_history (effective_date fix):")
    try:
        c.execute(text("ALTER TABLE `product_cost_history` MODIFY COLUMN `effective_date` DATE NULL"))
        c.commit()
        print("  ✅ effective_date made nullable")
    except Exception as _e:
        if "Unknown column" in str(_e) or "doesn't exist" in str(_e).lower():
            pass
        else:
            print(f"  ✓  {_e}")


# ── Create missing tables ────────────────────────────────────
CREATE_TABLES = [
    ("cheques", """CREATE TABLE IF NOT EXISTS `cheques` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cheque_number VARCHAR(30) NOT NULL,
        cheque_date DATE NOT NULL,
        bank_name VARCHAR(100) NOT NULL,
        amount DECIMAL(12,2) NOT NULL,
        status VARCHAR(20) DEFAULT 'received',
        customer_id INT, vendor_id INT,
        is_pdc BOOLEAN DEFAULT FALSE,
        deposit_date DATE, clearance_date DATE,
        bounce_date DATE, bounce_reason TEXT,
        bounce_charges DECIMAL(10,2) DEFAULT 0,
        notes TEXT, bank_account_code VARCHAR(20),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_by INT, updated_at DATETIME, updated_by INT
    )"""),
    ("cash_closings", """CREATE TABLE IF NOT EXISTS `cash_closings` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        closing_date DATE UNIQUE NOT NULL,
        opening_balance DECIMAL(14,2) DEFAULT 0,
        total_receipts DECIMAL(14,2) DEFAULT 0,
        total_payments DECIMAL(14,2) DEFAULT 0,
        total_expenses DECIMAL(14,2) DEFAULT 0,
        total_deposits DECIMAL(14,2) DEFAULT 0,
        closing_balance DECIMAL(14,2) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'draft',
        approved_by INT, approved_at DATETIME, notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, created_by INT
    )"""),
    ("expenses", """CREATE TABLE IF NOT EXISTS `expenses` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        expense_number VARCHAR(30) UNIQUE NOT NULL,
        expense_date DATE NOT NULL,
        category VARCHAR(100) NOT NULL,
        description TEXT NOT NULL,
        amount DECIMAL(12,2) NOT NULL,
        payment_mode VARCHAR(20) DEFAULT 'cash',
        reference_number VARCHAR(100),
        status VARCHAR(30) DEFAULT 'pending_approval',
        approved_by INT, approved_at DATETIME, notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_by INT, updated_at DATETIME, updated_by INT
    )"""),
    ("tds_entries", """CREATE TABLE IF NOT EXISTS `tds_entries` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        tds_number VARCHAR(30) UNIQUE NOT NULL,
        customer_id INT NOT NULL,
        deduction_date DATE NOT NULL,
        invoice_amount DECIMAL(12,2) NOT NULL,
        tds_amount DECIMAL(12,2) NOT NULL,
        tds_percent DECIMAL(5,2) NOT NULL,
        section_code VARCHAR(10) DEFAULT '194C',
        tan_number VARCHAR(10),
        financial_year VARCHAR(7) NOT NULL,
        is_reconciled BOOLEAN DEFAULT FALSE, notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_by INT, updated_at DATETIME, updated_by INT
    )"""),
    ("transporters", """CREATE TABLE IF NOT EXISTS `transporters` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        gstin VARCHAR(15), contact_person VARCHAR(100),
        phone VARCHAR(15), email VARCHAR(100),
        is_active BOOLEAN DEFAULT TRUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_by INT, updated_at DATETIME, updated_by INT
    )"""),
    ("vehicles", """CREATE TABLE IF NOT EXISTS `vehicles` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        vehicle_number VARCHAR(20) UNIQUE NOT NULL,
        vehicle_type VARCHAR(20) NOT NULL,
        owner_name VARCHAR(100), transporter_id INT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_by INT, updated_at DATETIME, updated_by INT
    )"""),
    ("stock_writeoffs", """CREATE TABLE IF NOT EXISTS `stock_writeoffs` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        writeoff_number VARCHAR(30) UNIQUE NOT NULL,
        warehouse_id INT NOT NULL, product_id INT NOT NULL,
        quantity DECIMAL(12,3) NOT NULL,
        reason_type VARCHAR(30) NOT NULL,
        reason_detail TEXT, writeoff_date DATE NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        approved_by INT, approved_at DATETIME,
        admin_notes TEXT, notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_by INT, updated_at DATETIME, updated_by INT
    )"""),
]

print("\nCreating missing tables...")
with engine.connect() as c:
    for table, sql in CREATE_TABLES:
        try:
            c.execute(text(sql))
            c.commit()
            print(f"  ✅ Table: {table}")
        except Exception as e:
            print(f"  ✓  {table}: {str(e)[:60]}")

print("\n✅ Migration complete!\n")
print("Next: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
