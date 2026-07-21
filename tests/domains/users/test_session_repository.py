from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from questr.domains.users.repository import (
    Session,
    SessionRepository,
    UserRepository,
)
from questr.domains.users.repository import (
    User as UserDomain,
)
from tests.domains.users.factories import UserFactory


@pytest.mark.usefixtures('db_session')
class TestSessionRepository:
    """Integration tests for SessionRepository against real PostgreSQL."""

    @pytest.fixture
    def session_repo(self, db_session: AsyncSession) -> SessionRepository:
        return SessionRepository(session=db_session)

    async def test_user_to_domain_carries_created_at(
        self,
        db_session: AsyncSession,
    ) -> None:
        """AC-3: User domain object carries created_at after _to_domain()."""
        user_repo = UserRepository(session=db_session)

        domain_user = UserDomain(
            id=uuid7(),
            username='created_at_test',
            email='created_at@test.com',
            first_name='Created',
            last_name='At',
            password_hash=('$argon2id$v=19$m=65536,t=3,p=4$mockhash'),
        )
        created = await user_repo.create(domain_user)
        assert created.created_at is not None
        assert isinstance(created.created_at, datetime)

    async def _create_user(self, db_session: AsyncSession) -> object:
        """Helper to create a persisted user."""
        user = UserFactory()
        db_session.add(user)
        await db_session.flush()
        return user

    async def _build_session(
        self, user_id: object, **kwargs: object
    ) -> Session:
        """Build a Session with useful defaults."""
        now = datetime.now(timezone.utc)
        fields = dict(
            user_id=user_id,
            issued_at=now,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
            absolute_expires_at=now + timedelta(hours=8),
            remember_me=False,
            ip_address='127.0.0.1',
            user_agent='pytest',
            csrf_token_hash='a' * 64,
            is_active=True,
        )
        fields.update(kwargs)
        return Session(**fields)

    async def test_create_and_get_by_id_roundtrip(
        self,
        session_repo: SessionRepository,
        db_session: AsyncSession,
    ) -> None:
        """AC-2: create and get_by_id roundtrip."""
        user = await self._create_user(db_session)
        session = await self._build_session(user.id)
        created = await session_repo.create(session)

        assert created.id is not None

        fetched = await session_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.user_id == user.id
        assert fetched.is_active is True
        assert fetched.remember_me is False

    async def test_deactivate_sets_is_active_false(
        self,
        session_repo: SessionRepository,
        db_session: AsyncSession,
    ) -> None:
        """AC-2: deactivate sets is_active to False."""
        user = await self._create_user(db_session)
        session = await self._build_session(user.id)
        created = await session_repo.create(session)

        result = await session_repo.deactivate(created.id)
        assert result is True

        fetched = await session_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.is_active is False

    async def test_revoke_all_for_user_marks_every_session_inactive(
        self,
        session_repo: SessionRepository,
        db_session: AsyncSession,
    ) -> None:
        """AC-2: revoke_all_for_user marks all active sessions inactive."""
        user = await self._create_user(db_session)

        for _ in range(3):
            s = await self._build_session(user.id)
            await session_repo.create(s)

        count = await session_repo.revoke_all_for_user(user.id)
        assert count == 3  # noqa: PLR2004

        sessions = await session_repo.get_by_user_id(user.id)
        assert all(s.is_active is False for s in sessions)

    async def test_count_active_excludes_inactive_and_lapsed(
        self,
        session_repo: SessionRepository,
        db_session: AsyncSession,
    ) -> None:
        """AC-2: count_active excludes inactive and absolute-lapsed."""
        user = await self._create_user(db_session)
        now = datetime.now(timezone.utc)

        # Active session
        s1 = await self._build_session(user.id)
        await session_repo.create(s1)

        # Inactive session
        s2 = await self._build_session(user.id, is_active=False)
        await session_repo.create(s2)

        # Absolute-lapsed (active but past absolute_expires_at)
        s3 = Session(
            user_id=user.id,
            issued_at=now - timedelta(hours=24),
            last_activity=now - timedelta(hours=24),
            expires_at=now - timedelta(hours=23),
            absolute_expires_at=now - timedelta(hours=1),
            remember_me=False,
            ip_address='127.0.0.1',
            user_agent='pytest',
            csrf_token_hash='c' * 64,
            is_active=True,
        )
        await session_repo.create(s3)

        count = await session_repo.count_active_for_user(user.id)
        assert count == 1  # noqa: PLR2004

    async def test_update_last_activity_writes_timestamp(
        self,
        session_repo: SessionRepository,
        db_session: AsyncSession,
    ) -> None:
        """AC-2: update_last_activity writes a new timestamp."""
        user = await self._create_user(db_session)
        session = await self._build_session(user.id)
        created = await session_repo.create(session)
        old = created.last_activity

        new_time = datetime.now(timezone.utc) + timedelta(seconds=5)
        await session_repo.update_last_activity(created.id, new_time)

        fetched = await session_repo.get_by_id(created.id)
        assert fetched is not None
        # Use total_seconds comparison to avoid microsecond issues
        assert fetched.last_activity is not None
        diff = (fetched.last_activity - new_time).total_seconds()
        assert abs(diff) < 1  # noqa: PLR2004
        assert fetched.last_activity != old
