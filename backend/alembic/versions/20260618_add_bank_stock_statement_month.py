"""sync bank_stock_statements with ORM model

The BankStockStatement ORM model declares statement_month, margin_percent,
locked_at, locked_by, excel_path and pdf_path, but the live table is a
legacy variant that never got them (it carries drawing_power_margin_pct
instead of margin_percent) — every SELECT against bank_stock_statements
failed with 1054. Add the missing columns, backfill statement_month from
statement_date as YYYY-MM (then enforce NOT NULL to match the model) and
margin_percent from the legacy drawing_power_margin_pct where available.
Also relax legacy NOT NULL columns the ORM does not populate (e.g.
bank_account_name) so inserts don't fail with 1364, without dropping data.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None

ADDED = [
    ("statement_month", sa.String(7)),
    ("margin_percent", sa.Numeric(5, 2)),
    ("locked_at", sa.DateTime()),
    ("locked_by", sa.Integer()),
    ("excel_path", sa.String(255)),
    ("pdf_path", sa.String(255)),
]


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "bank_stock_statements" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("bank_stock_statements")}

    for name, typ in ADDED:
        if name not in have:
            op.add_column("bank_stock_statements", sa.Column(name, typ, nullable=True))

    op.execute(
        "UPDATE bank_stock_statements "
        "SET statement_month = DATE_FORMAT(statement_date, '%%Y-%%m') "
        "WHERE statement_month IS NULL"
    )
    op.execute(
        "ALTER TABLE bank_stock_statements MODIFY statement_month VARCHAR(7) NOT NULL"
    )

    if "drawing_power_margin_pct" in have:
        op.execute(
            "UPDATE bank_stock_statements "
            "SET margin_percent = drawing_power_margin_pct "
            "WHERE margin_percent IS NULL"
        )
    op.execute(
        "UPDATE bank_stock_statements SET margin_percent = 25.00 "
        "WHERE margin_percent IS NULL"
    )

    # Legacy NOT NULL columns the ORM does not populate block every INSERT
    # with 1364; relax them in place, keeping type and data.
    model_cols = {"id"} | {name for name, _ in ADDED} | {
        "statement_date", "stock_value", "debtors_value", "total_value",
        "drawing_power", "is_locked", "bank_name", "account_number",
        "statement_number", "cc_limit", "stock_breakup", "debtor_breakup",
        "financial_year", "notes", "created_at", "updated_at",
        "created_by", "updated_by",
    }
    rows = conn.execute(sa.text(
        "SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bank_stock_statements' "
        "AND IS_NULLABLE = 'NO' AND COLUMN_KEY != 'PRI'"
    )).fetchall()
    for col, col_type in rows:
        if col not in model_cols:
            op.execute(
                f"ALTER TABLE bank_stock_statements MODIFY `{col}` {col_type} NULL"
            )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "bank_stock_statements" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("bank_stock_statements")}
    for name, _ in ADDED:
        if name in have:
            op.drop_column("bank_stock_statements", name)
