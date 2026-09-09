"""widen categories.prefix to VARCHAR(10)

The Category ORM model and the CategoryCreate/CategoryUpdate Pydantic schemas
all allow a prefix up to 10 chars, but the live MariaDB column drifted to
varchar(4). Creating/updating a category with a 5-10 char prefix raised
"Data too long for column 'prefix'" -> HTTP 500. Widen to VARCHAR(10) NOT NULL
to match the model.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "categories" not in insp.get_table_names():
        return
    col = next((c for c in insp.get_columns("categories") if c["name"] == "prefix"), None)
    if col is None:
        return
    length = getattr(col["type"], "length", None)
    if length is not None and length >= 10:
        return
    op.alter_column(
        "categories",
        "prefix",
        existing_type=sa.String(length or 4),
        type_=sa.String(10),
        existing_nullable=False,
    )


def downgrade():
    # No-op: narrowing back to VARCHAR(4) would truncate existing data.
    pass
