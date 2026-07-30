from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid7

import pytest

from questr.common.enums import UserRole
from questr.common.exceptions import AuthenticationError
from questr.common.permissions import ROLE_PERMISSIONS, Permission
from questr.domains.users.repository import (
    Session as SessionDomain,
)
from questr.domains.users.repository import (
    User as UserDomain,
)
from questr.domains.users.service import SessionService


@pytest.fixture
def mock_session_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    repo.deactivate = AsyncMock()
    return repo


@pytest.fixture
def mock_user_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    return repo


@pytest.fixture
def mock_audit_log_repo() -> MagicMock:
    repo = MagicMock()
    repo.insert = AsyncMock()
    return repo


@pytest.fixture
def mock_login_rate_limiter() -> MagicMock:
    return MagicMock()


@pytest.fixture
def session_service(
    mock_session_repo: MagicMock,
    mock_user_repo: MagicMock,
    mock_audit_log_repo: MagicMock,
    mock_login_rate_limiter: MagicMock,
) -> SessionService:
    return SessionService(
        user_repo=mock_user_repo,
        session_repo=mock_session_repo,
        audit_repo=mock_audit_log_repo,
        login_rate_limiter=mock_login_rate_limiter,
    )


class TestImpersonationTimebox:
    """T-025: 60-minute absolute time-box enforced by validate_session."""

    @pytest.mark.asyncio
    async def test_impersonation_session_expired_by_timebox(
        self,
        session_service: SessionService,
        mock_session_repo: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """An impersonation session past absolute_expires_at is rejected."""
        now = datetime.now(timezone.utc)
        user_id = uuid7()

        # Session with absolute_expires_at in the past (created 61 min
        # ago with a 60-min time-box).
        session = SessionDomain(
            id=uuid7(),
            user_id=user_id,
            is_active=True,
            issued_at=now - timedelta(minutes=61),
            last_activity=now - timedelta(minutes=61),
            expires_at=now - timedelta(minutes=31),
            absolute_expires_at=now - timedelta(minutes=1),
            remember_me=False,
            ip_address='127.0.0.1',
            user_agent='pytest',
            csrf_token_hash='x' * 64,
            impersonator_id=uuid7(),
            impersonator_session_id=uuid7(),
        )
        mock_session_repo.get_by_id.return_value = session
        mock_user_repo.get_by_id.return_value = UserDomain(
            id=user_id, username='target'
        )

        with pytest.raises(AuthenticationError, match='Session expired'):
            await session_service.validate_session(session.id)

        mock_session_repo.deactivate.assert_called_once_with(session.id)


class TestNoNesting:
    """T-026: Structural no-nesting via permission system."""

    @pytest.mark.asyncio
    async def test_impersonated_user_cannot_start_impersonation(
        self,
    ) -> None:
        """An impersonated USER principal holds no permissions.

        Since the effective user of an impersonated session has role
        USER, the permission check structurally prevents nesting.
        """
        perms = ROLE_PERMISSIONS[UserRole.USER]
        assert Permission.IMPERSONATE_USERS not in perms
        assert Permission.MANAGE_ROLES not in perms
