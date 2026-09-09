"""add state_code to warehouses + backfill state codes from names

Warehouses had no state_code at all; customer/vendor addresses frequently had
NULL (or, in one case, a wrong) state_code while carrying a valid state NAME.
GST intra/inter determination compares state CODES, so this adds the warehouse
column and backfills every table's state_code from its resolved state name
(filling NULLs and correcting mismatches where the name resolves).

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-06-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.utils.helpers import resolve_state_code


revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def _backfill(conn, table):
    rows = conn.execute(sa.text(f"SELECT id, state, state_code FROM {table}")).fetchall()
    for rid, state, code in rows:
        rc = resolve_state_code(state)
        if rc is None:
            continue
        if code is None or int(code) != rc:
            conn.execute(sa.text(f"UPDATE {table} SET state_code = :c WHERE id = :i"),
                         {"c": rc, "i": rid})


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "warehouses" in tables:
        have = {c["name"] for c in insp.get_columns("warehouses")}
        if "state_code" not in have:
            op.add_column("warehouses", sa.Column("state_code", sa.SmallInteger(), nullable=True))
    for table in ("warehouses", "customer_addresses", "customers", "vendor_addresses", "vendors"):
        if table in tables:
            _backfill(conn, table)


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "warehouses" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("warehouses")}
        if "state_code" in have:
            op.drop_column("warehouses", "state_code")
