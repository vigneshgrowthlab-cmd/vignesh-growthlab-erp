"""add DC approval/rejection audit fields to invoices

Tracks who approved or rejected a Delivery Challan during a stock transfer,
when it happened, and the reject reason. Used by the new destination-warehouse
approval flow in the warehouse module.

Revision ID: 1a2b3c4d5e6f
Revises: f6a7b8c9d0e1
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa


revision = '1a2b3c4d5e6f'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    from sqlalchemy import inspect as _inspect
    insp = _inspect(bind)
    try:
        return any(c["name"] == column for c in insp.get_columns(table))
    except Exception:
        return False


COLUMNS = [
    ("dc_approved_by", sa.Integer(), True),
    ("dc_approved_at", sa.DateTime(), True),
    ("dc_rejected_by", sa.Integer(), True),
    ("dc_rejected_at", sa.DateTime(), True),
    ("dc_rejection_reason", sa.Text(), True),
]


def upgrade() -> None:
    bind = op.get_bind()
    for name, coltype, nullable in COLUMNS:
        if not _has_column(bind, "invoices", name):
            op.add_column("invoices", sa.Column(name, coltype, nullable=nullable))


def downgrade() -> None:
    bind = op.get_bind()
    for name, _coltype, _nullable in COLUMNS:
        if _has_column(bind, "invoices", name):
            op.drop_column("invoices", name)
