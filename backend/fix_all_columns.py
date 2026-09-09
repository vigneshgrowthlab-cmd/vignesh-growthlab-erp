import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import engine
from sqlalchemy import text

queries = [
  "ALTER TABLE invoice_items DROP COLUMN IF EXISTS serial_numbers",
"ALTER TABLE purchase_items DROP COLUMN IF EXISTS serial_numbers",
]

with engine.connect() as c:
    try:
        for query in queries:
            c.execute(text(query))

        c.commit()
        print("ALTERED")

    except Exception as e:
        c.rollback()
        print(f"Error: {e}")