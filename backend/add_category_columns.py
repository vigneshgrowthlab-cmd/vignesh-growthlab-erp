import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import engine
from sqlalchemy import text

columns = [
    ("prefix",      "VARCHAR(4)"),
    ("default_hsn", "VARCHAR(8)"),
    ("default_gst", "DECIMAL(5,2) DEFAULT 18"),
]

with engine.connect() as conn:
    for col, typ in columns:
        try:
            conn.execute(text(f"ALTER TABLE categories ADD COLUMN {col} {typ}"))
            conn.commit()
            print(f"Added: {col}")
        except Exception as e:
            if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                print(f"Already exists: {col}")
            else:
                print(f"Error {col}: {e}")

print("Done")