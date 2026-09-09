"""drop zero-date DEFAULTs on date columns

The legacy _auto_migrate() hack in app/main.py forced every entry in its
`make_nullable` list to ``MODIFY COLUMN <col> <type> NULL DEFAULT 0``. For
DATE columns this stores ``'0000-00-00'`` as the default and bleeds into
every INSERT that omits the column. The companion change removes these
DATE columns from `make_nullable`; this migration normalises the existing
defaults and backfills any zero-date rows.

Sister migration: f6a7b8c9d0e1 covers stock_entries.entry_date.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-27
"""
from alembic import op


revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # product_cost_history.effective_date — 42 rows had '0000-00-00' in dev.
    # recorded_at is NOT NULL with a server default of now(), so it's safe
    # as a backfill source.
    op.execute(
        "UPDATE product_cost_history "
        "SET effective_date = DATE(recorded_at) "
        "WHERE effective_date IS NULL OR YEAR(effective_date) = 0"
    )
    op.execute("ALTER TABLE product_cost_history MODIFY COLUMN effective_date DATE NULL DEFAULT NULL")
    op.execute("ALTER TABLE purchases MODIFY COLUMN invoice_date DATE NULL DEFAULT NULL")
    op.execute("ALTER TABLE invoices MODIFY COLUMN invoice_date DATE NULL DEFAULT NULL")


def downgrade() -> None:
    # The previous DEFAULT '0000-00-00' was the bug. No useful state to restore.
    pass
