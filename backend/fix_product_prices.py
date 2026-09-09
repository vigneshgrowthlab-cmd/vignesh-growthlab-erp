"""
Run this script to add b2b_price and b2c_price columns to products table
and populate them from existing selling_price.
"""
import sys
sys.path.insert(0, '.')
from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Add columns
    for col, default in [('b2b_price', 'selling_price'), ('b2c_price', 'selling_price * 1.0952')]:
        try:
            conn.execute(text(f"ALTER TABLE products ADD COLUMN {col} DECIMAL(12,2) DEFAULT 0"))
            conn.commit()
            print(f"Added {col}")
        except Exception as e:
            print(f"Skip {col}: {str(e)[:50]}")
    
    # Populate b2b_price from selling_price
    conn.execute(text("UPDATE products SET b2b_price = selling_price WHERE b2b_price = 0 OR b2b_price IS NULL"))
    # Populate b2c_price as 10% more than cost (if purchase_cost > 0)
    conn.execute(text("UPDATE products SET b2c_price = ROUND(purchase_cost * 1.10, 2) WHERE purchase_cost > 0 AND (b2c_price = 0 OR b2c_price IS NULL)"))
    # If no purchase_cost, use selling_price * 1.05 as approximation
    conn.execute(text("UPDATE products SET b2c_price = ROUND(selling_price * 1.048, 2) WHERE (purchase_cost = 0 OR purchase_cost IS NULL) AND (b2c_price = 0 OR b2c_price IS NULL)"))
    conn.commit()
    print("Populated b2b_price and b2c_price from existing data")

print("Done")
