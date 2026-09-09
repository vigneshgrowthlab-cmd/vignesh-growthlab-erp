"""add round_off column to invoices

Stores the nearest-rupee rounding adjustment applied to an invoice's
grand total (e.g. +0.40 / -0.30). total_amount becomes the rounded
whole-rupee figure; round_off captures the difference so the journal's
balancing Round Off line and the E-Invoice RndOffAmt reconcile.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "invoices" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("invoices")}
    if "round_off" not in have:
        op.add_column(
            "invoices",
            sa.Column("round_off", sa.Numeric(12, 2), nullable=True, server_default="0"),
        )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "invoices" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("invoices")}
    if "round_off" in have:
        op.drop_column("invoices", "round_off")
