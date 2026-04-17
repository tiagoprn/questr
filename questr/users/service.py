import hashlib
from datetime import datetime, timezone
from uuid import uuid7

from argon2 import PasswordHasher

from questr.common.enums import UserRole, UserStatus
from questr.common.exceptions import (
    InvalidVerificationTokenError,
    RateLimitExceededError,
    UserAlreadyExistsError,
)
from questr.common.rate_limiter import RedisRateLimiter
from questr.common.services.email_service import BaseEmailService
from questr.users.domain import (
    EmailVerification,
    User,
    generate_verification_token,
    get_token_expiry,
    normalize_username,
    validate_password,
)
from questr.users.repository import (
    EmailVerificationRepository,
    UserRepository,
)

pwd_context = PasswordHasher()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        verification_repo: EmailVerificationRepository,
        email_service: BaseEmailService,
        rate_limiter: RedisRateLimiter,
    ) -> None:
        self.user_repo = user_repo
        self.verification_repo = verification_repo
        self.email_service = email_service
        self.rate_limiter = rate_limiter

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
            raise UserAlreadyExistsError(
                'Username already exists'
            )
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

        await self.email_service.send_verification_email(
            email, raw_token
        )

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

    async def resend_verification(
        self, email: str, client_ip: str
    ) -> bool:
        if not await self.rate_limiter.is_allowed(
            f'resend:{client_ip}'
        ):
            raise RateLimitExceededError(
                'Too many verification requests. '
                'Please try again later.'
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

        await self.email_service.send_verification_email(
            email, raw_token
        )

        return True
