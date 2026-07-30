from __future__ import annotations

from uuid import uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from questr.common.enums import AuditAction, UserRole
from questr.domains.users.repository import (
    AuditLog,
    AuditLogRepository,
)


@pytest.mark.usefixtures('db_session')
class TestAuditLogRepository:
    """Integration tests for AuditLogRepository against real PostgreSQL."""

    @pytest.fixture
    def audit_repo(self, db_session: AsyncSession) -> AuditLogRepository:
        return AuditLogRepository(session=db_session)

    async def test_create_persists_impersonation_start(
        self, audit_repo: AuditLogRepository
    ) -> None:
        """An IMPERSONATION_START row persists with correct columns."""
        actor_id = uuid7()
        target_id = uuid7()
        entry = await audit_repo.create(
            AuditLog(
                action=AuditAction.IMPERSONATION_START,
                actor_id=actor_id,
                target_id=target_id,
                impersonator_id=actor_id,
            ),
        )
        assert entry.id is not None
        assert entry.action == AuditAction.IMPERSONATION_START
        assert entry.actor_id == actor_id
        assert entry.target_id == target_id

    async def test_create_persists_role_granted(
        self, audit_repo: AuditLogRepository
    ) -> None:
        """A ROLE_GRANTED row persists with old_role/new_role."""
        actor_id = uuid7()
        target_id = uuid7()
        entry = await audit_repo.create(
            AuditLog(
                action=AuditAction.ROLE_GRANTED,
                actor_id=actor_id,
                target_id=target_id,
                old_role=UserRole.USER,
                new_role=UserRole.SUPERUSER,
            ),
        )
        assert entry.id is not None
        assert entry.old_role == UserRole.USER
        assert entry.new_role == UserRole.SUPERUSER

    async def test_no_update_method_exists(
        self, audit_repo: AuditLogRepository
    ) -> None:
        """AuditLogRepository has no update or delete methods."""
        assert not hasattr(audit_repo, 'update')
        assert not hasattr(audit_repo, 'delete')
