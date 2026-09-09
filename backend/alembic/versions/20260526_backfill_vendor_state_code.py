"""backfill vendors.state_code from gstin

Where a vendor has a GSTIN but no state_code, derive the state_code from
the first 2 digits of the GSTIN (Indian numbering convention). Existing
purchases against these vendors were defaulting to IGST regardless of
location because purchase_service computes gst_type from
`vendor.state_code or 0`.

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-05-26
"""
from alembic import op


revision = 'd4e5f6a7b8c9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MariaDB / MySQL: REGEXP returns 1 on match.
    op.execute("""
        UPDATE vendors
        SET state_code = CAST(SUBSTRING(gstin, 1, 2) AS UNSIGNED)
        WHERE state_code IS NULL
          AND gstin IS NOT NULL
          AND gstin <> ''
          AND SUBSTRING(gstin, 1, 2) REGEXP '^[0-9]{2}$'
    """)


def downgrade() -> None:
    # Irreversible — we no longer know which rows were originally NULL.
    pass
