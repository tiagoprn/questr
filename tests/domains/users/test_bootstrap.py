# ruff: noqa: PLR2004
from __future__ import annotations

from uuid import uuid7

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from questr.common.enums import AuditAction, UserRole, UserStatus
from questr.domains.users.repository import (
    User as UserDomain,
)
from questr.domains.users.repository import (
    UserRepository,
)
from questr.infrastructure.orm.models import AuditLogORMModel, UserORMModel


class TestBootstrapPromote:
    """T-033: Out-of-band superuser promotion."""

    @pytest.mark.asyncio
    async def test_promote_sets_role_and_writes_audit(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Promoting a USER sets role to SUPERUSER and writes audit row."""
        user_repo = UserRepository(session=db_session)
        user = UserDomain(
            id=uuid7(),
            username='promote_test',
            email='promote@test.com',
            first_name='Promote',
            last_name='Test',
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        await user_repo.create(user)

        # Execute the promote logic directly (same as the script)
        result = await db_session.execute(
            select(UserORMModel).where(
                UserORMModel.email == 'promote@test.com'
            )
        )
        orm_user = result.scalar_one_or_none()
        assert orm_user is not None
        assert orm_user.role == UserRole.USER

        old_role = orm_user.role.value
        orm_user.role = UserRole.SUPERUSER

        audit_log_id = uuid7()
        audit_entry = AuditLogORMModel(
            id=audit_log_id,
            action=AuditAction.ROLE_GRANTED,
            actor_id=None,
            target_id=orm_user.id,
            old_role=old_role,
            new_role=UserRole.SUPERUSER.value,
        )
        db_session.add(audit_entry)
        await db_session.flush()

        # Verify role changed
        fetched = await user_repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.role == UserRole.SUPERUSER

        # Verify audit row
        audit_entry_db = await db_session.get(AuditLogORMModel, audit_log_id)
        assert audit_entry_db is not None
        assert audit_entry_db.action == AuditAction.ROLE_GRANTED
        assert audit_entry_db.actor_id is None
        assert audit_entry_db.old_role == 'user'
        assert audit_entry_db.new_role == 'superuser'
