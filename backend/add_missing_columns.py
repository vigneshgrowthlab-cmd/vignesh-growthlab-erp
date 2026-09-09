from app.db.session import engine
from sqlalchemy import text
with engine.connect() as c:
    try:
        c.execute(text(\"ALTER TABLE accounts ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''\"))
        c.commit()
        print('Added name column')
    except Exception as e:
        print(f'Error: {e}')
    # Also update existing rows with a name
    c.execute(text(\"UPDATE accounts SET name=account_code WHERE name='' OR name IS NULL\"))
    c.commit()
    print('Done - now run: python seed.py')