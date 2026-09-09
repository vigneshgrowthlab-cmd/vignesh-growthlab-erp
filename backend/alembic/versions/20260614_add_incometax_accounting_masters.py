"""add income-tax / accounting masters (tds_section, aging_bucket, coa_map)

Phase 2 of the configuration-driven parameter system (see
docs/CONFIG_MIGRATION_PLAN.md). Effective-dated masters:
  tds_section_master   - TDS sections + rate + thresholds (Income Tax Act)
  aging_bucket_master  - receivables ageing boundaries + priority weights
  chart_of_account_map - logical account code -> (type, default name)

Resolution falls back to the in-code constants (schema default "194C",
30/60/90 ageing buckets, helpers._ACCOUNT_TYPE_MAP) when a master is empty, so
shipping these tables empty is a no-op.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
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

    if "tds_section_master" not in tables:
        op.create_table(
            "tds_section_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("section_code", sa.String(10), nullable=False),
            sa.Column("description", sa.String(120), nullable=True),
            sa.Column("rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("threshold_single", sa.Numeric(14, 2), nullable=True),
            sa.Column("threshold_annual", sa.Numeric(14, 2), nullable=True),
            sa.Column("deductee_type", sa.String(20), nullable=True),
            *_temporal_cols(),
        )
        op.create_index("ix_tds_section_master_window", "tds_section_master", ["section_code", "effective_from"])

    if "aging_bucket_master" not in tables:
        op.create_table(
            "aging_bucket_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(40), nullable=True),
            sa.Column("from_days", sa.Integer(), nullable=False),
            sa.Column("to_days", sa.Integer(), nullable=True),
            sa.Column("weight", sa.Numeric(5, 2), nullable=False, server_default="1"),
            *_temporal_cols(),
        )
        op.create_index("ix_aging_bucket_master_window", "aging_bucket_master", ["seq", "effective_from"])

    if "chart_of_account_map" not in tables:
        op.create_table(
            "chart_of_account_map",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(30), nullable=False),
            sa.Column("account_type", sa.String(30), nullable=False),
            sa.Column("default_name", sa.String(120), nullable=False),
            *_temporal_cols(),
        )
        op.create_index("ix_chart_of_account_map_code", "chart_of_account_map", ["code", "effective_from"])


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    for t in ("chart_of_account_map", "aging_bucket_master", "tds_section_master"):
        if t in tables:
            op.drop_table(t)
