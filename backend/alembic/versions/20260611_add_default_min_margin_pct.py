"""add default_min_margin_pct to company_settings

Products carry a per-row min_margin_pct (default 10%), but the "10" default was
hardcoded in the model, the auto-migrate list and the product form. This adds a
company-wide configurable default so the new-product form and any future
defaulting read it from settings instead of a literal.

Revision ID: a9b0c1d2e3f4
Revises: e7f8a9b0c1d2
Create Date: 2026-06-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9b0c1d2e3f4'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "company_settings" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("company_settings")}
        if "default_min_margin_pct" not in have:
            op.add_column(
                "company_settings",
                sa.Column("default_min_margin_pct", sa.Numeric(5, 2),
                          nullable=True, server_default="10.00"),
            )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "company_settings" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("company_settings")}
        if "default_min_margin_pct" in have:
            op.drop_column("company_settings", "default_min_margin_pct")
