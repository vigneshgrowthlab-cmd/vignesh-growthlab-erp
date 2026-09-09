"""add bank reconciliation tables

Adds bank_reconciliations (header) + bank_reconciliation_lines (per bank
statement entry, with match audit fields) for auditable bank reconciliation
with manual matching. Also adds is_reconciled / reconciliation_id to
journal_lines so cleared BANK journal lines can't be re-reconciled.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "bank_reconciliations" not in tables:
        op.create_table(
            "bank_reconciliations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reconciliation_number", sa.String(30), nullable=True, unique=True),
            sa.Column("account_code", sa.String(20), nullable=False, server_default="BANK"),
            sa.Column("period_from", sa.Date(), nullable=False),
            sa.Column("period_to", sa.Date(), nullable=False),
            sa.Column("statement_closing_balance", sa.Numeric(14, 2), server_default="0"),
            sa.Column("books_closing_balance", sa.Numeric(14, 2), server_default="0"),
            sa.Column("difference", sa.Numeric(14, 2), server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("financial_year", sa.String(10), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("finalized_by", sa.Integer(), nullable=True),
            sa.Column("finalized_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    else:
        # A legacy bank_reconciliations table may already exist (older design /
        # _auto_migrate drift). Add the columns this feature needs and relax any
        # legacy NOT NULL columns our ORM does not populate, without dropping data.
        have = {c["name"] for c in insp.get_columns("bank_reconciliations")}
        add = [
            ("reconciliation_number", sa.String(30), None),
            ("account_code", sa.String(20), "BANK"),
            ("period_from", sa.Date(), None),
            ("period_to", sa.Date(), None),
            ("statement_closing_balance", sa.Numeric(14, 2), "0"),
            ("books_closing_balance", sa.Numeric(14, 2), "0"),
            ("financial_year", sa.String(10), None),
            ("finalized_by", sa.Integer(), None),
            ("finalized_at", sa.DateTime(), None),
            ("updated_by", sa.Integer(), None),
        ]
        for name, typ, default in add:
            if name not in have:
                kw = {"server_default": default} if default is not None else {}
                op.add_column("bank_reconciliations", sa.Column(name, typ, nullable=True, **kw))
        for col, ddl in [("statement_month", "VARCHAR(7)"), ("bank_account_code", "VARCHAR(20)")]:
            if col in have:
                try:
                    op.execute(f"ALTER TABLE bank_reconciliations MODIFY `{col}` {ddl} NULL")
                except Exception:
                    pass

    if "bank_reconciliation_lines" not in tables:
        op.create_table(
            "bank_reconciliation_lines",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("reconciliation_id", sa.Integer(), nullable=False),
            sa.Column("bank_date", sa.Date(), nullable=True),
            sa.Column("bank_description", sa.String(255), nullable=True),
            sa.Column("bank_debit", sa.Numeric(14, 2), server_default="0"),
            sa.Column("bank_credit", sa.Numeric(14, 2), server_default="0"),
            sa.Column("bank_reference", sa.String(100), nullable=True),
            sa.Column("journal_line_id", sa.BigInteger(), nullable=True),
            sa.Column("previous_journal_line_id", sa.BigInteger(), nullable=True),
            sa.Column("match_type", sa.String(20), nullable=False, server_default="unmatched"),
            sa.Column("match_reason", sa.String(200), nullable=True),
            sa.Column("is_adjustment", sa.Boolean(), server_default=sa.false()),
            sa.Column("adjustment_journal_entry_id", sa.BigInteger(), nullable=True),
            sa.Column("matched_by", sa.Integer(), nullable=True),
            sa.Column("matched_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Index("ix_recon_line_recon", "reconciliation_id"),
        )

    if "journal_lines" in tables:
        have = {c["name"] for c in insp.get_columns("journal_lines")}
        if "is_reconciled" not in have:
            op.add_column(
                "journal_lines",
                sa.Column("is_reconciled", sa.Boolean(), nullable=True, server_default=sa.false()),
            )
        if "reconciliation_id" not in have:
            op.add_column(
                "journal_lines",
                sa.Column("reconciliation_id", sa.Integer(), nullable=True),
            )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "journal_lines" in tables:
        have = {c["name"] for c in insp.get_columns("journal_lines")}
        if "reconciliation_id" in have:
            op.drop_column("journal_lines", "reconciliation_id")
        if "is_reconciled" in have:
            op.drop_column("journal_lines", "is_reconciled")

    if "bank_reconciliation_lines" in tables:
        op.drop_table("bank_reconciliation_lines")
    if "bank_reconciliations" in tables:
        op.drop_table("bank_reconciliations")
