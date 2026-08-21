"""add_auth_recovery_and_email_change

Revision ID: 004
Revises: 003
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, Sequence[str], None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add previous_email and email_changed_at columns to users
    op.add_column(
        'users',
        sa.Column('previous_email', sa.String(255), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('email_changed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Add new values to the auditaction enum type. Postgres forbids
    # ADD VALUE inside a transaction, hence each runs in an autocommit
    # block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'PASSWORD_CHANGED'")
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'PASSWORD_RESET'")
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'EMAIL_CHANGE_REQUESTED'")
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'EMAIL_CHANGED'")
        op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'EMAIL_CHANGE_REVERTED'")

    # Create password_reset_tokens table
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_password_reset_tokens_user_id'),
        'password_reset_tokens',
        ['user_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_password_reset_tokens_token_hash'),
        'password_reset_tokens',
        ['token_hash'],
        unique=True,
    )

    # Create email_change_requests table
    op.create_table(
        'email_change_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('old_email', sa.String(255), nullable=False),
        sa.Column('new_email', sa.String(255), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revert_token_hash', sa.String(64), nullable=True),
        sa.Column('revert_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip', sa.String(45), nullable=False),
        sa.Column('user_agent', sa.String(512), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_email_change_requests_user_id'),
        'email_change_requests',
        ['user_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_email_change_requests_token_hash'),
        'email_change_requests',
        ['token_hash'],
        unique=True,
    )
    op.create_index(
        op.f('ix_email_change_requests_revert_token_hash'),
        'email_change_requests',
        ['revert_token_hash'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema.

    Note: dropping enum VALUES is not supported in PostgreSQL.
    The new enum values remain on the type after downgrade, which
    is harmless -- they will be cleaned up only when the entire
    migration chain is rolled back to a version before 004.
    """
    op.drop_table('email_change_requests')
    op.drop_table('password_reset_tokens')
    # Columns added in this migration are left intact;
    # downstream downgrades can drop them if needed.
    op.drop_column('users', 'email_changed_at')
    op.drop_column('users', 'previous_email')
