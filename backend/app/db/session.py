from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

import os

db_url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL") or settings.DATABASE_URL
if os.getenv("MYSQLHOST") and not os.getenv("DATABASE_URL") and not os.getenv("MYSQL_URL"):
    _user = os.getenv("MYSQLUSER", "root")
    _pwd = os.getenv("MYSQLPASSWORD", "")
    _host = os.getenv("MYSQLHOST")
    _port = os.getenv("MYSQLPORT", "3306")
    _db = os.getenv("MYSQLDATABASE", "railway")
    db_url = f"mysql+pymysql://{_user}:{_pwd}@{_host}:{_port}/{_db}"

if db_url.startswith("mysql://"):
    db_url = db_url.replace("mysql://", "mysql+pymysql://", 1)

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
)

# Enforce foreign keys on every connection
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET time_zone = '+05:30'")
    # The app was written/tested against MariaDB. Prod runs MySQL 8.4 (Percona),
    # whose default sql_mode is stricter and breaks behaviour the app relies on:
    #   - ONLY_FULL_GROUP_BY  -> report/ledger GROUP BY queries error 1055
    #   - STRICT_TRANS_TABLES -> raw-SQL inserts (e.g. seed.py) that omit a
    #     NOT NULL column having only a Python-side ORM default error 1364
    # Strip those flags per-connection to match the MariaDB-tested behaviour;
    # inputs are validated by Pydantic before reaching the DB.
    cursor.execute("SELECT @@sql_mode")
    _modes = (cursor.fetchone()[0] or "").split(",")
    _drop = {"ONLY_FULL_GROUP_BY", "STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"}
    cursor.execute(
        "SET SESSION sql_mode = %s",
        (",".join(m for m in _modes if m and m not in _drop),),
    )
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
