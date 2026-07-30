"""add_impersonation_and_audit

Revision ID: 003
Revises: b2f0b1a8ca4d
Create Date: 2026-07-29 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, Sequence[str], None] = 'b2f0b1a8ca4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add impersonation columns to sessions
    op.add_column(
        'sessions',
        sa.Column('impersonator_id', sa.UUID(), nullable=True),
    )
    op.add_column(
        'sessions',
        sa.Column('impersonator_session_id', sa.UUID(), nullable=True),
    )

    # Create audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('target_id', sa.UUID(), nullable=True),
        sa.Column('impersonator_id', sa.UUID(), nullable=True),
        sa.Column('impersonator_session_id', sa.UUID(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('old_role', sa.String(20), nullable=True),
        sa.Column('new_role', sa.String(20), nullable=True),
        sa.Column('reason', sa.String(512), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_audit_log_action', 'audit_log', ['action'], unique=False
    )
    op.create_index(
        'idx_audit_log_actor_id', 'audit_log', ['actor_id'], unique=False
    )
    op.create_index(
        'idx_audit_log_target_id', 'audit_log', ['target_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('audit_log')
    op.drop_column('sessions', 'impersonator_session_id')
    op.drop_column('sessions', 'impersonator_id')
