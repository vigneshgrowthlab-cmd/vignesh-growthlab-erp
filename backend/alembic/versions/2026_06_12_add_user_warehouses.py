"""add user_warehouses table for admin multi-warehouse assignment

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-06-12

"""
from alembic import op
import sqlalchemy as sa

revision = 'c7d8e9f0a1b2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_warehouses',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('warehouse_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('assigned_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'warehouse_id'),
    )
    op.create_index('ix_user_warehouses_user_id', 'user_warehouses', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_user_warehouses_user_id', table_name='user_warehouses')
    op.drop_table('user_warehouses')
