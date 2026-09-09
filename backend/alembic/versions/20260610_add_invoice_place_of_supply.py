"""add place_of_supply column to invoices

Persists the GST place-of-supply (destination state code) on each invoice at
creation time. Previously it was derived on the fly from the customer's
current shipping address, so a later address edit could retroactively change
the place of supply on an already-filed invoice. Freezing it on the document
keeps the stored invoice consistent with what was reported in GSTR-1.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "invoices" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("invoices")}
    if "place_of_supply" not in have:
        op.add_column(
            "invoices",
            sa.Column("place_of_supply", sa.SmallInteger(), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "invoices" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("invoices")}
    if "place_of_supply" in have:
        op.drop_column("invoices", "place_of_supply")
