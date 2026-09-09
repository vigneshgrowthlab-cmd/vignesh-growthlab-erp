import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import engine
from app.models.models import Base
from sqlalchemy import text

print("Disabling foreign key checks...")
with engine.connect() as conn:
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    conn.commit()

print("Dropping all tables...")
Base.metadata.drop_all(bind=engine)

print("Creating all tables with latest schema...")
Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    conn.commit()

print("Done — all tables recreated successfully")