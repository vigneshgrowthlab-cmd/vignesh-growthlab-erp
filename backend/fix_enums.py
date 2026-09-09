"""
fix_enums.py — Run once to convert all ENUM columns to VARCHAR.
Safe to run multiple times.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import engine
from sqlalchemy import text

FIXES = [
    ("invoices",          "document_type",    "VARCHAR(30)"),
    ("invoice_sequences", "document_type",    "VARCHAR(30)"),
    ("ledger_entries",    "transaction_type", "VARCHAR(20)"),
    ("journal_lines",     "transaction_type", "VARCHAR(20)"),
    ("customer_payments", "payment_mode",     "VARCHAR(20)"),
    ("vendor_payments",   "payment_mode",     "VARCHAR(20)"),
    ("expenses",          "payment_mode",     "VARCHAR(20)"),
    ("cheques",           "status",           "VARCHAR(20)"),
    ("stock_writeoffs",   "status",           "VARCHAR(20)"),
    ("invoices",          "quotation_status", "VARCHAR(20)"),
    ("invoices",          "quotation_id",     "INT"),
]

print("\nConverting ENUM columns to VARCHAR...\n")

with engine.connect() as c:
    for table, col, typ in FIXES:
        try:
            # Check column exists
            result = c.execute(text(
                f"SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_schema=DATABASE() AND table_name='{table}' AND column_name='{col}'"
            ))
            if result.scalar() == 0:
                # Add column if missing
                c.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {typ} NULL"))
                c.commit()
                print(f"  + {table}.{col} (added)")
            else:
                # Modify to VARCHAR
                c.execute(text(f"ALTER TABLE `{table}` MODIFY COLUMN `{col}` {typ} NULL"))
                c.commit()
                print(f"  OK {table}.{col} -> {typ}")
        except Exception as e:
            print(f"  ERR {table}.{col}: {str(e)[:80]}")

print("\nDone. Restart uvicorn now.\n")
