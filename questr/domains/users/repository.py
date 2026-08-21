from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid7

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from questr.common.enums import AuditAction, UserRole, UserStatus
from questr.infrastructure.orm.models import (
    AuditLogORMModel,
    EmailChangeORMModel,
    EmailVerificationORMModel,
    PasswordResetTokenORMModel,
    SessionORMModel,
    UserORMModel,
)


@dataclass
class User:
    """User domain object."""

    id: UUID | None = None
    username: str = ''
    email: str = ''
    previous_email: str | None = None
    email_changed_at: datetime | None = None
    first_name: str = ''
    last_name: str = ''
    password_hash: str = ''
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Session:
    """Session domain object."""

    id: UUID | None = None
    user_id: UUID | None = None
    issued_at: datetime | None = None
    last_activity: datetime | None = None
    expires_at: datetime | None = None
    absolute_expires_at: datetime | None = None
    remember_me: bool = False
    ip_address: str = ''
    user_agent: str = ''
    csrf_token_hash: str = ''
    is_active: bool = True
    impersonator_id: UUID | None = None
    impersonator_session_id: UUID | None = None


@dataclass
class AuditLog:
    """Audit log entry domain object."""

    id: UUID | None = None
    action: AuditAction = AuditAction.IMPERSONATION_START
    actor_id: UUID | None = None
    target_id: UUID | None = None
    impersonator_id: UUID | None = None
    impersonator_session_id: UUID | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    old_role: UserRole | None = None
    new_role: UserRole | None = None
    reason: str | None = None
    ip_address: str = ''
    user_agent: str = ''
    created_at: datetime | None = None


@dataclass
class EmailVerification:
    """Email verification domain object."""

    id: UUID | None = None
    user_id: UUID | None = None
    token_hash: str = ''
    expires_at: datetime | None = None
    used_at: datetime | None = None


@dataclass
class PasswordResetToken:
    """Password reset token domain object."""

    id: UUID | None = None
    user_id: UUID | None = None
    token_hash: str = ''
    expires_at: datetime | None = None
    used_at: datetime | None = None


@dataclass
class EmailChangeRequest:
    """Email change request domain object."""

    id: UUID | None = None
    user_id: UUID | None = None
    old_email: str = ''
    new_email: str = ''
    token_hash: str = ''
    expires_at: datetime | None = None
    used_at: datetime | None = None
    revert_token_hash: str | None = None
    revert_used_at: datetime | None = None
    ip: str = ''
    user_agent: str = ''
    created_at: datetime | None = None


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
            select(UserORMModel).where(UserORMModel.username == username)
        )
        orm_user = result.scalar_one_or_none()
        return self._to_domain(orm_user) if orm_user else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.email == email)
        )
        orm_user = result.scalar_one_or_none()
        return self._to_domain(orm_user) if orm_user else None

    async def get_by_email_or_previous(
        self, email: str, hold_window: timedelta
    ) -> User | None:
        """Find a user by current email or a held previous email.

        A ``previous_email`` only matches while the hold window is still
        open (``email_changed_at + hold_window`` in the future).
        """
        now = datetime.now(timezone.utc)
        hold_cutoff = now - hold_window
        result = await self.session.execute(
            select(UserORMModel).where(
                or_(
                    UserORMModel.email == email,
                    and_(
                        UserORMModel.previous_email == email,
                        UserORMModel.email_changed_at.is_not(None),
                        UserORMModel.email_changed_at > hold_cutoff,
                    ),
                )
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
        # Python-side timestamp (not ORM onupdate): an onupdate would
        # expire the attribute on flush and force a lazy refresh, which
        # raises MissingGreenlet in async sessions; it also uses the DB
        # clock, which freezegun cannot control.
        orm_user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._to_domain(orm_user)

    async def update_role(self, user_id: UUID, role: UserRole) -> User | None:
        """Update a user's role."""
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.id == user_id)
        )
        orm_user = result.scalar_one_or_none()
        if orm_user is None:
            return None
        orm_user.role = role
        orm_user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._to_domain(orm_user)

    async def update_password(
        self, user_id: UUID, new_hash: str
    ) -> User | None:
        """Set a user's password hash."""
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.id == user_id)
        )
        orm_user = result.scalar_one_or_none()
        if orm_user is None:
            return None
        orm_user.password_hash = new_hash
        orm_user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._to_domain(orm_user)

    async def update_email(self, user_id: UUID, new_email: str) -> User | None:
        """Set a user's primary email."""
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.id == user_id)
        )
        orm_user = result.scalar_one_or_none()
        if orm_user is None:
            return None
        orm_user.email = new_email
        orm_user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._to_domain(orm_user)

    async def set_email_hold(
        self, user_id: UUID, previous_email: str
    ) -> User | None:
        """Snapshot the old email and open the hold window."""
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.id == user_id)
        )
        orm_user = result.scalar_one_or_none()
        if orm_user is None:
            return None
        orm_user.previous_email = previous_email
        orm_user.email_changed_at = datetime.now(timezone.utc)
        orm_user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._to_domain(orm_user)

    async def revert_email(self, user_id: UUID) -> User | None:
        """Restore the previous email and clear the hold fields."""
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.id == user_id)
        )
        orm_user = result.scalar_one_or_none()
        if orm_user is None or orm_user.previous_email is None:
            return None
        orm_user.email = orm_user.previous_email
        orm_user.previous_email = None
        orm_user.email_changed_at = None
        orm_user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._to_domain(orm_user)

    @staticmethod
    def _to_domain(orm_user: UserORMModel) -> User:
        return User(
            id=orm_user.id,
            username=orm_user.username,
            email=orm_user.email,
            previous_email=orm_user.previous_email,
            email_changed_at=orm_user.email_changed_at,
            first_name=orm_user.first_name,
            last_name=orm_user.last_name,
            password_hash=orm_user.password_hash,
            role=orm_user.role,
            status=orm_user.status,
            created_at=orm_user.created_at,
            updated_at=orm_user.updated_at,
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
            delete(EmailVerificationORMModel).where(
                EmailVerificationORMModel.user_id == user_id
            )
        )
        await self.session.flush()
        return result.rowcount

    @staticmethod
    def _to_domain(orm_v: EmailVerificationORMModel) -> EmailVerification:
        return EmailVerification(
            id=orm_v.id,
            user_id=orm_v.user_id,
            token_hash=orm_v.token_hash,
            expires_at=orm_v.expires_at,
            used_at=orm_v.used_at,
        )


class PasswordResetTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, token: PasswordResetToken) -> PasswordResetToken:
        orm_token = PasswordResetTokenORMModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            used_at=token.used_at,
        )
        self.session.add(orm_token)
        await self.session.flush()
        return self._to_domain(orm_token)

    async def get_by_token_hash(
        self, token_hash: str
    ) -> PasswordResetToken | None:
        result = await self.session.execute(
            select(PasswordResetTokenORMModel).where(
                PasswordResetTokenORMModel.token_hash == token_hash
            )
        )
        orm_t = result.scalar_one_or_none()
        return self._to_domain(orm_t) if orm_t else None

    async def mark_as_used(self, token_id: UUID) -> bool:
        result = await self.session.execute(
            select(PasswordResetTokenORMModel).where(
                PasswordResetTokenORMModel.id == token_id
            )
        )
        orm_t = result.scalar_one_or_none()
        if orm_t is None:
            return False
        orm_t.used_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def delete_by_user_id(self, user_id: UUID) -> int:
        result = await self.session.execute(
            delete(PasswordResetTokenORMModel).where(
                PasswordResetTokenORMModel.user_id == user_id
            )
        )
        await self.session.flush()
        return result.rowcount

    @staticmethod
    def _to_domain(orm_t: PasswordResetTokenORMModel) -> PasswordResetToken:
        return PasswordResetToken(
            id=orm_t.id,
            user_id=orm_t.user_id,
            token_hash=orm_t.token_hash,
            expires_at=orm_t.expires_at,
            used_at=orm_t.used_at,
        )


class EmailChangeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, request: EmailChangeRequest) -> EmailChangeRequest:
        orm_request = EmailChangeORMModel(
            id=request.id,
            user_id=request.user_id,
            old_email=request.old_email,
            new_email=request.new_email,
            token_hash=request.token_hash,
            expires_at=request.expires_at,
            used_at=request.used_at,
            revert_token_hash=request.revert_token_hash,
            revert_used_at=request.revert_used_at,
            ip=request.ip,
            user_agent=request.user_agent,
        )
        self.session.add(orm_request)
        await self.session.flush()
        return self._to_domain(orm_request)

    async def get_by_token_hash(
        self, token_hash: str
    ) -> EmailChangeRequest | None:
        result = await self.session.execute(
            select(EmailChangeORMModel).where(
                EmailChangeORMModel.token_hash == token_hash
            )
        )
        orm_r = result.scalar_one_or_none()
        return self._to_domain(orm_r) if orm_r else None

    async def get_by_revert_token_hash(
        self, revert_token_hash: str
    ) -> EmailChangeRequest | None:
        result = await self.session.execute(
            select(EmailChangeORMModel).where(
                EmailChangeORMModel.revert_token_hash == revert_token_hash
            )
        )
        orm_r = result.scalar_one_or_none()
        return self._to_domain(orm_r) if orm_r else None

    async def mark_as_used(self, request_id: UUID) -> bool:
        result = await self.session.execute(
            select(EmailChangeORMModel).where(
                EmailChangeORMModel.id == request_id
            )
        )
        orm_r = result.scalar_one_or_none()
        if orm_r is None:
            return False
        orm_r.used_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def mark_revert_as_used(self, request_id: UUID) -> bool:
        result = await self.session.execute(
            select(EmailChangeORMModel).where(
                EmailChangeORMModel.id == request_id
            )
        )
        orm_r = result.scalar_one_or_none()
        if orm_r is None:
            return False
        orm_r.revert_used_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def delete_by_user_id(self, user_id: UUID) -> int:
        result = await self.session.execute(
            delete(EmailChangeORMModel).where(
                EmailChangeORMModel.user_id == user_id
            )
        )
        await self.session.flush()
        return result.rowcount

    @staticmethod
    def _to_domain(orm_r: EmailChangeORMModel) -> EmailChangeRequest:
        return EmailChangeRequest(
            id=orm_r.id,
            user_id=orm_r.user_id,
            old_email=orm_r.old_email,
            new_email=orm_r.new_email,
            token_hash=orm_r.token_hash,
            expires_at=orm_r.expires_at,
            used_at=orm_r.used_at,
            revert_token_hash=orm_r.revert_token_hash,
            revert_used_at=orm_r.revert_used_at,
            ip=orm_r.ip,
            user_agent=orm_r.user_agent,
            created_at=orm_r.created_at,
        )


class SessionRepository:
    """Repository for session persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, session_obj: Session) -> Session:
        orm_session = SessionORMModel(
            id=session_obj.id or uuid7(),
            user_id=session_obj.user_id,
            issued_at=session_obj.issued_at,
            last_activity=session_obj.last_activity,
            expires_at=session_obj.expires_at,
            absolute_expires_at=session_obj.absolute_expires_at,
            remember_me=session_obj.remember_me,
            ip_address=session_obj.ip_address,
            user_agent=session_obj.user_agent,
            csrf_token_hash=session_obj.csrf_token_hash,
            is_active=session_obj.is_active,
            impersonator_id=session_obj.impersonator_id,
            impersonator_session_id=session_obj.impersonator_session_id,
        )
        self.session.add(orm_session)
        await self.session.flush()
        return self._to_domain(orm_session)

    async def get_by_id(self, session_id: UUID) -> Session | None:
        result = await self.session.execute(
            select(SessionORMModel).where(SessionORMModel.id == session_id)
        )
        orm_session = result.scalar_one_or_none()
        return self._to_domain(orm_session) if orm_session else None

    async def get_by_user_id(self, user_id: UUID) -> list[Session]:
        result = await self.session.execute(
            select(SessionORMModel).where(SessionORMModel.user_id == user_id)
        )
        orm_sessions = result.scalars().all()
        return [self._to_domain(s) for s in orm_sessions]

    async def deactivate(self, session_id: UUID) -> bool:
        result = await self.session.execute(
            update(SessionORMModel)
            .where(SessionORMModel.id == session_id)
            .values(is_active=False)
        )
        await self.session.flush()
        return result.rowcount > 0

    async def revoke_all_for_user(
        self, user_id: UUID, except_session_id: UUID | None = None
    ) -> int:
        stmt = update(SessionORMModel).where(
            SessionORMModel.user_id == user_id,
            SessionORMModel.is_active.is_(True),
        )
        if except_session_id is not None:
            stmt = stmt.where(SessionORMModel.id != except_session_id)
        result = await self.session.execute(stmt.values(is_active=False))
        await self.session.flush()
        return result.rowcount

    async def count_active_for_user(self, user_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(SessionORMModel).where(
                SessionORMModel.user_id == user_id,
                SessionORMModel.is_active.is_(True),
                SessionORMModel.absolute_expires_at > now,
            )
        )
        return len(result.scalars().all())

    async def update_last_activity(
        self,
        session_id: UUID,
        timestamp: datetime,
        expires_at: datetime,
    ) -> None:
        """Update last_activity and slide the idle window (FR-005)."""
        await self.session.execute(
            update(SessionORMModel)
            .where(SessionORMModel.id == session_id)
            .values(last_activity=timestamp, expires_at=expires_at)
        )
        await self.session.flush()

    async def update_csrf_hash(
        self,
        session_id: UUID,
        csrf_token_hash: str,
    ) -> None:
        """Replace the stored CSRF token hash on a session row.

        Used by stop-impersonation to rotate the admin session's CSRF
        token after the impersonation ends.
        """
        await self.session.execute(
            update(SessionORMModel)
            .where(SessionORMModel.id == session_id)
            .values(csrf_token_hash=csrf_token_hash)
        )
        await self.session.flush()

    @staticmethod
    def _to_domain(orm_s: SessionORMModel) -> Session:
        return Session(
            id=orm_s.id,
            user_id=orm_s.user_id,
            issued_at=orm_s.issued_at,
            last_activity=orm_s.last_activity,
            expires_at=orm_s.expires_at,
            absolute_expires_at=orm_s.absolute_expires_at,
            remember_me=orm_s.remember_me,
            ip_address=orm_s.ip_address,
            user_agent=orm_s.user_agent,
            csrf_token_hash=orm_s.csrf_token_hash,
            is_active=orm_s.is_active,
            impersonator_id=orm_s.impersonator_id,
            impersonator_session_id=orm_s.impersonator_session_id,
        )


class AuditLogRepository:
    """Insert-only repository for audit log entries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, entry: AuditLog) -> AuditLog:
        """Persist a new audit log entry.

        No update or delete methods: append-only discipline.
        """
        orm_entry = AuditLogORMModel(
            id=entry.id or uuid7(),
            action=entry.action,
            actor_id=entry.actor_id,
            target_id=entry.target_id,
            impersonator_id=entry.impersonator_id,
            impersonator_session_id=entry.impersonator_session_id,
            started_at=entry.started_at,
            ended_at=entry.ended_at,
            old_role=entry.old_role,
            new_role=entry.new_role,
            reason=entry.reason,
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
        )
        self.session.add(orm_entry)
        await self.session.flush()
        return self._to_domain(orm_entry)

    @staticmethod
    def _to_domain(orm_e: AuditLogORMModel) -> AuditLog:
        return AuditLog(
            id=orm_e.id,
            action=AuditAction(orm_e.action)
            if orm_e.action
            else (AuditAction.IMPERSONATION_START),
            actor_id=orm_e.actor_id,
            target_id=orm_e.target_id,
            impersonator_id=orm_e.impersonator_id,
            impersonator_session_id=orm_e.impersonator_session_id,
            started_at=orm_e.started_at,
            ended_at=orm_e.ended_at,
            old_role=UserRole(orm_e.old_role) if orm_e.old_role else None,
            new_role=UserRole(orm_e.new_role) if orm_e.new_role else None,
            reason=orm_e.reason,
            ip_address=orm_e.ip_address or '',
            user_agent=orm_e.user_agent or '',
            created_at=orm_e.created_at,
        )
