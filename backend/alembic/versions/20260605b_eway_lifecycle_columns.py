"""eway bill lifecycle columns (entry_type, cancel reason/date)

Adds columns to eway_bill_logs to support the e-way bill lifecycle:
recording cancellation (Rule 138(9)) and vehicle / Part-B updates
(Rule 138(5)) entered manually from the portal.

entry_type: 'generate' | 'update_vehicle' | 'cancel'
cancel_reason / cancelled_at: cancellation audit

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


NEW_COLUMNS = [
    ("entry_type", sa.String(length=20)),
    ("cancel_reason", sa.String(length=200)),
    ("cancelled_at", sa.DateTime()),
]


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "eway_bill_logs" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("eway_bill_logs")}
    for name, col_type in NEW_COLUMNS:
        if name not in have:
            op.add_column("eway_bill_logs", sa.Column(name, col_type, nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "eway_bill_logs" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("eway_bill_logs")}
    for name, _ in reversed(NEW_COLUMNS):
        if name in have:
            op.drop_column("eway_bill_logs", name)
