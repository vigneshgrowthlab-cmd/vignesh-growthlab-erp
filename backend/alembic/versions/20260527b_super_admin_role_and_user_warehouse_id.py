"""super_admin role and users.warehouse_id (merge migration)

Two related cleanups:

1. Replace the magic-string super-admin check (`username == 'system_administrator'`)
   with a real role. Promote any existing user named ``system_administrator``
   to ``role = 'super_admin'``. The username is left untouched so existing
   logins keep working; only the role is changed.

2. Bring ``users.warehouse_id`` into the canonical schema. The column was
   previously only added by ``app.main._auto_migrate()`` on startup, so the
   ORM model didn't know about it and every reader had to drop into raw SQL.
   This migration adds it idempotently (matches what auto_migrate did — no
   FK at the DB level — but now Alembic owns it).

Both steps are written defensively so they're safe on databases where
``_auto_migrate()`` already ran the column add, or where no
``system_administrator`` user exists yet.

Also acts as a merge migration: the alembic tree previously had two heads
(``1a2b3c4d5e6f`` add_dc_approval_audit and ``a7b8c9d0e1f2``
drop_zero_date_defaults), both branching off ``f6a7b8c9d0e1``. Declaring
``down_revision`` as a tuple merges them so ``alembic upgrade head``
resolves to a single target.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2, 1a2b3c4d5e6f
Create Date: 2026-05-27
"""
from alembic import op


revision = 'b8c9d0e1f2a3'
down_revision = ('a7b8c9d0e1f2', '1a2b3c4d5e6f')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add users.warehouse_id idempotently — auto_migrate may have already
    #    added it. MariaDB supports ADD COLUMN IF NOT EXISTS.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS warehouse_id INT NULL")

    # 2. Promote any existing system_administrator user to the new role.
    #    Safe on fresh DBs where the user doesn't exist (UPDATE affects 0 rows).
    op.execute(
        "UPDATE users SET role='super_admin' "
        "WHERE username='system_administrator'"
    )


def downgrade() -> None:
    # Demote super-admins back to plain admin (closest pre-migration role).
    op.execute("UPDATE users SET role='admin' WHERE role='super_admin'")
    # Leave users.warehouse_id in place — _auto_migrate() adds it anyway and
    # dropping it would lose warehouse assignments.
