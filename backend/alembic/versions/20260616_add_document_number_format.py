"""add document_number_format

Phase 5b of the configuration-driven parameter system (see
docs/CONFIG_MIGRATION_PLAN.md). Holds prefix/padding/separator for internal
document numbers (JE/PO/VP/ADJ/WO/EXP/TDS/BSS). Resolution falls back to the
in-code prefix/padding when a row is absent, so an empty table is a no-op.
Invoice numbering is unchanged (CompanySettings prefixes + invoice_sequences).

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "document_number_format" not in set(insp.get_table_names()):
        op.create_table(
            "document_number_format",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("doc_type", sa.String(20), nullable=False, unique=True),
            sa.Column("prefix", sa.String(10), nullable=False),
            sa.Column("padding", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("separator", sa.String(3), nullable=False, server_default="-"),
            sa.Column("description", sa.String(120), nullable=True),
            sa.Column("status", sa.String(15), nullable=False, server_default="active"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "document_number_format" in set(insp.get_table_names()):
        op.drop_table("document_number_format")
