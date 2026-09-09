"""add GST structured masters (gst_rate_master, state_master, uqc_master)

Phase 1b of the configuration-driven parameter system (see
docs/CONFIG_MIGRATION_PLAN.md). Effective-dated masters that replace the
hardcoded literals in app/utils/irp_validation.py (VALID_GST_RATES,
VALID_STATE_CODES, UQC_MAP) and the hardcoded /gst-rates and /states endpoint
lists. Resolution falls back to the in-code constants when a master is empty,
so shipping these tables empty is a no-op.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-06-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None


def _temporal_cols():
    return [
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(15), nullable=False, server_default="active"),
        sa.Column("regulatory_reference", sa.String(200), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "gst_rate_master" not in tables:
        op.create_table(
            "gst_rate_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("label", sa.String(80), nullable=True),
            sa.Column("is_selectable", sa.Boolean(), nullable=False, server_default="1"),
            *_temporal_cols(),
        )
        op.create_index("ix_gst_rate_master_window", "gst_rate_master", ["rate", "effective_from"])

    if "state_master" not in tables:
        op.create_table(
            "state_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("state_code", sa.SmallInteger(), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("is_selectable", sa.Boolean(), nullable=False, server_default="1"),
            *_temporal_cols(),
        )
        op.create_index("ix_state_master_window", "state_master", ["state_code", "effective_from"])

    if "uqc_master" not in tables:
        op.create_table(
            "uqc_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("unit_text", sa.String(30), nullable=False),
            sa.Column("uqc_code", sa.String(10), nullable=False),
            *_temporal_cols(),
        )
        op.create_index("ix_uqc_master_window", "uqc_master", ["unit_text", "effective_from"])


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    for t in ("uqc_master", "state_master", "gst_rate_master"):
        if t in tables:
            op.drop_table(t)
