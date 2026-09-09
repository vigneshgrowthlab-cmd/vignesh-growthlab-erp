import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import engine
from sqlalchemy import text

columns = [
    ("pan_number",          "VARCHAR(10)"),
    ("bank_name",           "VARCHAR(100)"),
    ("bank_account_number", "VARCHAR(30)"),
    ("bank_ifsc",           "VARCHAR(15)"),
]

with engine.connect() as conn:
    for col_name, col_type in columns:
        try:
            conn.execute(text(f"ALTER TABLE vendors ADD COLUMN {col_name} {col_type}"))
            conn.commit()
            print(f"Added column: {col_name}")
        except Exception as e:
            if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                print(f"Already exists: {col_name}")
            else:
                print(f"Error adding {col_name}: {e}")

print("\nDone.")