# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
# noqa: PLR6301,PLR2004
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid7

import pytest

from questr.common.enums import UserRole, UserStatus
from questr.common.exceptions import (
    InvalidVerificationTokenError,
    RateLimitExceededError,
    UserAlreadyExistsError,
)
from questr.domains.users.service import AuthService, EmailVerification, User


@pytest.fixture
def mock_user_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_username = AsyncMock(return_value=None)
    repo.get_by_email = AsyncMock(return_value=None)
    repo.update_status = AsyncMock()
    return repo


@pytest.fixture
def mock_verification_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_token_hash = AsyncMock(return_value=None)
    repo.mark_as_used = AsyncMock(return_value=True)
    repo.delete_by_user_id = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_email_service() -> MagicMock:
    service = MagicMock()
    service.send_verification_email = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_rate_limiter() -> MagicMock:
    limiter = MagicMock()
    limiter.is_allowed = AsyncMock(return_value=True)
    return limiter


@pytest.fixture
def auth_service(
    mock_user_repo: MagicMock,
    mock_verification_repo: MagicMock,
    mock_email_service: MagicMock,
    mock_rate_limiter: MagicMock,
) -> AuthService:
    return AuthService(
        user_repo=mock_user_repo,
        verification_repo=mock_verification_repo,
        email_service=mock_email_service,
        rate_limiter=mock_rate_limiter,
    )


class TestSignup:
    @pytest.mark.asyncio
    async def test_creates_user_and_sends_email(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        mock_verification_repo: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        mock_user_repo.get_by_username.return_value = None
        mock_user_repo.get_by_email.return_value = None
        mock_user_repo.create.return_value = User(
            id=uuid7(),
            username='testuser',
            email='test@example.com',
            first_name='Test',
            last_name='User',
            password_hash='hashed',
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )
        mock_verification_repo.create.return_value = EmailVerification(
            id=uuid7(),
            user_id=uuid7(),
            token_hash='hash',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        result = await auth_service.signup(
            username='TestUser',
            email='test@example.com',
            first_name='Test',
            last_name='User',
            password='StrongPass1!',
            password_confirmation='StrongPass1!',
            client_ip='127.0.0.1',
        )

        assert result.username == 'testuser'
        mock_user_repo.create.assert_called_once()
        mock_verification_repo.create.assert_called_once()
        mock_email_service.send_verification_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_duplicate_username(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
    ) -> None:
        mock_user_repo.get_by_username.return_value = User(
            id=uuid7(), username='testuser'
        )

        with pytest.raises(UserAlreadyExistsError):
            await auth_service.signup(
                username='testuser',
                email='new@example.com',
                first_name='Test',
                last_name='User',
                password='StrongPass1!',
                password_confirmation='StrongPass1!',
                client_ip='127.0.0.1',
            )

    @pytest.mark.asyncio
    async def test_raises_on_duplicate_email(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
    ) -> None:
        mock_user_repo.get_by_username.return_value = None
        mock_user_repo.get_by_email.return_value = User(
            id=uuid7(), email='test@example.com'
        )

        with pytest.raises(UserAlreadyExistsError):
            await auth_service.signup(
                username='newuser',
                email='test@example.com',
                first_name='Test',
                last_name='User',
                password='StrongPass1!',
                password_confirmation='StrongPass1!',
                client_ip='127.0.0.1',
            )

    @pytest.mark.asyncio
    async def test_raises_on_password_mismatch(
        self,
        auth_service: AuthService,
    ) -> None:
        with pytest.raises(ValueError, match='Passwords do not match'):
            await auth_service.signup(
                username='testuser',
                email='test@example.com',
                first_name='Test',
                last_name='User',
                password='StrongPass1!',
                password_confirmation='Different1!',
                client_ip='127.0.0.1',
            )

    @pytest.mark.asyncio
    async def test_raises_on_weak_password(
        self,
        auth_service: AuthService,
    ) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            await auth_service.signup(
                username='testuser',
                email='test@example.com',
                first_name='Test',
                last_name='User',
                password='weak',
                password_confirmation='weak',
                client_ip='127.0.0.1',
            )


class TestVerifyEmail:
    @pytest.mark.asyncio
    async def test_activates_user_on_valid_token(
        self,
        auth_service: AuthService,
        mock_verification_repo: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        user_id = uuid7()
        mock_verification_repo.get_by_token_hash.return_value = (
            EmailVerification(
                id=uuid7(),
                user_id=user_id,
                token_hash='valid_hash',
                expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)),
            )
        )
        mock_verification_repo.mark_as_used.return_value = True
        mock_user_repo.update_status.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            status=UserStatus.ACTIVE,
        )

        result = await auth_service.verify_email('raw_token')

        assert result.status == UserStatus.ACTIVE
        mock_user_repo.update_status.assert_called_once_with(
            user_id, UserStatus.ACTIVE
        )

    @pytest.mark.asyncio
    async def test_raises_on_invalid_token(
        self,
        auth_service: AuthService,
        mock_verification_repo: MagicMock,
    ) -> None:
        mock_verification_repo.get_by_token_hash.return_value = None

        with pytest.raises(InvalidVerificationTokenError):
            await auth_service.verify_email('invalid_token')

    @pytest.mark.asyncio
    async def test_raises_on_used_token(
        self,
        auth_service: AuthService,
        mock_verification_repo: MagicMock,
    ) -> None:
        mock_verification_repo.get_by_token_hash.return_value = (
            EmailVerification(
                id=uuid7(),
                user_id=uuid7(),
                token_hash='used_hash',
                expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)),
                used_at=datetime.now(timezone.utc),
            )
        )

        with pytest.raises(InvalidVerificationTokenError):
            await auth_service.verify_email('used_token')

    @pytest.mark.asyncio
    async def test_raises_on_expired_token(
        self,
        auth_service: AuthService,
        mock_verification_repo: MagicMock,
    ) -> None:
        mock_verification_repo.get_by_token_hash.return_value = (
            EmailVerification(
                id=uuid7(),
                user_id=uuid7(),
                token_hash='expired_hash',
                expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)),
            )
        )

        with pytest.raises(InvalidVerificationTokenError):
            await auth_service.verify_email('expired_token')


class TestResendVerification:
    @pytest.mark.asyncio
    async def test_creates_new_token_and_deletes_old(
        self,
        auth_service: AuthService,
        mock_rate_limiter: MagicMock,
        mock_user_repo: MagicMock,
        mock_verification_repo: MagicMock,
    ) -> None:
        user_id = uuid7()
        mock_user_repo.get_by_email.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            status=UserStatus.PENDING,
        )
        mock_verification_repo.delete_by_user_id.return_value = 1
        mock_verification_repo.create.return_value = EmailVerification(
            id=uuid7(),
            user_id=user_id,
            token_hash='new_hash',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        result = await auth_service.resend_verification(
            email='test@example.com', client_ip='127.0.0.1'
        )

        assert result is True
        mock_verification_repo.delete_by_user_id.assert_called_once()
        mock_verification_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_rate_limit(
        self,
        auth_service: AuthService,
        mock_rate_limiter: MagicMock,
    ) -> None:
        mock_rate_limiter.is_allowed.return_value = False

        with pytest.raises(RateLimitExceededError):
            await auth_service.resend_verification(
                email='test@example.com', client_ip='127.0.0.1'
            )

    @pytest.mark.asyncio
    async def test_returns_true_for_unknown_email(
        self,
        auth_service: AuthService,
        mock_rate_limiter: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        mock_user_repo.get_by_email.return_value = None

        result = await auth_service.resend_verification(
            email='unknown@example.com', client_ip='127.0.0.1'
        )

        assert result is True
