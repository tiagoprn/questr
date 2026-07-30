from datetime import datetime
from uuid import UUID

from sqlalchemy import UUID as SAUUID
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from questr.common.enums import AuditAction, UserRole, UserStatus
from questr.infrastructure.orm.base import Base


class UserORMModel(Base):
    __tablename__ = 'users'

    id: Mapped[UUID] = mapped_column(SAUUID, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(1024), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.USER, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), default=UserStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    email_verification: Mapped['EmailVerificationORMModel | None'] = (
        relationship(
            back_populates='user',
            uselist=False,
        )
    )
    sessions: Mapped[list['SessionORMModel']] = relationship(
        back_populates='user',
    )


class EmailVerificationORMModel(Base):
    __tablename__ = 'email_verifications'

    id: Mapped[UUID] = mapped_column(SAUUID, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        SAUUID,
        ForeignKey('users.id'),
        unique=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped['UserORMModel'] = relationship(
        back_populates='email_verification'
    )


class SessionORMModel(Base):
    __tablename__ = 'sessions'

    __table_args__ = (
        Index(
            'idx_sessions_is_active',
            'is_active',
            postgresql_where=text('is_active = true'),
        ),
    )

    id: Mapped[UUID] = mapped_column(SAUUID, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        SAUUID,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    remember_me: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    impersonator_id: Mapped[UUID | None] = mapped_column(SAUUID, nullable=True)
    impersonator_session_id: Mapped[UUID | None] = mapped_column(
        SAUUID, nullable=True
    )

    user: Mapped['UserORMModel'] = relationship(back_populates='sessions')


class AuditLogORMModel(Base):
    __tablename__ = 'audit_log'

    __table_args__ = (
        Index('idx_audit_log_action', 'action'),
        Index('idx_audit_log_actor_id', 'actor_id'),
        Index('idx_audit_log_target_id', 'target_id'),
    )

    id: Mapped[UUID] = mapped_column(SAUUID, primary_key=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(SAUUID, nullable=True)
    target_id: Mapped[UUID | None] = mapped_column(SAUUID, nullable=True)
    impersonator_id: Mapped[UUID | None] = mapped_column(SAUUID, nullable=True)
    impersonator_session_id: Mapped[UUID | None] = mapped_column(
        SAUUID, nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    old_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
