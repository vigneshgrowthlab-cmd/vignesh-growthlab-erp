"""add refresh_token_hash to active_sessions for multi-session support

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'e9f0a1b2c3d4'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    have = {c["name"] for c in insp.get_columns("active_sessions")}
    if "refresh_token_hash" not in have:
        op.add_column('active_sessions', sa.Column('refresh_token_hash', sa.String(64), nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    have = {c["name"] for c in insp.get_columns("active_sessions")}
    if "refresh_token_hash" in have:
        op.drop_column('active_sessions', 'refresh_token_hash')
