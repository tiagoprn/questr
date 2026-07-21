# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
# noqa: PLR6301,PLR2004
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid7

import pytest

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
from questr.domains.users.repository import Session as SessionDomain
from questr.domains.users.service import AuthService, EmailVerification, User


@pytest.fixture
def mock_user_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_username = AsyncMock(return_value=None)
    repo.get_by_email = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock()
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
def mock_session_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.deactivate = AsyncMock(return_value=True)
    repo.revoke_all_for_user = AsyncMock(return_value=0)
    repo.count_active_for_user = AsyncMock(return_value=0)
    repo.update_last_activity = AsyncMock()
    return repo


@pytest.fixture
def mock_login_rate_limiter() -> MagicMock:
    limiter = MagicMock()
    limiter.check_login_allowed = AsyncMock()
    limiter.record_failure = AsyncMock()
    limiter.record_success = AsyncMock()
    limiter.record_ip_attempt = AsyncMock()
    return limiter


@pytest.fixture
def auth_service(
    mock_user_repo: MagicMock,
    mock_verification_repo: MagicMock,
    mock_email_service: MagicMock,
    mock_rate_limiter: MagicMock,
    mock_session_repo: MagicMock,
    mock_login_rate_limiter: MagicMock,
) -> AuthService:
    return AuthService(
        user_repo=mock_user_repo,
        verification_repo=mock_verification_repo,
        email_service=mock_email_service,
        rate_limiter=mock_rate_limiter,
        session_repo=mock_session_repo,
        login_rate_limiter=mock_login_rate_limiter,
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
    async def test_plus_tag_emails_are_distinct(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
    ) -> None:
        """Two emails with same base but different + tags are distinct."""
        # Arrange: first email exists
        mock_user_repo.get_by_email.side_effect = [
            None,  # first call: email1 not found
            User(id=uuid7(), email='base+tag1@example.com'),  # found
        ]
        mock_user_repo.get_by_username.return_value = None
        mock_user_repo.create.return_value = User(
            id=uuid7(),
            username='plususer1',
            email='base+tag1@example.com',
            first_name='Plus',
            last_name='One',
            password_hash='hashed',
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )

        # Act: signup with tag1 succeeds
        await auth_service.signup(
            username='plususer1',
            email='base+tag1@example.com',
            first_name='Plus',
            last_name='One',
            password='StrongPass1!',
            password_confirmation='StrongPass1!',
            client_ip='127.0.0.1',
        )

        # Act: signup with tag2 should also succeed (distinct email)
        mock_user_repo.get_by_email.side_effect = [
            None,  # email2 not found
            None,  # for good measure (get_by_username is mocked separately)
        ]
        mock_user_repo.get_by_username.return_value = None
        mock_user_repo.create.return_value = User(
            id=uuid7(),
            username='plususer2',
            email='base+tag2@example.com',
            first_name='Plus',
            last_name='Two',
            password_hash='hashed',
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )

        await auth_service.signup(
            username='plususer2',
            email='base+tag2@example.com',
            first_name='Plus',
            last_name='Two',
            password='StrongPass1!',
            password_confirmation='StrongPass1!',
            client_ip='127.0.0.1',
        )
        # No exception means both registrations were distinct

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


class TestLogin:
    """Tests for AuthService.login()."""

    @pytest.mark.asyncio
    async def test_login_success_returns_session_and_csrf_token(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """AC-1: Successful login returns user + session + CSRF token."""
        user_id = uuid7()
        user = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            first_name='Test',
            last_name='User',
            password_hash='$argon2id$v=19$m=65536,t=3,p=4$mockhash',
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email.return_value = user

        mock_session_repo.create.return_value = SessionDomain(
            id=uuid7(),
            user_id=user_id,
            issued_at=datetime.now(timezone.utc),
        )
        mock_session_repo.count_active_for_user.return_value = 0

        with patch(
            'questr.domains.users.service.verify_password', return_value=True
        ):
            result = await auth_service.login(
                email='test@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

        assert result['user'] is not None
        assert result['session'] is not None
        assert result['csrf_token'] is not None
        assert len(result['csrf_token']) > 0
        mock_session_repo.create.assert_called_once()
        mock_login_rate_limiter.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_unknown_email_runs_dummy_verify_raises_generic(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
    ) -> None:
        """AC-2: Unknown email -> dummy verify + generic 401."""
        mock_user_repo.get_by_email.return_value = None

        with pytest.raises(AuthenticationError):
            await auth_service.login(
                email='unknown@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

    @pytest.mark.asyncio
    async def test_login_wrong_password_increments_failures_raises_generic(  # noqa: E501
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """AC-2: Wrong password -> increment failure + generic 401."""
        user = User(
            id=uuid7(),
            username='testuser',
            email='test@example.com',
            password_hash='$argon2id$v=19$m=65536,t=3,p=4$mockhash',
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email.return_value = user

        with pytest.raises(AuthenticationError):
            await auth_service.login(
                email='test@example.com',
                password='WrongPass1!',
                client_ip='127.0.0.1',
            )

        mock_login_rate_limiter.record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_unknown_email_records_ip_attempt(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """FR-007: no-user attempts count toward the per-IP window."""
        mock_user_repo.get_by_email.return_value = None

        with pytest.raises(AuthenticationError):
            await auth_service.login(
                email='unknown@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

        mock_login_rate_limiter.record_ip_attempt.assert_called_once_with(
            '127.0.0.1'
        )
        mock_login_rate_limiter.record_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_success_records_ip_attempt(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """FR-007: successful logins also count toward the IP window."""
        user_id = uuid7()
        user = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            password_hash='$argon2id$v=19$m=65536,t=3,p=4$mockhash',
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email.return_value = user
        mock_session_repo.create.return_value = SessionDomain(
            id=uuid7(),
            user_id=user_id,
            issued_at=datetime.now(timezone.utc),
        )
        mock_session_repo.count_active_for_user.return_value = 0

        with patch(
            'questr.domains.users.service.verify_password', return_value=True
        ):
            await auth_service.login(
                email='test@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

        mock_login_rate_limiter.record_ip_attempt.assert_called_once_with(
            '127.0.0.1'
        )
        mock_login_rate_limiter.record_success.assert_called_once()

    @pytest.mark.parametrize(
        ('status', 'expected'),
        [
            (UserStatus.PENDING, EmailNotVerifiedError),
            (UserStatus.SUSPENDED, AccountSuspendedError),
            (UserStatus.BANNED, AccountBannedError),
        ],
    )
    @pytest.mark.asyncio
    async def test_login_non_active_status_raises_structured(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        status: UserStatus,
        expected: type,
    ) -> None:
        """AC-2: Non-ACTIVE status -> verify-and-discard + structured 403."""
        user = User(
            id=uuid7(),
            username='testuser',
            email='test@example.com',
            password_hash='$argon2id$v=19$m=65536,t=3,p=4$mockhash',
            status=status,
        )
        mock_user_repo.get_by_email.return_value = user

        with pytest.raises(expected):
            await auth_service.login(
                email='test@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

    @pytest.mark.asyncio
    async def test_login_locked_account_rejects_without_verify(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """AC-3: Lockout branch rejects without burning Argon2 CPU."""
        mock_login_rate_limiter.check_login_allowed.side_effect = (
            RateLimitExceededError('Account locked')
        )

        with pytest.raises(RateLimitExceededError):
            await auth_service.login(
                email='test@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

        mock_user_repo.get_by_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_eleventh_session_raises_too_many_active(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
    ) -> None:
        """AC-4: 11th concurrent session raises TooManyActiveSessionsError."""
        user = User(
            id=uuid7(),
            username='testuser',
            email='test@example.com',
            password_hash='$argon2id$v=19$m=65536,t=3,p=4$mockhash',
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email.return_value = user
        mock_session_repo.count_active_for_user.return_value = 11  # >= MAX

        with patch(
            'questr.domains.users.service.verify_password', return_value=True
        ):
            with pytest.raises(TooManyActiveSessionsError):
                await auth_service.login(
                    email='test@example.com',
                    password='StrongPass1!',
                    client_ip='127.0.0.1',
                )


class TestValidateSession:
    """Tests for AuthService.validate_session()."""

    @pytest.mark.asyncio
    async def test_validate_session_writes_last_activity_eagerly(
        self,
        auth_service: AuthService,
        mock_session_repo: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """AC-5: validate_session resets the idle window eagerly."""
        user_id = uuid7()
        session_id = uuid7()
        now = datetime.now(timezone.utc)

        session = SessionDomain(
            id=session_id,
            user_id=user_id,
            is_active=True,
            issued_at=now,
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
            absolute_expires_at=now + timedelta(hours=8),
            ip_address='127.0.0.1',
            user_agent='pytest',
        )
        mock_session_repo.get_by_id.return_value = session
        mock_user_repo.get_by_id.return_value = User(
            id=user_id, username='testuser'
        )

        result = await auth_service.validate_session(session_id)

        assert result is not None
        mock_session_repo.update_last_activity.assert_called_once()
        # FR-005: the idle window slides forward from the request time.
        call = mock_session_repo.update_last_activity.call_args
        assert call.args[2] - call.args[1] == timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_validate_session_idle_expired_deactivates_raises(
        self,
        auth_service: AuthService,
        mock_session_repo: MagicMock,
    ) -> None:
        """AC-5: Idle expiry deactivates session and raises."""
        now = datetime.now(timezone.utc)
        session = SessionDomain(
            id=uuid7(),
            user_id=uuid7(),
            is_active=True,
            issued_at=now - timedelta(hours=2),
            last_activity=now - timedelta(minutes=45),  # past idle 30 min
            expires_at=now - timedelta(minutes=15),  # expired
            absolute_expires_at=now + timedelta(hours=6),
            ip_address='127.0.0.1',
            user_agent='pytest',
        )
        mock_session_repo.get_by_id.return_value = session

        with pytest.raises(AuthenticationError):
            await auth_service.validate_session(session.id)

        mock_session_repo.deactivate.assert_called_once_with(session.id)

    @pytest.mark.asyncio
    async def test_validate_session_absolute_expired_deactivates_raises(
        self,
        auth_service: AuthService,
        mock_session_repo: MagicMock,
    ) -> None:
        """AC-5: Absolute expiry deactivates session and raises."""
        now = datetime.now(timezone.utc)
        session = SessionDomain(
            id=uuid7(),
            user_id=uuid7(),
            is_active=True,
            issued_at=now - timedelta(hours=12),
            last_activity=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=25),
            absolute_expires_at=now - timedelta(hours=1),  # past absolute
            ip_address='127.0.0.1',
            user_agent='pytest',
        )
        mock_session_repo.get_by_id.return_value = session

        with pytest.raises(AuthenticationError):
            await auth_service.validate_session(session.id)

        mock_session_repo.deactivate.assert_called_once_with(session.id)


class TestLogout:
    """Tests for AuthService.logout() and logout_all()."""

    @pytest.mark.asyncio
    async def test_logout_deactivates_only_current_session(
        self,
        auth_service: AuthService,
        mock_session_repo: MagicMock,
    ) -> None:
        """AC-6: logout invalidates only the current session."""
        session_id = uuid7()

        await auth_service.logout(session_id)

        mock_session_repo.deactivate.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_logout_all_revokes_all_and_returns_count(
        self,
        auth_service: AuthService,
        mock_session_repo: MagicMock,
    ) -> None:
        """AC-6: logout_all revokes every active session, returns count."""
        user_id = uuid7()
        mock_session_repo.revoke_all_for_user.return_value = 5

        count = await auth_service.logout_all(user_id)

        assert count == 5
        mock_session_repo.revoke_all_for_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_auth_logs_contain_only_allowed_keys(
        self,
        auth_service: AuthService,
        mock_user_repo: MagicMock,
        caplog: object,
    ) -> None:
        """AC-7: Log records contain none of the NFR-005 excluded fields."""
        caplog.set_level(logging.INFO)

        # Trigger a login that fails generically (no user)
        mock_user_repo.get_by_email.return_value = None

        with pytest.raises(AuthenticationError):
            await auth_service.login(
                email='test@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

        # Check that log records exist for questr.auth
        auth_logs = [r for r in caplog.records if r.name == 'questr.auth']
        assert len(auth_logs) > 0

        excluded_keys = {
            'email',
            'password',
            'password_hash',
            'csrf_token',
            'session_id',
            'user_agent',
        }
        for record in auth_logs:
            msg = str(record.message).lower()
            for key in excluded_keys:
                assert key not in msg, (
                    f'Excluded key "{key}" found in log: {msg}'
                )
