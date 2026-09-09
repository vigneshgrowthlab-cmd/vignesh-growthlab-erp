import sys
sys.path.insert(0, '/home/claude/erp-final-fix/backend')

from app.db.session import engine
from sqlalchemy import text

columns = [
    ("invoices", "vehicle_number",               "VARCHAR(20)"),
    ("invoices", "vehicle_id",                   "INT"),
    ("invoices", "driver_name",                  "VARCHAR(100)"),
    ("invoices", "lr_number",                    "VARCHAR(50)"),
    ("invoices", "dc_destination_warehouse_id",  "INT"),
    ("invoices", "dc_status",                    "VARCHAR(20) DEFAULT 'pending'"),
    ("stock_transfers", "dc_ids",               "TEXT"),
    ("stock_transfers", "created_by",            "INT"),
]

with engine.connect() as conn:
    for table, col, defn in columns:
        try:
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {defn}"))
            conn.commit()
            print(f"  ADDED  {table}.{col}")
        except Exception as e:
            err = str(e)
            if "Duplicate column" in err or "already exists" in err:
                print(f"  EXISTS {table}.{col}")
            else:
                print(f"  ERROR  {table}.{col}: {err[:80]}")

print("\nDone.")