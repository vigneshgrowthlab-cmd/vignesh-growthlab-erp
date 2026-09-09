"""Add original_item_id to invoice_items for credit-note over-return guard

Links each credit-note line back to the exact source invoice_item it returns,
enabling precise per-line quantity validation across multiple credit notes.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f0a1b2c3d4e5'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    have = {c["name"] for c in insp.get_columns("invoice_items")}
    if "original_item_id" not in have:
        op.add_column(
            "invoice_items",
            sa.Column("original_item_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_invoice_items_original_item_id",
            "invoice_items", "invoice_items",
            ["original_item_id"], ["id"],
        )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    have = {c["name"] for c in insp.get_columns("invoice_items")}
    if "original_item_id" in have:
        op.drop_constraint(
            "fk_invoice_items_original_item_id", "invoice_items", type_="foreignkey"
        )
        op.drop_column("invoice_items", "original_item_id")
