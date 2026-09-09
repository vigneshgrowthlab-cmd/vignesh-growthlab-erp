"""add DPDP tables (consent, retention, erasure)

Phase 4b of the configuration-driven parameter system (see
docs/CONFIG_MIGRATION_PLAN.md). Adds the DPDP Act compliance capability that was
entirely absent:
  consent_purpose       - catalog of processing purposes
  consent_record        - grant/withdrawal per data principal
  data_retention_policy - per-entity retention window (INERT until is_active)
  erasure_request       - right-to-erasure request + processing audit trail

All tables are additive; no existing table or behaviour changes. Retention
policies ship inactive (is_active=0) so nothing is ever auto-purged.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "consent_purpose" not in tables:
        op.create_table(
            "consent_purpose",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purpose_key", sa.String(50), nullable=False, unique=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("requires_explicit", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if "consent_record" not in tables:
        op.create_table(
            "consent_record",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("principal_type", sa.String(20), nullable=False),
            sa.Column("principal_id", sa.Integer(), nullable=False),
            sa.Column("purpose_key", sa.String(50), nullable=False),
            sa.Column("purpose_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(15), nullable=False, server_default="granted"),
            sa.Column("granted_at", sa.DateTime(), nullable=True),
            sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
            sa.Column("source", sa.String(50), nullable=True),
            sa.Column("notes", sa.String(255), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_consent_record_principal", "consent_record",
                        ["principal_type", "principal_id", "purpose_key"])

    if "data_retention_policy" not in tables:
        op.create_table(
            "data_retention_policy",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("entity", sa.String(50), nullable=False),
            sa.Column("retention_days", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(20), nullable=False, server_default="delete"),
            sa.Column("legal_basis", sa.String(200), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("notes", sa.String(255), nullable=True),
            sa.Column("effective_from", sa.Date(), nullable=True),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if "erasure_request" not in tables:
        op.create_table(
            "erasure_request",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("subject_type", sa.String(20), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.Column("subject_label", sa.String(120), nullable=True),
            sa.Column("status", sa.String(15), nullable=False, server_default="pending"),
            sa.Column("reason", sa.String(255), nullable=True),
            sa.Column("requested_by", sa.Integer(), nullable=True),
            sa.Column("requested_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("processed_by", sa.Integer(), nullable=True),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("result_note", sa.String(255), nullable=True),
        )
        op.create_index("ix_erasure_request_subject", "erasure_request",
                        ["subject_type", "subject_id"])


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    for t in ("erasure_request", "data_retention_policy", "consent_record", "consent_purpose"):
        if t in tables:
            op.drop_table(t)
