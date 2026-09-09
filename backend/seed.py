"""
seed.py - Run once to seed required master data.
Safe to run multiple times (uses ON DUPLICATE KEY UPDATE).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import engine
from app.core.config import settings
from sqlalchemy import text

print("\nSeeding required master data...\n")

with engine.connect() as c:

    # Chart of Accounts
    print("-- Accounts --")
    accounts = [
        ("CASH",          "Cash in Hand",                "asset"),
        ("BANK",          "Bank Account",                "asset"),
        ("STOCK",         "Stock / Inventory",           "asset"),
        ("DEBTORS",       "Accounts Receivable",         "asset"),
        ("GST_ITC",       "GST Input Tax Credit",        "asset"),
        ("CREDITORS",     "Accounts Payable",            "liability"),
        ("GST_PAY",       "GST Payable",                 "liability"),
        ("SALES",         "Sales Revenue",               "income"),
        ("PURCHASES",     "Purchase Cost of Goods",      "expense"),
        ("EXPENSES",      "General Expenses",            "expense"),
        ("LOSS_WRITEOFF", "Stock Writeoff Loss",         "expense"),
        ("TDS_PAYABLE",   "TDS Payable",                 "liability"),
        ("ADVANCE_PAY",   "Advance Payments",            "asset"),
        ("ADVANCE_REC",   "Advance Receipts",            "liability"),
        ("DISCOUNT",      "Discount Allowed",            "expense"),
        ("INTEREST",      "Interest Income",             "income"),
        ("BANK_CHARGES",  "Bank Charges",                "expense"),
        ("OPENING_STOCK", "Opening Stock",               "asset"),
        ("ROUND_OFF",     "Round Off",                   "income"),
    ]

    for code, name, atype in accounts:
        try:
            c.execute(text(
                "INSERT INTO accounts (account_code, name, account_type, is_system, is_active, "
                "opening_balance, current_balance) "
                "VALUES (:code, :name, :type, 1, 1, 0, 0) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name), account_type=VALUES(account_type)"
            ), {"code": code, "name": name, "type": atype})
            c.commit()
            print("  OK: " + code)
        except Exception as e:
            print("  ERR " + code + ": " + str(e))

    # Company Settings
    print("\n-- Company Settings --")
    try:
        existing = c.execute(text("SELECT id FROM company_settings LIMIT 1")).fetchone()
        if not existing:
            c.execute(text(
                "INSERT INTO company_settings "
                "(company_name, gstin, state, state_code, address_line1, city, pincode, financial_year_start) "
                "VALUES (:name, :gstin, :state, :state_code, :address, :city, :pincode, :fy_month)"
            ), {
                "name": settings.COMPANY_NAME,
                "gstin": settings.COMPANY_GSTIN,
                "state": settings.COMPANY_STATE,
                "state_code": settings.COMPANY_STATE_CODE,
                "address": settings.COMPANY_ADDRESS,
                "city": settings.COMPANY_CITY,
                "pincode": settings.COMPANY_PINCODE,
                "fy_month": settings.FINANCIAL_YEAR_START_MONTH,
            })
            c.commit()
            print("  OK: Default company settings created")
        else:
            print("  OK: Company settings already exist")
    except Exception as e:
        print("  ERR company_settings: " + str(e))

    # Default Warehouse
    print("\n-- Default Warehouse --")
    try:
        existing = c.execute(text("SELECT id FROM warehouses LIMIT 1")).fetchone()
        if not existing:
            c.execute(text(
                "INSERT INTO warehouses (name, code, is_active, is_default) "
                "VALUES ('Main Warehouse', 'MAIN', 1, 1)"
            ))
            c.commit()
            print("  OK: Default warehouse created")
        else:
            print("  OK: Warehouse already exists")
    except Exception as e:
        print("  ERR warehouse: " + str(e))

    # Super-Admin User
    print("\n-- Super-Admin Users --")
    try:
        import bcrypt
        pw = bcrypt.hashpw(b"Admin@1234", bcrypt.gensalt()).decode()
        for uname, email, fname in [
            ("admin", "admin@vigneshgrowthlab.com", "Vignesh GrowthLab Admin"),
            ("superadmin", "superadmin@vigneshgrowthlab.com", "Vignesh GrowthLab Superadmin"),
        ]:
            existing = c.execute(text("SELECT id FROM users WHERE username=:u"), {"u": uname}).fetchone()
            if not existing:
                c.execute(text(
                    "INSERT INTO users (username, email, full_name, hashed_password, role, is_active) "
                    "VALUES (:u, :e, :fn, :pw, 'super_admin', 1)"
                ), {"u": uname, "e": email, "fn": fname, "pw": pw})
                print(f"  OK: Super-admin user created ({uname} / Admin@1234)")
            else:
                c.execute(text(
                    "UPDATE users SET role='super_admin', hashed_password=:pw, is_active=1 WHERE username=:u"
                ), {"u": uname, "pw": pw})
                print(f"  OK: Super-admin user verified/updated ({uname} / Admin@1234)")
        c.commit()
    except Exception as e:
        print("  ERR super-admin user: " + str(e))

    # Invoice Sequences
    print("\n-- Invoice Sequences --")
    sequences = [
        ("b2b_invoice",      "BINV", "2025-26"),
        ("b2c_invoice",      "CINV", "2025-26"),
        ("quotation",        "QT",   "2025-26"),
        ("delivery_challan", "DC",   "2025-26"),
        ("credit_note",      "CN",   "2025-26"),
    ]
    for doc_type, prefix, fy in sequences:
        try:
            c.execute(text(
                "INSERT IGNORE INTO invoice_sequences "
                "(document_type, prefix, financial_year, last_number) "
                "VALUES (:dt, :pfx, :fy, 0)"
            ), {"dt": doc_type, "pfx": prefix, "fy": fy})
            c.commit()
            print("  OK: " + doc_type)
        except Exception as e:
            print("  ERR " + doc_type + ": " + str(e))

print("\nDone! Now run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000\n")
