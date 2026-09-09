"""add workflow status/transition masters (advisory layer)

Phase 5c of the configuration-driven parameter system (see
docs/CONFIG_MIGRATION_PLAN.md). Adds:
  workflow_status_master      - configurable labels/colours per entity status
  workflow_transition_master  - allowed transitions (+ optional required role)

Used in ADVISORY mode only: the Python status enums remain the structural
source of truth; a disallowed transition is logged, never blocked. Empty tables
=> permissive (everything allowed), so this is a no-op until seeded.

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "workflow_status_master" not in tables:
        op.create_table(
            "workflow_status_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("entity", sa.String(40), nullable=False),
            sa.Column("status_code", sa.String(30), nullable=False),
            sa.Column("label", sa.String(60), nullable=False),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("entity", "status_code", name="uq_workflow_status"),
        )
        op.create_index("ix_workflow_status_entity", "workflow_status_master", ["entity"])

    if "workflow_transition_master" not in tables:
        op.create_table(
            "workflow_transition_master",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("entity", sa.String(40), nullable=False),
            sa.Column("from_status", sa.String(30), nullable=False),
            sa.Column("to_status", sa.String(30), nullable=False),
            sa.Column("required_role", sa.String(30), nullable=True),
            sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_workflow_transition_entity", "workflow_transition_master", ["entity"])


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    for t in ("workflow_transition_master", "workflow_status_master"):
        if t in tables:
            op.drop_table(t)
