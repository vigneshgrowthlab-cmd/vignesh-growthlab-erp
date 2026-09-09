"""add transport fields to invoices and company_settings

Revision ID: 20260617_transport
Revises: d8e9f0a1b2c3
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = '20260617_transport'
down_revision = 'f0a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('invoices') as batch_op:
        batch_op.add_column(sa.Column('transporter_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('transporter_name', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('show_transport_on_print', sa.Boolean(), nullable=True))
        batch_op.create_foreign_key(
            'fk_invoices_transporter_id', 'transporters',
            ['transporter_id'], ['id']
        )

    with op.batch_alter_table('company_settings') as batch_op:
        batch_op.add_column(sa.Column('show_transport_on_invoice', sa.Boolean(), nullable=True, server_default=sa.true()))
        batch_op.add_column(sa.Column('show_transport_on_challan', sa.Boolean(), nullable=True, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('invoices') as batch_op:
        batch_op.drop_constraint('fk_invoices_transporter_id', type_='foreignkey')
        batch_op.drop_column('show_transport_on_print')
        batch_op.drop_column('transporter_name')
        batch_op.drop_column('transporter_id')

    with op.batch_alter_table('company_settings') as batch_op:
        batch_op.drop_column('show_transport_on_challan')
        batch_op.drop_column('show_transport_on_invoice')
