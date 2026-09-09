"""add config core (config_definitions + config_values)

Phase 0 of the configuration-driven parameter system (see
docs/CONFIG_MIGRATION_PLAN.md). Creates the generic temporal parameter store:

  config_definitions  - catalog of what CAN be configured (metadata/validation)
  config_values       - effective-dated, versioned actual values

No existing table or behaviour is touched. The resolver (ConfigService) falls
back to current config.py / model defaults when no row exists, so shipping
these tables empty is a no-op.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-06-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b0c1d2e3f4a5'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "config_definitions" not in tables:
        op.create_table(
            "config_definitions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("config_key", sa.String(120), nullable=False, unique=True),
            sa.Column("domain", sa.String(30), nullable=False),
            sa.Column("data_type", sa.String(20), nullable=False),
            sa.Column("unit", sa.String(20), nullable=True),
            sa.Column("scope_type", sa.String(30), nullable=False, server_default="global"),
            sa.Column("validation_json", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_regulatory", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("owner_role", sa.String(30), nullable=True, server_default="super_admin"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
        )

    if "config_values" not in tables:
        op.create_table(
            "config_values",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("config_key", sa.String(120), nullable=False),
            sa.Column("scope_value", sa.String(60), nullable=True),
            sa.Column("value_json", sa.Text(), nullable=True),
            sa.Column("value_numeric", sa.Numeric(18, 4), nullable=True),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(15), nullable=False, server_default="active"),
            sa.Column("regulatory_reference", sa.String(200), nullable=True),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_config_values_lookup",
            "config_values",
            ["config_key", "scope_value", "effective_from"],
        )
        op.create_index(
            "ix_config_values_status",
            "config_values",
            ["config_key", "status"],
        )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if "config_values" in tables:
        op.drop_table("config_values")
    if "config_definitions" in tables:
        op.drop_table("config_definitions")
