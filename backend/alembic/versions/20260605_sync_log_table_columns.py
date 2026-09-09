"""sync einvoice_logs / eway_bill_logs columns with models

Brings two log tables in line with the ORM models. On some databases these
columns were defined on the models (and in earlier migrations) but the DDL
was never applied (the legacy stamp-without-run / _auto_migrate situation),
so writes fail with "Unknown column".

einvoice_logs: ack_number, ack_date, retry_count
eway_bill_logs: dc_approved_by, dc_approved_at, dc_rejected_by,
                dc_rejected_at, dc_rejection_reason

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


TABLE_COLUMNS = {
    "einvoice_logs": [
        ("ack_number", sa.String(length=50)),
        ("ack_date", sa.DateTime()),
        ("retry_count", sa.SmallInteger()),
    ],
    "eway_bill_logs": [
        ("dc_approved_by", sa.Integer()),
        ("dc_approved_at", sa.DateTime()),
        ("dc_rejected_by", sa.Integer()),
        ("dc_rejected_at", sa.DateTime()),
        ("dc_rejection_reason", sa.Text()),
    ],
}


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())
    for table, columns in TABLE_COLUMNS.items():
        if table not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, col_type in columns:
            if name not in have:
                op.add_column(table, sa.Column(name, col_type, nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())
    for table, columns in TABLE_COLUMNS.items():
        if table not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, _ in reversed(columns):
            if name in have:
                op.drop_column(table, name)
