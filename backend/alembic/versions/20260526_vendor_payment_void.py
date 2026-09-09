"""add vendor_payments soft-void columns

Adds is_void / voided_at / voided_by so vendor payments can be reversed
without destroying audit history. The void path posts reversing ledger +
journal entries and recomputes paid_amount on affected purchases.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
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
    # Idempotent: app/main.py::_auto_migrate may have already added these
    # columns on a running server, so guard each ADD COLUMN.
    bind = op.get_bind()
    if not _has_column(bind, "vendor_payments", "is_void"):
        op.add_column(
            "vendor_payments",
            sa.Column("is_void", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not _has_column(bind, "vendor_payments", "voided_at"):
        op.add_column("vendor_payments", sa.Column("voided_at", sa.DateTime(), nullable=True))
    if not _has_column(bind, "vendor_payments", "voided_by"):
        op.add_column(
            "vendor_payments",
            sa.Column("voided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "vendor_payments", "voided_by"):
        op.drop_column("vendor_payments", "voided_by")
    if _has_column(bind, "vendor_payments", "voided_at"):
        op.drop_column("vendor_payments", "voided_at")
    if _has_column(bind, "vendor_payments", "is_void"):
        op.drop_column("vendor_payments", "is_void")
