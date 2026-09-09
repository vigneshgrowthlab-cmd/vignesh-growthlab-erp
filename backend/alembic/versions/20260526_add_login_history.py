"""add login_history table

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'login_history',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('username', sa.String(50), nullable=False, index=True),
        sa.Column('full_name', sa.String(100), nullable=True),
        sa.Column('login_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('logout_at', sa.DateTime(), nullable=True),
        sa.Column('session_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('login_history')
