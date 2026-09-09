"""add entry_date to stock_entries

Aligns the StockEntry ORM with the live schema. The column was already
added on running databases by app/main.py::_auto_migrate, but it was
missing from the SQLAlchemy model — which broke any query that referenced
StockEntry.entry_date (e.g. warehouse stock-ageing, bank stock-statement).
Adding it to the model and registering this migration makes the schema
authoritative through Alembic.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    from sqlalchemy import inspect as _inspect
    insp = _inspect(bind)
    try:
        return any(c["name"] == column for c in insp.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "stock_entries", "entry_date"):
        op.add_column("stock_entries", sa.Column("entry_date", sa.Date(), nullable=True))
    # On dev DBs where _auto_migrate had previously forced DEFAULT 0 (which
    # MariaDB stores as '0000-00-00' for DATE columns), normalise to NULL.
    op.execute("ALTER TABLE stock_entries MODIFY COLUMN entry_date DATE NULL DEFAULT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "stock_entries", "entry_date"):
        op.drop_column("stock_entries", "entry_date")
