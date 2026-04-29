from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from questr.common.enums import UserRole, UserStatus
from questr.infrastructure.orm.models import EmailVerificationORMModel, UserORMModel


@dataclass
class User:
    """User domain object."""

    id: UUID | None = None
    username: str = ''
    email: str = ''
    first_name: str = ''
    last_name: str = ''
    password_hash: str = ''
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING


@dataclass
class EmailVerification:
    """Email verification domain object."""

    id: UUID | None = None
    user_id: UUID | None = None
    token_hash: str = ''
    expires_at: datetime | None = None
    used_at: datetime | None = None


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user: User) -> User:
        orm_user = UserORMModel(
            id=user.id,
            username=user.username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            password_hash=user.password_hash,
            role=user.role,
            status=user.status,
        )
        self.session.add(orm_user)
        await self.session.flush()
        return self._to_domain(orm_user)

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.id == user_id)
        )
        orm_user = result.scalar_one_or_none()
        return self._to_domain(orm_user) if orm_user else None

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(UserORMModel).where(
                UserORMModel.username == username
            )
        )
        orm_user = result.scalar_one_or_none()
        return self._to_domain(orm_user) if orm_user else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(UserORMModel).where(
                UserORMModel.email == email
            )
        )
        orm_user = result.scalar_one_or_none()
        return self._to_domain(orm_user) if orm_user else None

    async def update_status(
        self, user_id: UUID, status: UserStatus
    ) -> User | None:
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.id == user_id)
        )
        orm_user = result.scalar_one_or_none()
        if orm_user is None:
            return None
        orm_user.status = status
        await self.session.flush()
        return self._to_domain(orm_user)

    @staticmethod
    def _to_domain(orm_user: UserORMModel) -> User:
        return User(
            id=orm_user.id,
            username=orm_user.username,
            email=orm_user.email,
            first_name=orm_user.first_name,
            last_name=orm_user.last_name,
            password_hash=orm_user.password_hash,
            role=orm_user.role,
            status=orm_user.status,
        )


class EmailVerificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, verification: EmailVerification
    ) -> EmailVerification:
        orm_verification = EmailVerificationORMModel(
            id=verification.id,
            user_id=verification.user_id,
            token_hash=verification.token_hash,
            expires_at=verification.expires_at,
            used_at=verification.used_at,
        )
        self.session.add(orm_verification)
        await self.session.flush()
        return self._to_domain(orm_verification)

    async def get_by_token_hash(
        self, token_hash: str
    ) -> EmailVerification | None:
        result = await self.session.execute(
            select(EmailVerificationORMModel).where(
                EmailVerificationORMModel.token_hash == token_hash
            )
        )
        orm_v = result.scalar_one_or_none()
        return self._to_domain(orm_v) if orm_v else None

    async def mark_as_used(self, verification_id: UUID) -> bool:
        result = await self.session.execute(
            select(EmailVerificationORMModel).where(
                EmailVerificationORMModel.id == verification_id
            )
        )
        orm_v = result.scalar_one_or_none()
        if orm_v is None:
            return False
        orm_v.used_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def delete_by_user_id(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(EmailVerificationORMModel).where(
                EmailVerificationORMModel.user_id == user_id
            )
        )
        records = result.scalars().all()
        count = len(records)
        for record in records:
            await self.session.delete(record)
        await self.session.flush()
        return count

    @staticmethod
    def _to_domain(orm_v: EmailVerificationORMModel) -> EmailVerification:
        return EmailVerification(
            id=orm_v.id,
            user_id=orm_v.user_id,
            token_hash=orm_v.token_hash,
            expires_at=orm_v.expires_at,
            used_at=orm_v.used_at,
        )
