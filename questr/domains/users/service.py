from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid7

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from questr.common.enums import AuditAction, UserRole, UserStatus
from questr.common.exceptions import (
    AccountBannedError,
    AccountSuspendedError,
    AuthenticationError,
    EmailNotVerifiedError,
    InvalidCurrentPasswordError,
    InvalidResetTokenError,
    InvalidVerificationTokenError,
    RateLimitExceededError,
    TooManyActiveSessionsError,
    UserAlreadyExistsError,
)
from questr.domains.users.repository import (
    AuditLog,
    AuditLogRepository,
    EmailChangeRepository,
    EmailChangeRequest,
    EmailVerification,
    EmailVerificationRepository,
    PasswordResetToken,
    PasswordResetTokenRepository,
    Session,
    SessionRepository,
    User,
    UserRepository,
)
from questr.infrastructure.dual_rate_limiter import DualRateLimiter
from questr.infrastructure.email import BaseEmailService
from questr.infrastructure.login_rate_limiter import LoginRateLimiter
from questr.infrastructure.rate_limiter import RedisRateLimiter
from questr.settings import settings

logger = logging.getLogger('questr.auth')
pwd_context = PasswordHash(hashers=[Argon2Hasher()])


# Pre-computed Argon2 hash of a random password, used for the no-user
# timing branch (TD-006).
_DUMMY_HASH = pwd_context.hash('__questr_dummy_timing__')


@dataclass
class SessionPrincipal:
    """Result of session validation: the user plus effective-user metadata.

    Attributes:
        user: The authenticated (or impersonated) user.
        is_impersonation: Whether this session is an impersonation.
        impersonator_session_id: If impersonating, the admin's original
            session id (used for stop-impersonation linkage).
    """

    user: User
    is_impersonation: bool = False
    impersonator_session_id: UUID | None = None


# ── Domain functions ─────────────────────────────────────────────────


def normalize_username(username: str) -> str:
    username = username.strip()
    username = username.lower()
    username = (
        unicodedata
        .normalize('NFKD', username)
        .encode('ascii', 'ignore')
        .decode('ascii')
    )
    username = re.sub(r'[^a-z0-9_-]', '', username)
    return username


def generate_verification_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def get_token_expiry(ttl: timedelta = timedelta(hours=24)) -> datetime:
    return datetime.now(timezone.utc) + ttl


def sanitize_ip(client_ip: str) -> str:
    """Validate/truncate the client IP before persisting (design §5).

    A value that parses as an IP is accepted (truncated to 45 chars if
    over-length, e.g. a scoped IPv6 literal); anything else is stored as
    ``'unknown'`` so a crafted X-Forwarded-For header cannot make
    PostgreSQL reject the session row.
    """
    try:
        ipaddress.ip_address(client_ip)
    except ValueError:
        return 'unknown'
    return client_ip[:45]


@dataclass
class PasswordValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


def validate_password(password: str) -> PasswordValidationResult:
    errors: list[str] = []

    if len(password) < 8:  # noqa: PLR2004
        errors.append('Password must be at least 8 characters')
    if not re.search(r'[A-Z]', password):
        errors.append('Password must contain at least 1 uppercase letter')
    if not re.search(r'[a-z]', password):
        errors.append('Password must contain at least 1 lowercase letter')
    if not re.search(r'\d', password):
        errors.append('Password must contain at least 1 number')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append(
            'Password must contain at least 1 special character '
            '(!@#$%^&*(),.?":{}|<>)'
        )

    return PasswordValidationResult(is_valid=len(errors) == 0, errors=errors)


# ── Application services ──────────────────────────────────────────────


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


class AccountService:
    """Account lifecycle: signup, email verification, resend.

    deps: user_repo, verification_repo, email_service, rate_limiter,
    login_rate_limiter, reset_token_repo, audit_repo, dual_rate_limiter,
    email_change_repo.
    """

    def __init__(  # noqa: PLR0913,PLR0917
        self,
        user_repo: UserRepository,
        verification_repo: EmailVerificationRepository,
        email_service: BaseEmailService,
        rate_limiter: RedisRateLimiter,
        login_rate_limiter: LoginRateLimiter,
        password_reset_token_repo: PasswordResetTokenRepository,
        audit_repo: AuditLogRepository,
        dual_rate_limiter: DualRateLimiter,
        email_change_repo: EmailChangeRepository,
    ) -> None:
        self.user_repo = user_repo
        self.verification_repo = verification_repo
        self.email_service = email_service
        self.rate_limiter = rate_limiter
        self.login_rate_limiter = login_rate_limiter
        self.password_reset_token_repo = password_reset_token_repo
        self.audit_repo = audit_repo
        self.dual_rate_limiter = dual_rate_limiter
        self.email_change_repo = email_change_repo

    async def signup(  # noqa: PLR0913,PLR0917
        self,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        password: str,
        password_confirmation: str,
        client_ip: str,
    ) -> User:
        if password != password_confirmation:
            raise ValueError('Passwords do not match')

        result = validate_password(password)
        if not result.is_valid:
            raise ValueError('; '.join(result.errors))

        normalized_username = normalize_username(username)

        existing = await self.user_repo.get_by_username(normalized_username)
        if existing:
            raise UserAlreadyExistsError('Username already exists')
        # NOTE: get_by_email uses exact match (full string, including `+` tag),
        # so user+tag1@domain and user+tag2@domain are distinct users.
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise UserAlreadyExistsError('Email already exists')

        user = User(
            id=uuid7(),
            username=normalized_username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=hash_password(password),
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )

        created_user = await self.user_repo.create(user)

        raw_token, token_hash = generate_verification_token()
        verification = EmailVerification(
            id=uuid7(),
            user_id=created_user.id,
            token_hash=token_hash,
            expires_at=get_token_expiry(),
        )
        await self.verification_repo.create(verification)

        await self.email_service.send_verification_email(email, raw_token)

        return created_user

    async def verify_email(self, token: str) -> User:
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        verification = await self.verification_repo.get_by_token_hash(
            token_hash
        )
        if verification is None:
            raise InvalidVerificationTokenError(
                'Invalid or expired verification token'
            )

        if verification.used_at is not None:
            raise InvalidVerificationTokenError(
                'Invalid or expired verification token'
            )

        if verification.expires_at < datetime.now(timezone.utc):
            raise InvalidVerificationTokenError(
                'Invalid or expired verification token'
            )

        await self.verification_repo.mark_as_used(verification.id)

        user = await self.user_repo.update_status(
            verification.user_id, UserStatus.ACTIVE
        )
        if user is None:
            raise InvalidVerificationTokenError(
                'Invalid or expired verification token'
            )

        return user

    async def resend_verification(self, email: str, client_ip: str) -> bool:
        if not await self.rate_limiter.is_allowed(f'resend:{client_ip}'):
            raise RateLimitExceededError(
                'Too many verification requests. Please try again later.'
            )

        user = await self.user_repo.get_by_email(email)

        if user is None or user.status != UserStatus.PENDING:
            return True

        await self.verification_repo.delete_by_user_id(user.id)

        raw_token, token_hash = generate_verification_token()
        verification = EmailVerification(
            id=uuid7(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=get_token_expiry(),
        )
        await self.verification_repo.create(verification)

        await self.email_service.send_verification_email(email, raw_token)

        return True

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        client_ip: str,
        user_agent: str,
    ) -> User:
        """Change the authenticated user's password.

        Gate 1: current-password lockout via the login rate limiter.
        Gate 2: invalidate outstanding password-reset tokens.

        Raises:
            InvalidCurrentPasswordError: if the current password is wrong.
            ValueError: if the new password is weak (400 via T-003).
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise AuthenticationError('Not authenticated')

        await self.login_rate_limiter.check_login_allowed(
            user.email, client_ip
        )

        if not verify_password(current_password, user.password_hash):
            await self.login_rate_limiter.record_failure(user.email, client_ip)
            raise InvalidCurrentPasswordError('Current password is incorrect')

        await self.login_rate_limiter.record_success(user.email)

        result = validate_password(new_password)
        if not result.is_valid:
            raise ValueError('; '.join(result.errors))

        new_hash = hash_password(new_password)
        await self.user_repo.update_password(user_id, new_hash)

        await self.password_reset_token_repo.delete_by_user_id(user_id)

        await self.audit_repo.insert(
            AuditLog(
                action=AuditAction.PASSWORD_CHANGED,
                actor_id=user_id,
                target_id=user_id,
                ip_address=sanitize_ip(client_ip),
                user_agent=user_agent,
            ),
        )

        await self.email_service.send_password_changed_email(user.email)

        return user

    async def request_password_reset(
        self, email: str, client_ip: str, user_agent: str
    ) -> bool:
        """Request a password reset. Uniform 200 regardless of outcome.

        Gate 6: dual rate limit, count-on-send (only enqueued emails
        count). Gate 7: identical external response for all account
        states. Matrix D3: ACTIVE sends a reset, PENDING resends
        verification, SUSPENDED/BANNED send nothing.
        """
        await self.dual_rate_limiter.check_allowed(email, client_ip)

        hold_window = timedelta(hours=settings.EMAIL_CHANGE_HOLD_HOURS)
        user = await self.user_repo.get_by_email_or_previous(
            email, hold_window
        )

        if user is None:
            # Dummy work for timing equalisation (gate 7).
            generate_verification_token()
            return True

        if user.status == UserStatus.PENDING:
            # Resend verification instead of a reset (matrix D3).
            await self.verification_repo.delete_by_user_id(user.id)
            raw_token, token_hash = generate_verification_token()
            verification = EmailVerification(
                id=uuid7(),
                user_id=user.id,
                token_hash=token_hash,
                expires_at=get_token_expiry(),
            )
            await self.verification_repo.create(verification)
            await self.email_service.send_verification_email(
                user.email, raw_token
            )
            await self.dual_rate_limiter.consume_on_send(email, client_ip)
            return True

        if user.status != UserStatus.ACTIVE:
            # SUSPENDED/BANNED: send nothing (matrix D3), uniform response.
            return True

        # ACTIVE: rotate outstanding reset tokens, then create a new one.
        await self.password_reset_token_repo.delete_by_user_id(user.id)
        raw_token, token_hash = generate_verification_token()
        reset_token = PasswordResetToken(
            id=uuid7(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=get_token_expiry(
                timedelta(hours=settings.RESET_TOKEN_TTL_HOURS)
            ),
        )
        await self.password_reset_token_repo.create(reset_token)

        # Gate 3: during the hold, route the reset link to previous_email.
        reset_email = user.previous_email or user.email
        await self.email_service.send_password_reset_email(
            reset_email, raw_token
        )
        await self.dual_rate_limiter.consume_on_send(email, client_ip)
        return True

    async def reset_password(
        self, token: str, new_password: str, client_ip: str, user_agent: str
    ) -> User:
        """Reset a password using a single-use reset token.

        Gate 2: the token is single-use and outstanding tokens are
        invalidated. Raises ``InvalidResetTokenError`` on a bad,
        expired, or used token, or for SUSPENDED/BANNED accounts.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        reset_token = await self.password_reset_token_repo.get_by_token_hash(
            token_hash
        )

        if reset_token is None or reset_token.used_at is not None:
            raise InvalidResetTokenError('Invalid or expired reset token')
        now = datetime.now(timezone.utc)
        if reset_token.expires_at is None or reset_token.expires_at < now:
            raise InvalidResetTokenError('Invalid or expired reset token')

        user = await self.user_repo.get_by_id(reset_token.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise InvalidResetTokenError('Invalid or expired reset token')

        result = validate_password(new_password)
        if not result.is_valid:
            raise ValueError('; '.join(result.errors))

        new_hash = hash_password(new_password)
        await self.user_repo.update_password(user.id, new_hash)

        await self.password_reset_token_repo.delete_by_user_id(user.id)
        await self.password_reset_token_repo.mark_as_used(reset_token.id)

        await self.audit_repo.insert(
            AuditLog(
                action=AuditAction.PASSWORD_RESET,
                actor_id=user.id,
                target_id=user.id,
                ip_address=sanitize_ip(client_ip),
                user_agent=user_agent,
            ),
        )

        await self.email_service.send_password_reset_done_email(user.email)

        return user

    async def request_email_change(
        self,
        user_id: UUID,
        new_email: str,
        current_password: str,
        client_ip: str,
        user_agent: str,
    ) -> bool:
        """Request an email change.

        Gate 1: current-password lockout. Gate 3: uniqueness excludes a
        held previous_email. Gate 4: confirm link to the new address and
        a revert link to the old address. Gate 6: dual rate limit,
        count-on-send.
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise AuthenticationError('Not authenticated')

        await self.dual_rate_limiter.check_allowed(user.email, client_ip)

        await self.login_rate_limiter.check_login_allowed(
            user.email, client_ip
        )

        if not verify_password(current_password, user.password_hash):
            await self.login_rate_limiter.record_failure(user.email, client_ip)
            raise InvalidCurrentPasswordError('Current password is incorrect')

        await self.login_rate_limiter.record_success(user.email)

        hold_window = timedelta(hours=settings.EMAIL_CHANGE_HOLD_HOURS)
        existing = await self.user_repo.get_by_email_or_previous(
            new_email, hold_window
        )
        if existing is not None:
            raise UserAlreadyExistsError('Email already in use')

        # Rotate on re-request.
        await self.email_change_repo.delete_by_user_id(user.id)

        confirm_raw, confirm_hash = generate_verification_token()
        revert_raw, revert_hash = generate_verification_token()
        request = EmailChangeRequest(
            id=uuid7(),
            user_id=user.id,
            old_email=user.email,
            new_email=new_email,
            token_hash=confirm_hash,
            expires_at=get_token_expiry(timedelta(hours=24)),
            revert_token_hash=revert_hash,
            ip=sanitize_ip(client_ip),
            user_agent=user_agent,
        )
        await self.email_change_repo.create(request)

        await self.audit_repo.insert(
            AuditLog(
                action=AuditAction.EMAIL_CHANGE_REQUESTED,
                actor_id=user.id,
                target_id=user.id,
                ip_address=sanitize_ip(client_ip),
                user_agent=user_agent,
            ),
        )

        await self.email_service.send_email_change_confirm_email(
            new_email, confirm_raw
        )
        await self.email_service.send_email_change_old_notification(
            user.email, revert_raw
        )
        await self.dual_rate_limiter.consume_on_send(user.email, client_ip)
        return True

    async def confirm_email_change(
        self, token: str, client_ip: str, user_agent: str
    ) -> User:
        """Confirm an email change with a single-use token.

        Gate 2: outstanding reset tokens are invalidated. Gate 3: the
        hold fields are set (previous_email + email_changed_at).
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        request = await self.email_change_repo.get_by_token_hash(token_hash)

        if request is None or request.used_at is not None:
            raise InvalidResetTokenError('Invalid or expired token')
        now = datetime.now(timezone.utc)
        if request.expires_at is None or request.expires_at < now:
            raise InvalidResetTokenError('Invalid or expired token')

        user = await self.user_repo.get_by_id(request.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise InvalidResetTokenError('Invalid or expired token')

        # Uniqueness recheck: the new email may have been taken.
        hold_window = timedelta(hours=settings.EMAIL_CHANGE_HOLD_HOURS)
        existing = await self.user_repo.get_by_email_or_previous(
            request.new_email, hold_window
        )
        if existing is not None and existing.id != user.id:
            raise UserAlreadyExistsError('Email already in use')

        await self.user_repo.update_email(user.id, request.new_email)
        await self.user_repo.set_email_hold(user.id, request.old_email)

        await self.password_reset_token_repo.delete_by_user_id(user.id)
        await self.email_change_repo.mark_as_used(request.id)

        await self.audit_repo.insert(
            AuditLog(
                action=AuditAction.EMAIL_CHANGED,
                actor_id=user.id,
                target_id=user.id,
                ip_address=sanitize_ip(client_ip),
                user_agent=user_agent,
            ),
        )

        await self.email_service.send_email_changed_notice(request.new_email)

        return user

    async def revert_email_change(
        self, revert_token: str, client_ip: str, user_agent: str
    ) -> User:
        """Revert an email change with a single-use revert token.

        Gate 2: outstanding reset tokens are invalidated. Gate 4: the
        revert is only valid within the hold window.
        """
        token_hash = hashlib.sha256(revert_token.encode()).hexdigest()
        request = await self.email_change_repo.get_by_revert_token_hash(
            token_hash
        )

        if request is None or request.revert_used_at is not None:
            raise InvalidResetTokenError('Invalid or expired token')

        user = await self.user_repo.get_by_id(request.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise InvalidResetTokenError('Invalid or expired token')

        # Hold-window validity: revert only within the hold window.
        hold_window = timedelta(hours=settings.EMAIL_CHANGE_HOLD_HOURS)
        now = datetime.now(timezone.utc)
        hold_expired = (
            user.email_changed_at is None
            or user.email_changed_at + hold_window < now
        )
        if hold_expired:
            raise InvalidResetTokenError('Invalid or expired token')

        await self.user_repo.revert_email(user.id)

        await self.password_reset_token_repo.delete_by_user_id(user.id)
        await self.email_change_repo.mark_revert_as_used(request.id)

        await self.audit_repo.insert(
            AuditLog(
                action=AuditAction.EMAIL_CHANGE_REVERTED,
                actor_id=user.id,
                target_id=user.id,
                ip_address=sanitize_ip(client_ip),
                user_agent=user_agent,
            ),
        )

        await self.email_service.send_email_change_reverted_notice(
            request.old_email
        )

        return user


class SessionService:
    """Session lifecycle: login, validate, logout, logout_all,
    start_impersonation, stop_impersonation.

    deps: user_repo, session_repo, audit_repo, login_rate_limiter.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        audit_repo: AuditLogRepository,
        login_rate_limiter: LoginRateLimiter,
    ) -> None:
        self.user_repo = user_repo
        self.session_repo = session_repo
        self.audit_repo = audit_repo
        self.login_rate_limiter = login_rate_limiter

    async def login(  # noqa: PLR0913, PLR0917, PLR0912
        self,
        email: str,
        password: str,
        client_ip: str,
        remember_me: bool = False,
        user_agent: str = '',
    ) -> dict:
        """Authenticate a user and create a session.

        Returns a dict with keys ``user``, ``session``, ``csrf_token``
        on success.

        Raises:
            RateLimitExceededError: if IP throttled or account locked.
            AuthenticationError: if credentials don't match.
            EmailNotVerifiedError: if account is PENDING.
            AccountSuspendedError: if account is SUSPENDED.
            AccountBannedError: if account is BANNED.
            TooManyActiveSessionsError: if >= MAX_CONCURRENT_SESSIONS.
        """
        # Per-IP and per-account lockout check
        await self.login_rate_limiter.check_login_allowed(email, client_ip)

        # User lookup
        user = await self.user_repo.get_by_email(email)

        if user is None:
            # No-user branch: dummy verify for timing equalisation (TD-006)
            verify_password(password, _DUMMY_HASH)
            # FR-007: every attempt counts toward the per-IP window,
            # even when there is no account to lock out.
            await self.login_rate_limiter.record_ip_attempt(client_ip)
            logger.info(
                'login_attempt',
                extra={
                    'result': 'failure',
                    'error_code': None,
                    'account_lookup_done': True,
                },
            )
            raise AuthenticationError('Invalid email or password')

        # Non-ACTIVE status branch: verify real hash (discard result)
        # then raise structured error (TD-006 constant-time design)
        if user.status != UserStatus.ACTIVE:
            verify_password(password, user.password_hash)
            # FR-007: account-state rejections still count per-IP.
            await self.login_rate_limiter.record_ip_attempt(client_ip)
            logger.info(
                'login_attempt',
                extra={
                    'result': 'failure',
                    'error_code': user.status.value,
                    'account_lookup_done': True,
                },
            )
            if user.status == UserStatus.PENDING:
                raise EmailNotVerifiedError(
                    'Email not verified. Please check your inbox.'
                )
            if user.status == UserStatus.SUSPENDED:
                raise AccountSuspendedError('Account is suspended')
            if user.status == UserStatus.BANNED:
                raise AccountBannedError('Account is banned')
            raise AuthenticationError('Invalid email or password')

        # Password verify
        if not verify_password(password, user.password_hash):
            await self.login_rate_limiter.record_failure(email, client_ip)
            logger.info(
                'login_attempt',
                extra={
                    'result': 'failure',
                    'error_code': None,
                    'account_lookup_done': True,
                },
            )
            raise AuthenticationError('Invalid email or password')

        # Concurrent-session cap check
        active = await self.session_repo.count_active_for_user(user.id)
        if active >= settings.MAX_CONCURRENT_SESSIONS:
            logger.info(
                'login_attempt',
                extra={
                    'result': 'too_many_sessions',
                    'error_code': None,
                    'account_lookup_done': True,
                },
            )
            raise TooManyActiveSessionsError(
                'Maximum active sessions reached. '
                'Log out from another device first, '
                "or use 'Log out everywhere'."
            )

        # Mint CSRF token
        csrf_raw = secrets.token_urlsafe(32)
        csrf_hash = hashlib.sha256(csrf_raw.encode()).hexdigest()

        # Determine session lifetime
        now = datetime.now(timezone.utc)
        if remember_me:
            absolute_expires_at = now + timedelta(
                days=settings.SESSION_REMEMBER_DAYS
            )
        else:
            absolute_expires_at = now + timedelta(
                hours=settings.SESSION_ABSOLUTE_HOURS
            )
        expires_at = now + timedelta(minutes=settings.SESSION_IDLE_MINUTES)

        # Create session record (design §5: IP/UA sanitized pre-persist)
        session = Session(
            user_id=user.id,
            issued_at=now,
            last_activity=now,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
            remember_me=remember_me,
            ip_address=sanitize_ip(client_ip),
            user_agent=user_agent[:512],
            csrf_token_hash=csrf_hash,
            is_active=True,
        )
        created_session = await self.session_repo.create(session)

        # Reset failure counter on success; the attempt itself still
        # counts toward the per-IP window (FR-007).
        await self.login_rate_limiter.record_success(email)
        await self.login_rate_limiter.record_ip_attempt(client_ip)

        logger.info(
            'login_attempt',
            extra={
                'result': 'success',
                'error_code': None,
                'account_lookup_done': True,
            },
        )

        return {
            'user': user,
            'session': created_session,
            'csrf_token': csrf_raw,
        }

    async def validate_session(self, session_id: UUID) -> SessionPrincipal:
        """Validate a session and return a SessionPrincipal.

        Performs idle-expiry and absolute-expiry checks, deactivates
        expired sessions, and eagerly updates last_activity on valid
        sessions. For impersonation sessions, sets
        ``is_impersonation=True`` and carries the admin's original
        session id for stop-impersonation linkage.

        Raises:
            AuthenticationError: if session is invalid or expired.
        """
        session = await self.session_repo.get_by_id(session_id)
        if session is None or not session.is_active:
            raise AuthenticationError('Not authenticated')

        now = datetime.now(timezone.utc)

        # Absolute expiry check
        if (
            session.absolute_expires_at is not None
            and now >= session.absolute_expires_at
        ):
            await self.session_repo.deactivate(session_id)
            raise AuthenticationError('Session expired')

        # Idle expiry check (30 min inactivity)
        if session.expires_at is not None and now >= session.expires_at:
            await self.session_repo.deactivate(session_id)
            raise AuthenticationError('Session expired')

        # Eagerly update last_activity and slide the idle window
        # forward from this request (FR-005; design §7 step 6).
        new_expiry = now + timedelta(minutes=settings.SESSION_IDLE_MINUTES)
        await self.session_repo.update_last_activity(
            session_id, now, new_expiry
        )

        user = await self.user_repo.get_by_id(session.user_id)
        if user is None:
            raise AuthenticationError('Not authenticated')

        is_impersonation = session.impersonator_id is not None
        return SessionPrincipal(
            user=user,
            is_impersonation=is_impersonation,
            impersonator_session_id=session.impersonator_session_id
            if is_impersonation
            else None,
        )

    async def logout(self, session_id: UUID) -> None:
        """Deactivate the current session."""
        await self.session_repo.deactivate(session_id)

    async def logout_all(
        self, user_id: UUID, except_session_id: UUID | None = None
    ) -> int:
        """Revoke all active sessions for the given user.

        Args:
            user_id: Target user.
            except_session_id: Optional session id to keep active.

        Returns the number of revoked sessions.
        """
        return await self.session_repo.revoke_all_for_user(
            user_id, except_session_id
        )

    async def rotate_csrf(self, session_id: UUID) -> str:
        """Rotate a session's CSRF token and return the raw token."""
        csrf_raw = secrets.token_urlsafe(32)
        csrf_hash = hashlib.sha256(csrf_raw.encode()).hexdigest()
        await self.session_repo.update_csrf_hash(session_id, csrf_hash)
        return csrf_raw

    async def start_impersonation(  # noqa: PLR0913, PLR0917
        self,
        admin_user: User,
        admin_session_id: UUID,
        target_user: User,
        client_ip: str,
        user_agent: str,
        reason: str | None = None,
    ) -> dict:
        """Start an impersonation session as the target user.

        Creates a new session for the target user linked back to the
        admin session, with a 60-minute absolute time-box, and writes
        an IMPERSONATION_START audit row.

        Returns a dict with keys ``user``, ``session``, ``csrf_token``
        (matching the shape of ``login()``).

        Raises:
            SelfImpersonationError: if admin and target are the same.
            SuperuserImpersonationError: if the target is a SUPERUSER.
            TargetNotActiveError: if the target is not ACTIVE.
        """
        # Guard: no-self
        if admin_user.id == target_user.id:
            from questr.common.exceptions import (  # noqa: PLC0415
                SelfImpersonationError,
            )

            raise SelfImpersonationError()

        # Guard: no-superuser
        if target_user.role == UserRole.SUPERUSER:
            from questr.common.exceptions import (  # noqa: PLC0415
                SuperuserImpersonationError,
            )

            raise SuperuserImpersonationError()

        # Guard: active-only
        if target_user.status != UserStatus.ACTIVE:
            from questr.common.exceptions import (  # noqa: PLC0415
                TargetNotActiveError,
            )

            raise TargetNotActiveError()

        # Mint CSRF token
        csrf_raw = secrets.token_urlsafe(32)
        csrf_hash = hashlib.sha256(csrf_raw.encode()).hexdigest()

        # Create impersonation session: 60-minute absolute time-box
        now = datetime.now(timezone.utc)
        absolute_expires_at = now + timedelta(hours=1)
        expires_at = now + timedelta(minutes=settings.SESSION_IDLE_MINUTES)

        impersonation_session = Session(
            id=uuid7(),
            user_id=target_user.id,
            issued_at=now,
            last_activity=now,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
            remember_me=False,
            ip_address=client_ip,
            user_agent=user_agent,
            csrf_token_hash=csrf_hash,
            is_active=True,
            impersonator_id=admin_user.id,
            impersonator_session_id=admin_session_id,
        )
        created_session = await self.session_repo.create(impersonation_session)

        # Write audit row
        await self.audit_repo.insert(
            AuditLog(
                action=AuditAction.IMPERSONATION_START,
                actor_id=admin_user.id,
                target_id=target_user.id,
                impersonator_id=admin_user.id,
                impersonator_session_id=admin_session_id,
                started_at=now,
                reason=reason,
                ip_address=client_ip,
                user_agent=user_agent,
            ),
        )

        return {
            'user': target_user,
            'session': created_session,
            'csrf_token': csrf_raw,
        }

    async def stop_impersonation(  # noqa: PLR0913
        self,
        impersonation_session_id: UUID,
    ) -> dict:
        """Stop impersonation and restore the admin session.

        Validates the impersonation session (must be active, must be
        an impersonation), re-validates the linked admin session,
        checks the admin session belongs to the same user as the
        impersonator, deactivates the impersonation session, writes
        an IMPERSONATION_END audit row, and rotates the admin
        session's CSRF token.

        Returns a dict with keys ``admin_session_id`` and
        ``csrf_token`` for the route to set cookies.

        Raises:
            AuthenticationError: if the impersonation session is
                invalid, expired, not impersonating, or the admin
                session is gone/expired/deactivated.
        """
        # Validate the impersonation session
        session = await self.session_repo.get_by_id(impersonation_session_id)
        if session is None or not session.is_active:
            raise AuthenticationError('Not authenticated')

        now = datetime.now(timezone.utc)

        # Absolute expiry check
        if (
            session.absolute_expires_at is not None
            and now >= session.absolute_expires_at
        ):
            await self.session_repo.deactivate(impersonation_session_id)
            raise AuthenticationError('Session expired')

        # Idle expiry check
        if session.expires_at is not None and now >= session.expires_at:
            await self.session_repo.deactivate(impersonation_session_id)
            raise AuthenticationError('Session expired')

        # Gate: must be an impersonation session
        if session.impersonator_id is None:
            raise AuthenticationError('Not authenticated')

        # Re-validate the linked admin session via validate_session,
        # which checks active + absolute + idle expiry, deactivates on
        # expiry, slides the idle window on success, and fetches the
        # admin user (plan-literal; stop-linkage is the biggest risk).
        if session.impersonator_session_id is None:
            raise AuthenticationError('Not authenticated')
        admin_principal = await self.validate_session(
            session.impersonator_session_id
        )
        if admin_principal.user.id != session.impersonator_id:
            raise AuthenticationError('Not authenticated')

        # Deactivate the impersonation session
        await self.session_repo.deactivate(impersonation_session_id)

        # Write audit row
        await self.audit_repo.insert(
            AuditLog(
                action=AuditAction.IMPERSONATION_END,
                actor_id=session.impersonator_id,
                target_id=session.user_id,
                impersonator_id=session.impersonator_id,
                impersonator_session_id=session.impersonator_session_id,
                ended_at=now,
                ip_address=session.ip_address,
                user_agent=session.user_agent,
            ),
        )

        # Rotate the admin session's CSRF token
        csrf_raw = secrets.token_urlsafe(32)
        csrf_hash = hashlib.sha256(csrf_raw.encode()).hexdigest()
        await self.session_repo.update_csrf_hash(
            session.impersonator_session_id, csrf_hash
        )

        return {
            'admin_session_id': session.impersonator_session_id,
            'csrf_token': csrf_raw,
        }


class RoleService:
    """Role management: change_role with audit trail.

    deps: user_repo, audit_repo.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        audit_repo: AuditLogRepository,
    ) -> None:
        self.user_repo = user_repo
        self.audit_repo = audit_repo

    async def change_role(
        self,
        *,
        actor: User,
        target_id: UUID,
        new_role: UserRole,
        ip: str,
        user_agent: str,
    ) -> AuditLog:
        """Change a user's role and write a ROLE_GRANTED/ROLE_REVOKED
        audit row.

        The service fetches the target itself (it needs the old role
        for the audit row). The audit row records ip_address and
        user_agent for parity with impersonation audit rows.

        Args:
            actor: The user performing the change.
            target_id: The id of the user whose role is changing.
            new_role: The new role to assign.
            ip: The request client IP.
            user_agent: The request user-agent string.

        Returns:
            The persisted AuditLog entry.

        Raises:
            AuthenticationError: if the target is not found.
        """
        target = await self.user_repo.get_by_id(target_id)
        if target is None:
            raise AuthenticationError('User not found')
        old_role = target.role

        # Update via repository (the ORM model handles persistence)
        updated = await self.user_repo.update_role(target.id, new_role)
        if updated is None:
            raise AuthenticationError('User not found')

        # Determine action: grant if promoted (or same), revoke if
        # demoted to a lesser role.
        role_hierarchy = {UserRole.USER: 0, UserRole.SUPERUSER: 1}
        old_level = role_hierarchy.get(old_role, 0)
        new_level = role_hierarchy.get(new_role, 0)
        action = (
            AuditAction.ROLE_GRANTED
            if new_level >= old_level
            else AuditAction.ROLE_REVOKED
        )
        return await self.audit_repo.insert(
            AuditLog(
                action=action,
                actor_id=actor.id,
                target_id=target.id,
                old_role=old_role,
                new_role=new_role,
                ip_address=ip,
                user_agent=user_agent,
            ),
        )
