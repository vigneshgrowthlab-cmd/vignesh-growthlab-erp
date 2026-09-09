"""Add credited_amount to invoices

Tracks the running total of all active (non-cancelled) credit notes applied to
an invoice so the value is available without a join.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    have = {c["name"] for c in insp.get_columns("invoices")}
    if "credited_amount" not in have:
        op.add_column(
            "invoices",
            sa.Column("credited_amount", sa.Numeric(12, 2), nullable=True, server_default="0"),
        )

    # Backfill: sum total_amount of all non-cancelled credit notes per invoice
    op.execute(
        """
        UPDATE invoices orig
        JOIN (
            SELECT original_invoice_id, SUM(total_amount) AS total_credited
            FROM invoices
            WHERE document_type = 'credit_note'
              AND is_cancelled = 0
              AND original_invoice_id IS NOT NULL
            GROUP BY original_invoice_id
        ) cn ON cn.original_invoice_id = orig.id
        SET orig.credited_amount = cn.total_credited
        WHERE orig.document_type != 'credit_note'
        """
    )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    have = {c["name"] for c in insp.get_columns("invoices")}
    if "credited_amount" in have:
        op.drop_column("invoices", "credited_amount")
