from __future__ import annotations

import hashlib
import logging
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid7

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from questr.common.enums import UserRole, UserStatus
from questr.common.exceptions import (
    AccountBannedError,
    AccountSuspendedError,
    AuthenticationError,
    EmailNotVerifiedError,
    InvalidVerificationTokenError,
    RateLimitExceededError,
    TooManyActiveSessionsError,
    UserAlreadyExistsError,
)
from questr.domains.users.repository import (
    EmailVerification,
    EmailVerificationRepository,
    Session,
    SessionRepository,
    User,
    UserRepository,
)
from questr.infrastructure.email import BaseEmailService
from questr.infrastructure.login_rate_limiter import LoginRateLimiter
from questr.infrastructure.rate_limiter import RedisRateLimiter

logger = logging.getLogger('questr.auth')
pwd_context = PasswordHash(hashers=[Argon2Hasher()])


# Pre-computed Argon2 hash of a random password, used for the no-user
# timing branch (TD-006).
_DUMMY_HASH = pwd_context.hash('__questr_dummy_timing__')


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


def get_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)


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


class AuthService:
    def __init__(  # noqa: PLR0913, PLR0917
        self,
        user_repo: UserRepository,
        verification_repo: EmailVerificationRepository,
        email_service: BaseEmailService,
        rate_limiter: RedisRateLimiter,
        session_repo: SessionRepository | None = None,
        login_rate_limiter: LoginRateLimiter | None = None,
    ) -> None:
        self.user_repo = user_repo
        self.verification_repo = verification_repo
        self.email_service = email_service
        self.rate_limiter = rate_limiter
        self.session_repo = session_repo
        self.login_rate_limiter = login_rate_limiter

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

    async def login(  # noqa: PLR0913, PLR0917, PLR0912
        self,
        email: str,
        password: str,
        client_ip: str,
        remember_me: bool = False,
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
        if self.login_rate_limiter is not None:
            await self.login_rate_limiter.check_login_allowed(email, client_ip)

        # User lookup
        user = await self.user_repo.get_by_email(email)

        if user is None:
            # No-user branch: dummy verify for timing equalisation (TD-006)
            verify_password(password, _DUMMY_HASH)
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
            if self.login_rate_limiter is not None:
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
        if self.session_repo is not None:
            active = await self.session_repo.count_active_for_user(user.id)
            if active >= 10:  # noqa: PLR2004
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
            absolute_expires_at = now + timedelta(days=30)
        else:
            absolute_expires_at = now + timedelta(hours=8)
        expires_at = now + timedelta(minutes=30)

        # Create session record (IP/UA validation happens in T6 layer)
        if self.session_repo is not None:
            session = Session(
                user_id=user.id,
                issued_at=now,
                last_activity=now,
                expires_at=expires_at,
                absolute_expires_at=absolute_expires_at,
                remember_me=remember_me,
                ip_address=client_ip[:45],
                user_agent='',  # Filled by API layer
                csrf_token_hash=csrf_hash,
                is_active=True,
            )
            created_session = await self.session_repo.create(session)
        else:
            created_session = None

        # Reset failure counter on success
        if self.login_rate_limiter is not None:
            await self.login_rate_limiter.record_success(email)

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

    async def validate_session(self, session_id: UUID) -> User:
        """Validate a session and return the owning User.

        Performs idle-expiry and absolute-expiry checks, deactivates
        expired sessions, and eagerly updates last_activity on valid
        sessions.

        Raises:
            AuthenticationError: if session is invalid or expired.
        """
        if self.session_repo is None:
            raise AuthenticationError('Session service unavailable')

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

        # Eagerly update last_activity and extend idle window
        await self.session_repo.update_last_activity(session_id, now)

        user = await self.user_repo.get_by_id(session.user_id)
        if user is None:
            raise AuthenticationError('Not authenticated')
        return user

    async def logout(self, session_id: UUID) -> None:
        """Deactivate the current session."""
        if self.session_repo is not None:
            await self.session_repo.deactivate(session_id)

    async def logout_all(self, user_id: UUID) -> int:
        """Revoke all active sessions for the given user.

        Returns the number of revoked sessions.
        """
        if self.session_repo is not None:
            return await self.session_repo.revoke_all_for_user(user_id)
        return 0
