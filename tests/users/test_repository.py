# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
from datetime import datetime, timedelta, timezone
from uuid import uuid7

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from questr.common.enums import UserRole, UserStatus
from questr.orm.models import UserORMModel
from questr.users.domain import EmailVerification, User
from questr.users.repository import EmailVerificationRepository, UserRepository
from tests.users.factories import UserFactory


class TestUserRepository:
    @pytest_asyncio.fixture
    async def repo(self, db_session: AsyncSession) -> UserRepository:
        return UserRepository(db_session)

    @pytest_asyncio.fixture
    async def created_user(
        self, db_session: AsyncSession
    ) -> tuple[UserRepository, User]:
        repo = UserRepository(db_session)
        uid = uuid7()
        user = User(
            id=uid,
            username=f'testuser_{uid.hex[:8]}',
            email=f'{uid.hex[:8]}@example.com',
            first_name='Test',
            last_name='User',
            password_hash='hash123',
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )
        created = await repo.create(user)
        await db_session.flush()
        return repo, created

    @pytest.mark.asyncio
    async def test_create_inserts_user(
        self, repo: UserRepository, db_session: AsyncSession
    ) -> None:
        uid = uuid7()
        user = User(
            id=uid,
            username=f'alice_{uid.hex[:8]}',
            email=f'alice_{uid.hex[:8]}@example.com',
            first_name='Alice',
            last_name='Smith',
            password_hash='hash456',
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )
        result = await repo.create(user)
        await db_session.flush()
        assert result.username.startswith('alice_')
        assert 'example.com' in result.email

    @pytest.mark.asyncio
    async def test_get_by_username(self, created_user: tuple) -> None:
        repo, created = created_user
        found = await repo.get_by_username(created.username)
        assert found is not None
        assert found.username == created.username

    @pytest.mark.asyncio
    async def test_get_by_email(self, created_user: tuple) -> None:
        repo, created = created_user
        found = await repo.get_by_email(created.email)
        assert found is not None
        assert found.email == created.email

    @pytest.mark.asyncio
    async def test_update_status(
        self,
        created_user: tuple,
        db_session: AsyncSession,
    ) -> None:
        repo, created = created_user
        updated = await repo.update_status(
            created.id, UserStatus.ACTIVE
        )
        await db_session.flush()
        assert updated is not None
        assert updated.status == UserStatus.ACTIVE


class TestEmailVerificationRepository:
    @pytest_asyncio.fixture
    async def vrepo(
        self, db_session: AsyncSession
    ) -> EmailVerificationRepository:
        return EmailVerificationRepository(db_session)

    @pytest_asyncio.fixture
    async def orm_user(
        self, db_session: AsyncSession
    ) -> UserORMModel:
        user = UserFactory()
        db_session.add(user)
        await db_session.flush()
        return user

    @pytest.mark.asyncio
    async def test_create_inserts_verification(
        self,
        vrepo: EmailVerificationRepository,
        db_session: AsyncSession,
        orm_user: UserORMModel,
    ) -> None:
        verification = EmailVerification(
            id=uuid7(),
            user_id=orm_user.id,
            token_hash='tokenhash123',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        result = await vrepo.create(verification)
        await db_session.flush()
        assert result.token_hash == 'tokenhash123'

    @pytest.mark.asyncio
    async def test_get_by_token_hash(
        self,
        vrepo: EmailVerificationRepository,
        db_session: AsyncSession,
        orm_user: UserORMModel,
    ) -> None:
        token_hash = 'findme_hash_456'
        verification = EmailVerification(
            id=uuid7(),
            user_id=orm_user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        await vrepo.create(verification)
        await db_session.flush()

        found = await vrepo.get_by_token_hash(token_hash)
        assert found is not None
        assert found.token_hash == token_hash

    @pytest.mark.asyncio
    async def test_mark_as_used(
        self,
        vrepo: EmailVerificationRepository,
        db_session: AsyncSession,
        orm_user: UserORMModel,
    ) -> None:
        verification = EmailVerification(
            id=uuid7(),
            user_id=orm_user.id,
            token_hash='used_hash',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        created = await vrepo.create(verification)
        await db_session.flush()

        result = await vrepo.mark_as_used(created.id)
        await db_session.flush()
        assert result is True

        updated = await vrepo.get_by_token_hash('used_hash')
        assert updated is not None
        assert updated.used_at is not None

    @pytest.mark.asyncio
    async def test_delete_by_user_id(
        self,
        vrepo: EmailVerificationRepository,
        db_session: AsyncSession,
        orm_user: UserORMModel,
    ) -> None:
        verification = EmailVerification(
            id=uuid7(),
            user_id=orm_user.id,
            token_hash='delete_hash',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        await vrepo.create(verification)
        await db_session.flush()

        count = await vrepo.delete_by_user_id(orm_user.id)
        await db_session.flush()
        assert count >= 1
