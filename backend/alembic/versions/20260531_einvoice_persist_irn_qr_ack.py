"""einvoice persist irn qr ack signed columns

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-05-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


NEW_COLUMNS = [
    ("qr_code", sa.Text()),
    ("signed_invoice", sa.Text()),
    ("irn_ack_number", sa.String(length=50)),
    ("irn_ack_date", sa.DateTime()),
    ("irn_generated_at", sa.DateTime()),
    ("irn_error", sa.Text()),
]


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("invoices")]
    for name, col_type in NEW_COLUMNS:
        if name not in cols:
            op.add_column("invoices", sa.Column(name, col_type, nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("invoices")]
    for name, _ in reversed(NEW_COLUMNS):
        if name in cols:
            op.drop_column("invoices", name)
