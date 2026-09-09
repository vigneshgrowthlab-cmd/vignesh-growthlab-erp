"""Remove serial-number tracking feature

Drops every column and table related to serial-tracked products:

  * products.serial_tracking          (per-product opt-in flag)
  * stock_entries.serial_number       (per FIFO layer)
  * invoice_items.serial_number       (line-item allocation on sale)
  * product_serials                   (serial registry table)

ORM models, Pydantic schemas, the /invoices/serials/available endpoint,
the bulk-upload CSV header, and the ProductFormPage toggle are removed
in the same commit. Any frontend forms that previously sent
``serial_number`` in invoice/purchase line items no longer do so —
Pydantic now rejects the extra field if older clients keep sending it,
which is the intended behaviour for a fully removed feature.

No data preservation: per the product decision, all serial history is
wiped. Historical invoice prints from before this migration ran lose
the per-line S/N display; nothing else changes.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-05-27
"""
from alembic import op


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MariaDB supports IF EXISTS clauses on ALTER and DROP — makes the
    # migration tolerant of databases where _auto_migrate() never added
    # the columns in the first place.
    op.execute("ALTER TABLE products       DROP COLUMN IF EXISTS serial_tracking")
    op.execute("ALTER TABLE stock_entries  DROP COLUMN IF EXISTS serial_number")
    op.execute("ALTER TABLE invoice_items  DROP COLUMN IF EXISTS serial_number")
    op.execute("DROP TABLE IF EXISTS product_serials")


def downgrade() -> None:
    # Recreate the columns and table empty. Existing data is gone — the
    # downgrade restores schema shape only, not the history.
    op.execute(
        "ALTER TABLE products "
        "ADD COLUMN IF NOT EXISTS serial_tracking BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE stock_entries "
        "ADD COLUMN IF NOT EXISTS serial_number VARCHAR(100) NULL"
    )
    op.execute(
        "ALTER TABLE invoice_items "
        "ADD COLUMN IF NOT EXISTS serial_number VARCHAR(100) NULL"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS product_serials (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            warehouse_id INT NULL,
            serial_number VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'in_stock',
            purchase_item_id INT NULL,
            invoice_item_id INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
