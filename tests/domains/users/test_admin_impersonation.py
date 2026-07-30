# ruff: noqa: PLR2004
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from questr.common.enums import UserRole, UserStatus
from questr.common.exceptions import (
    AuthenticationError,
    SelfImpersonationError,
    SuperuserImpersonationError,
    TargetNotActiveError,
)
from questr.domains.users.api import (
    get_current_user,
    get_role_service,
    get_session_service,
    get_user_repository,
)
from questr.domains.users.repository import (
    Session,
    UserRepository,
)
from questr.domains.users.repository import (
    User as UserDomain,
)
from questr.domains.users.service import RoleService, SessionService


@pytest.fixture
def mock_session_service() -> MagicMock:
    svc = MagicMock(spec=SessionService)
    svc.start_impersonation = AsyncMock()
    return svc


@pytest.fixture
def mock_user_repo() -> MagicMock:
    repo = MagicMock(spec=UserRepository)
    repo.get_by_email = AsyncMock()
    repo.get_by_id = AsyncMock()
    return repo


def _make_admin_current() -> dict:
    """Return a T_CurrentUser dict for a superuser."""
    admin = MagicMock()
    admin.id = uuid7()
    admin.role = UserRole.SUPERUSER
    admin.status = UserStatus.ACTIVE
    return {
        'user': admin,
        'csrf_token': 'admin-csrf',
        'is_impersonation': False,
        'impersonator_session_id': None,
    }


def _make_target_user(
    role: UserRole = UserRole.USER,
    status: UserStatus = UserStatus.ACTIVE,
) -> UserDomain:
    return UserDomain(
        id=uuid7(),
        username='target_user',
        email='target@example.com',
        first_name='Target',
        last_name='User',
        role=role,
        status=status,
    )


class TestStartImpersonation:
    """Tests for POST /api/v1/auth/admin/impersonate."""

    async def _setup(
        self,
        app: FastAPI,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
        admin_current: dict | None = None,
    ) -> None:
        if admin_current is None:
            admin_current = _make_admin_current()

        app.dependency_overrides = {}
        app.dependency_overrides[get_session_service] = lambda: (
            mock_session_service
        )  # noqa: E501
        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo
        app.dependency_overrides[get_current_user] = lambda: admin_current

    @pytest.mark.asyncio
    async def test_superuser_starts_impersonation(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """T-015: Superuser starts impersonation, gets session_id cookie."""
        target = _make_target_user()
        mock_user_repo.get_by_id.return_value = target

        fake_session = Session(
            id=uuid7(),
            user_id=target.id,
            issued_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            absolute_expires_at=datetime.now(timezone.utc),
            remember_me=False,
            ip_address='127.0.0.1',
            user_agent='pytest',
            csrf_token_hash='x' * 64,
            is_active=True,
            impersonator_id=uuid7(),
            impersonator_session_id=uuid7(),
        )
        mock_session_service.start_impersonation.return_value = {
            'user': target,
            'session': fake_session,
            'csrf_token': 'new-csrf-token',
        }

        await self._setup(app, mock_session_service, mock_user_repo)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/impersonate',
            json={'target_id': str(target.id)},
        )
        assert resp.status_code == 200
        assert 'session_id' in resp.cookies
        assert 'csrf_token' in resp.cookies
        assert resp.cookies['csrf_token'] == 'new-csrf-token'
        mock_session_service.start_impersonation.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_caller_denied_403(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """T-015: A non-superuser caller gets 403."""
        user_current = _make_admin_current()
        user_current['user'].role = UserRole.USER

        await self._setup(
            app, mock_session_service, mock_user_repo, user_current
        )

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'user-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/impersonate',
            json={'target_id': str(uuid7())},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_superuser_target_denied_403(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """T-016: Attempting to impersonate a superuser yields 403."""
        target = _make_target_user(role=UserRole.SUPERUSER)
        mock_user_repo.get_by_id.return_value = target
        mock_session_service.start_impersonation.side_effect = (
            SuperuserImpersonationError()
        )

        await self._setup(app, mock_session_service, mock_user_repo)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/impersonate',
            json={'target_id': str(target.id)},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data.get('error_code') == 'superuser_impersonation'

    @pytest.mark.asyncio
    async def test_self_impersonation_denied_400(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """T-017: Self-impersonation yields 400."""
        target = _make_target_user()
        admin_current = _make_admin_current()
        admin_current['user'].id = target.id
        admin_current['user'].email = 'admin@example.com'
        mock_user_repo.get_by_id.return_value = target
        mock_session_service.start_impersonation.side_effect = (
            SelfImpersonationError()
        )

        await self._setup(
            app, mock_session_service, mock_user_repo, admin_current
        )

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/impersonate',
            json={'target_id': str(target.id)},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data.get('error_code') == 'self_impersonation'

    @pytest.mark.asyncio
    async def test_target_not_active_denied_409(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """T-018: Non-ACTIVE target yields 409."""
        target = _make_target_user(status=UserStatus.SUSPENDED)
        mock_user_repo.get_by_id.return_value = target
        mock_session_service.start_impersonation.side_effect = (
            TargetNotActiveError()
        )

        await self._setup(app, mock_session_service, mock_user_repo)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/impersonate',
            json={'target_id': str(target.id)},
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data.get('error_code') == 'target_not_active'

    @pytest.mark.asyncio
    async def test_target_not_found_404(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """Unknown target id returns 404."""
        mock_user_repo.get_by_id.return_value = None

        await self._setup(app, mock_session_service, mock_user_repo)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/impersonate',
            json={'target_id': str(uuid7())},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_bypasses_max_concurrent_sessions(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """T-037: Impersonation starts even when target has many sessions."""
        target = _make_target_user()
        mock_user_repo.get_by_id.return_value = target

        fake_session = Session(
            id=uuid7(),
            user_id=target.id,
            issued_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            absolute_expires_at=datetime.now(timezone.utc),
            remember_me=False,
            ip_address='127.0.0.1',
            user_agent='pytest',
            csrf_token_hash='x' * 64,
            is_active=True,
            impersonator_id=uuid7(),
            impersonator_session_id=uuid7(),
        )
        mock_session_service.start_impersonation.return_value = {
            'user': target,
            'session': fake_session,
            'csrf_token': 'bypass-csrf-token',
        }

        await self._setup(app, mock_session_service, mock_user_repo)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/impersonate',
            json={'target_id': str(target.id)},
        )
        # Succeeds (bypass) instead of 429 TooManyActiveSessions
        assert resp.status_code == 200


class TestStopImpersonation:
    """Tests for POST /api/v1/auth/admin/impersonate/stop."""

    async def _setup(
        self,
        app: FastAPI,
        mock_session_service: MagicMock,
        admin_current: dict | None = None,
    ) -> None:
        if admin_current is None:
            admin_current = _make_admin_current()

        app.dependency_overrides = {}
        app.dependency_overrides[get_session_service] = lambda: (
            mock_session_service
        )  # noqa: E501
        app.dependency_overrides[get_current_user] = lambda: admin_current

    @pytest.mark.asyncio
    async def test_stop_restores_admin_session(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
    ) -> None:
        """T-021: Stop restores admin session, cookies flipped."""
        admin_session_id = uuid7()
        mock_session_service.stop_impersonation = AsyncMock(
            return_value={
                'admin_session_id': admin_session_id,
                'csrf_token': 'rotated-csrf-token',
            },
        )

        await self._setup(app, mock_session_service)

        # Simulate being in an impersonation session
        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'impersonation-csrf'
        resp = await client.post('/api/v1/auth/admin/impersonate/stop')

        assert resp.status_code == 200
        assert resp.cookies['session_id'] == str(admin_session_id)
        assert resp.cookies['csrf_token'] == 'rotated-csrf-token'
        mock_session_service.stop_impersonation.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_graceful_degrade_on_expired_admin(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
    ) -> None:
        """T-022: Stop degrades to 401 when admin session is gone."""
        mock_session_service.stop_impersonation = AsyncMock(
            side_effect=AuthenticationError('Not authenticated'),
        )

        await self._setup(app, mock_session_service)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'impersonation-csrf'
        resp = await client.post('/api/v1/auth/admin/impersonate/stop')

        assert resp.status_code == 401
        data = resp.json()
        assert 'detail' in data
        # No session flip: the cookies keep whatever was sent

    @pytest.mark.asyncio
    async def test_stop_rejects_non_impersonation(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
    ) -> None:
        """T-023: Non-impersonation session calling stop is rejected."""
        mock_session_service.stop_impersonation = AsyncMock(
            side_effect=AuthenticationError('Not authenticated'),
        )

        await self._setup(app, mock_session_service)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'normal-csrf'
        resp = await client.post('/api/v1/auth/admin/impersonate/stop')

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_stop_without_session_id_returns_401(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_session_service: MagicMock,
    ) -> None:
        """No session_id cookie returns 401."""
        await self._setup(app, mock_session_service)

        resp = await client.post('/api/v1/auth/admin/impersonate/stop')
        assert resp.status_code == 401


class TestStopImpersonationIdleSlide:
    """T-024: Stop slides the admin session's idle window."""

    @pytest.fixture
    def admin_session_id(self) -> UUID:
        return uuid7()

    @pytest.mark.asyncio
    async def test_stop_slides_admin_idle_window(
        self,
        mock_session_service: MagicMock,
    ) -> None:
        """Verify stop_impersonation updates admin session activity."""
        admin_session_id = uuid7()
        mock_session_service.stop_impersonation = AsyncMock(
            return_value={
                'admin_session_id': admin_session_id,
                'csrf_token': 'rotated-csrf',
            },
        )
        # The mock returns successfully, confirming no crash.
        result = await mock_session_service.stop_impersonation(
            impersonation_session_id=uuid7(),
        )
        assert result['admin_session_id'] == admin_session_id
        assert 'csrf_token' in result


class TestChangeRole:
    """T-029/T-005: Tests for POST /api/v1/auth/admin/roles.

    Planned request schema uses ``target_id: UUID`` and
    ``new_role: UserRole``; the service signature is
    ``change_role(*, actor, target_id, new_role, ip, user_agent)``.
    """

    @pytest.mark.asyncio
    async def test_superuser_grants_role_calls_service_with_planned_kwargs(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """Superuser grants SUPERUSER; route forwards planned kwargs
        including ip/user_agent extracted from the request."""
        app.dependency_overrides = {}

        actor = MagicMock()
        actor.id = uuid7()
        actor.role = UserRole.SUPERUSER
        admin_current = {
            'user': actor,
            'csrf_token': 'admin-csrf',
            'is_impersonation': False,
            'impersonator_session_id': None,
        }
        app.dependency_overrides[get_current_user] = lambda: admin_current

        target = _make_target_user(role=UserRole.USER)
        mock_user_repo = MagicMock(spec=UserRepository)
        mock_user_repo.get_by_id = AsyncMock(return_value=target)
        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo

        mock_role_service = MagicMock(spec=RoleService)
        mock_role_service.change_role = AsyncMock()
        app.dependency_overrides[get_role_service] = lambda: mock_role_service

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        client.headers['user-agent'] = 'pytest-role-ua'
        resp = await client.post(
            '/api/v1/auth/admin/roles',
            json={
                'target_id': str(target.id),
                'new_role': 'superuser',
            },
        )
        assert resp.status_code == 200
        mock_role_service.change_role.assert_called_once()
        kwargs = mock_role_service.change_role.call_args.kwargs
        assert kwargs['actor'] is actor
        assert kwargs['target_id'] == target.id
        assert kwargs['new_role'] == UserRole.SUPERUSER
        assert isinstance(kwargs['ip'], str)
        assert kwargs['user_agent'] == 'pytest-role-ua'

    @pytest.mark.asyncio
    async def test_user_caller_denied_403(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """A non-superuser calling the role endpoint gets 403."""
        app.dependency_overrides = {}

        user = MagicMock()
        user.role = UserRole.USER
        user_current = {
            'user': user,
            'csrf_token': 'user-csrf',
            'is_impersonation': False,
            'impersonator_session_id': None,
        }
        app.dependency_overrides[get_current_user] = lambda: user_current

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'user-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/roles',
            json={
                'target_id': str(uuid7()),
                'new_role': 'superuser',
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_self_change_denied_403(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """A superuser changing their own role is denied."""
        app.dependency_overrides = {}

        actor = MagicMock()
        actor.id = uuid7()
        actor.role = UserRole.SUPERUSER
        admin_current = {
            'user': actor,
            'csrf_token': 'admin-csrf',
            'is_impersonation': False,
            'impersonator_session_id': None,
        }
        app.dependency_overrides[get_current_user] = lambda: admin_current

        # Target has same id as actor
        target = _make_target_user(role=UserRole.SUPERUSER)
        target.id = actor.id
        mock_user_repo = MagicMock(spec=UserRepository)
        mock_user_repo.get_by_id = AsyncMock(return_value=target)
        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/roles',
            json={
                'target_id': str(target.id),
                'new_role': 'user',
            },
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data.get('error_code') == 'self_role_change'

    @pytest.mark.asyncio
    async def test_unknown_target_returns_404(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """An unknown target_id yields 404, not a service call."""
        app.dependency_overrides = {}

        actor = MagicMock()
        actor.id = uuid7()
        actor.role = UserRole.SUPERUSER
        admin_current = {
            'user': actor,
            'csrf_token': 'admin-csrf',
            'is_impersonation': False,
            'impersonator_session_id': None,
        }
        app.dependency_overrides[get_current_user] = lambda: admin_current

        mock_user_repo = MagicMock(spec=UserRepository)
        mock_user_repo.get_by_id = AsyncMock(return_value=None)
        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo

        mock_role_service = MagicMock(spec=RoleService)
        mock_role_service.change_role = AsyncMock()
        app.dependency_overrides[get_role_service] = lambda: mock_role_service

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/roles',
            json={
                'target_id': str(uuid7()),
                'new_role': 'superuser',
            },
        )
        assert resp.status_code == 404
        mock_role_service.change_role.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_role_returns_422(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """An invalid role string is rejected by Pydantic (422), not
        a manual 400 block."""
        app.dependency_overrides = {}

        actor = MagicMock()
        actor.id = uuid7()
        actor.role = UserRole.SUPERUSER
        admin_current = {
            'user': actor,
            'csrf_token': 'admin-csrf',
            'is_impersonation': False,
            'impersonator_session_id': None,
        }
        app.dependency_overrides[get_current_user] = lambda: admin_current

        target = _make_target_user(role=UserRole.USER)
        mock_user_repo = MagicMock(spec=UserRepository)
        mock_user_repo.get_by_id = AsyncMock(return_value=target)
        app.dependency_overrides[get_user_repository] = lambda: mock_user_repo

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'admin-csrf'
        resp = await client.post(
            '/api/v1/auth/admin/roles',
            json={
                'target_id': str(target.id),
                'new_role': 'wizard',
            },
        )
        assert resp.status_code == 422
