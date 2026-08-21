# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
# noqa: PLR6301,PLR2004
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid7

import pytest

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
    EmailChangeRequest,
    PasswordResetToken,
)
from questr.domains.users.repository import (
    Session as SessionDomain,
)
from questr.domains.users.service import (
    AccountService,
    EmailVerification,
    RoleService,
    SessionService,
    User,
    hash_password,
)
from questr.settings import settings


@pytest.fixture
def mock_user_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_username = AsyncMock(return_value=None)
    repo.get_by_email = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock()
    repo.update_status = AsyncMock()
    repo.update_password = AsyncMock()
    repo.update_email = AsyncMock()
    repo.set_email_hold = AsyncMock()
    repo.revert_email = AsyncMock()
    repo.get_by_email_or_previous = AsyncMock(return_value=None)
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
    service.send_password_changed_email = AsyncMock(return_value=True)
    service.send_password_reset_email = AsyncMock(return_value=True)
    service.send_password_reset_done_email = AsyncMock(return_value=True)
    service.send_email_change_confirm_email = AsyncMock(return_value=True)
    service.send_email_change_old_notification = AsyncMock(return_value=True)
    service.send_email_changed_notice = AsyncMock(return_value=True)
    service.send_email_change_reverted_notice = AsyncMock(return_value=True)
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
    repo.update_csrf_hash = AsyncMock()
    return repo


@pytest.fixture
def mock_audit_log_repo() -> MagicMock:
    repo = MagicMock()
    repo.insert = AsyncMock()
    return repo


@pytest.fixture
def mock_password_reset_token_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_token_hash = AsyncMock()
    repo.mark_as_used = AsyncMock()
    repo.delete_by_user_id = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_dual_rate_limiter() -> MagicMock:
    limiter = MagicMock()
    limiter.check_allowed = AsyncMock()
    limiter.consume_on_send = AsyncMock()
    return limiter


@pytest.fixture
def mock_email_change_repo() -> MagicMock:
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_token_hash = AsyncMock()
    repo.get_by_revert_token_hash = AsyncMock()
    repo.mark_as_used = AsyncMock()
    repo.mark_revert_as_used = AsyncMock()
    repo.delete_by_user_id = AsyncMock(return_value=0)
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
def account_service(
    mock_user_repo: MagicMock,
    mock_verification_repo: MagicMock,
    mock_email_service: MagicMock,
    mock_rate_limiter: MagicMock,
    mock_login_rate_limiter: MagicMock,
    mock_password_reset_token_repo: MagicMock,
    mock_audit_log_repo: MagicMock,
    mock_dual_rate_limiter: MagicMock,
    mock_email_change_repo: MagicMock,
) -> AccountService:
    return AccountService(
        user_repo=mock_user_repo,
        verification_repo=mock_verification_repo,
        email_service=mock_email_service,
        rate_limiter=mock_rate_limiter,
        login_rate_limiter=mock_login_rate_limiter,
        password_reset_token_repo=mock_password_reset_token_repo,
        audit_repo=mock_audit_log_repo,
        dual_rate_limiter=mock_dual_rate_limiter,
        email_change_repo=mock_email_change_repo,
    )


@pytest.fixture
def session_service(
    mock_user_repo: MagicMock,
    mock_session_repo: MagicMock,
    mock_audit_log_repo: MagicMock,
    mock_login_rate_limiter: MagicMock,
) -> SessionService:
    return SessionService(
        user_repo=mock_user_repo,
        session_repo=mock_session_repo,
        audit_repo=mock_audit_log_repo,
        login_rate_limiter=mock_login_rate_limiter,
    )


class TestSignup:
    @pytest.mark.asyncio
    async def test_creates_user_and_sends_email(
        self,
        account_service: AccountService,
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

        result = await account_service.signup(
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
        account_service: AccountService,
        mock_user_repo: MagicMock,
    ) -> None:
        mock_user_repo.get_by_username.return_value = User(
            id=uuid7(), username='testuser'
        )

        with pytest.raises(UserAlreadyExistsError):
            await account_service.signup(
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
        account_service: AccountService,
        mock_user_repo: MagicMock,
    ) -> None:
        mock_user_repo.get_by_username.return_value = None
        mock_user_repo.get_by_email.return_value = User(
            id=uuid7(), email='test@example.com'
        )

        with pytest.raises(UserAlreadyExistsError):
            await account_service.signup(
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
        account_service: AccountService,
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
        await account_service.signup(
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

        await account_service.signup(
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
        account_service: AccountService,
    ) -> None:
        with pytest.raises(ValueError, match='Passwords do not match'):
            await account_service.signup(
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
        account_service: AccountService,
    ) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            await account_service.signup(
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
        account_service: AccountService,
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

        result = await account_service.verify_email('raw_token')

        assert result.status == UserStatus.ACTIVE
        mock_user_repo.update_status.assert_called_once_with(
            user_id, UserStatus.ACTIVE
        )

    @pytest.mark.asyncio
    async def test_raises_on_invalid_token(
        self,
        account_service: AccountService,
        mock_verification_repo: MagicMock,
    ) -> None:
        mock_verification_repo.get_by_token_hash.return_value = None

        with pytest.raises(InvalidVerificationTokenError):
            await account_service.verify_email('invalid_token')

    @pytest.mark.asyncio
    async def test_raises_on_used_token(
        self,
        account_service: AccountService,
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
            await account_service.verify_email('used_token')

    @pytest.mark.asyncio
    async def test_raises_on_expired_token(
        self,
        account_service: AccountService,
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
            await account_service.verify_email('expired_token')


class TestResendVerification:
    @pytest.mark.asyncio
    async def test_creates_new_token_and_deletes_old(
        self,
        account_service: AccountService,
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

        result = await account_service.resend_verification(
            email='test@example.com', client_ip='127.0.0.1'
        )

        assert result is True
        mock_verification_repo.delete_by_user_id.assert_called_once()
        mock_verification_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_rate_limit(
        self,
        account_service: AccountService,
        mock_rate_limiter: MagicMock,
    ) -> None:
        mock_rate_limiter.is_allowed.return_value = False

        with pytest.raises(RateLimitExceededError):
            await account_service.resend_verification(
                email='test@example.com', client_ip='127.0.0.1'
            )

    @pytest.mark.asyncio
    async def test_returns_true_for_unknown_email(
        self,
        account_service: AccountService,
        mock_rate_limiter: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        mock_user_repo.get_by_email.return_value = None

        result = await account_service.resend_verification(
            email='unknown@example.com', client_ip='127.0.0.1'
        )

        assert result is True


class TestChangePassword:
    """Tests for AccountService.change_password()."""

    @pytest.mark.asyncio
    async def test_wrong_current_password_raises_and_records_failure(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """Gate 1: mismatch raises and records a failure."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )

        with pytest.raises(InvalidCurrentPasswordError):
            await account_service.change_password(
                user_id=user_id,
                current_password='wrong',
                new_password='NewPass1!',
                client_ip='127.0.0.1',
                user_agent='test',
            )

        mock_login_rate_limiter.record_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_locked_account_rejected_before_verify(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """Gate 1: check_login_allowed lockout short-circuits."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )
        mock_login_rate_limiter.check_login_allowed.side_effect = (
            RateLimitExceededError('locked')
        )

        with pytest.raises(RateLimitExceededError):
            await account_service.change_password(
                user_id=user_id,
                current_password='OldPass1!',
                new_password='NewPass1!',
                client_ip='127.0.0.1',
                user_agent='test',
            )

        mock_login_rate_limiter.record_failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_weak_new_password_raises_value_error(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """T-003: weak new password raises ValueError (400 at boundary)."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )

        with pytest.raises(ValueError):  # noqa: PT011
            await account_service.change_password(
                user_id=user_id,
                current_password='OldPass1!',
                new_password='weak',
                client_ip='127.0.0.1',
                user_agent='test',
            )

    @pytest.mark.asyncio
    async def test_success_updates_password_invalidates_tokens_and_audits(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
        mock_password_reset_token_repo: MagicMock,
        mock_audit_log_repo: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        """Gates 1+2: success updates hash, deletes reset tokens, audits."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.update_password.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            password_hash=hash_password('NewPass1!'),
            status=UserStatus.ACTIVE,
        )

        result = await account_service.change_password(
            user_id=user_id,
            current_password='OldPass1!',
            new_password='NewPass1!',
            client_ip='127.0.0.1',
            user_agent='test-agent',
        )

        assert result is not None
        mock_login_rate_limiter.record_success.assert_awaited_once()
        mock_user_repo.update_password.assert_awaited_once()
        mock_password_reset_token_repo.delete_by_user_id.assert_awaited_once_with(
            user_id
        )
        mock_audit_log_repo.insert.assert_awaited_once()
        audit = mock_audit_log_repo.insert.await_args.args[0]
        assert audit.action == AuditAction.PASSWORD_CHANGED
        assert audit.ip_address == '127.0.0.1'
        assert audit.user_agent == 'test-agent'
        mock_email_service.send_password_changed_email.assert_awaited_once_with(
            'test@example.com'
        )


class TestRequestPasswordReset:
    """Tests for AccountService.request_password_reset()."""

    @pytest.mark.asyncio
    async def test_unknown_email_returns_true_uniformly(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_dual_rate_limiter: MagicMock,
    ) -> None:
        """Gate 7: unknown email returns True (no enumeration)."""
        mock_user_repo.get_by_email_or_previous.return_value = None
        result = await account_service.request_password_reset(
            'nobody@example.com', '127.0.0.1', 'test'
        )
        assert result is True
        mock_dual_rate_limiter.consume_on_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_sends_reset_and_consumes(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_password_reset_token_repo: MagicMock,
        mock_email_service: MagicMock,
        mock_dual_rate_limiter: MagicMock,
    ) -> None:
        """Matrix D3: ACTIVE sends a reset and counts the send."""
        user_id = uuid7()
        mock_user_repo.get_by_email_or_previous.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            status=UserStatus.ACTIVE,
        )
        result = await account_service.request_password_reset(
            'test@example.com', '127.0.0.1', 'test'
        )
        assert result is True
        mock_password_reset_token_repo.delete_by_user_id.assert_awaited_once_with(
            user_id
        )
        mock_password_reset_token_repo.create.assert_awaited_once()
        mock_email_service.send_password_reset_email.assert_awaited_once()
        mock_dual_rate_limiter.consume_on_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pending_resends_verification(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_verification_repo: MagicMock,
        mock_email_service: MagicMock,
        mock_dual_rate_limiter: MagicMock,
    ) -> None:
        """Matrix D3: PENDING resends verification, no reset token."""
        user_id = uuid7()
        mock_user_repo.get_by_email_or_previous.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            status=UserStatus.PENDING,
        )
        result = await account_service.request_password_reset(
            'test@example.com', '127.0.0.1', 'test'
        )
        assert result is True
        mock_verification_repo.create.assert_awaited_once()
        mock_email_service.send_verification_email.assert_awaited_once()
        mock_dual_rate_limiter.consume_on_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_suspended_sends_nothing(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_email_service: MagicMock,
        mock_dual_rate_limiter: MagicMock,
    ) -> None:
        """Matrix D3: SUSPENDED sends nothing, uniform True."""
        mock_user_repo.get_by_email_or_previous.return_value = User(
            id=uuid7(),
            username='testuser',
            email='test@example.com',
            status=UserStatus.SUSPENDED,
        )
        result = await account_service.request_password_reset(
            'test@example.com', '127.0.0.1', 'test'
        )
        assert result is True
        mock_email_service.send_password_reset_email.assert_not_awaited()
        mock_dual_rate_limiter.consume_on_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rate_limited_raises(
        self,
        account_service: AccountService,
        mock_dual_rate_limiter: MagicMock,
    ) -> None:
        """Gate 6: check_allowed lockout raises."""
        mock_dual_rate_limiter.check_allowed.side_effect = (
            RateLimitExceededError('limited')
        )
        with pytest.raises(RateLimitExceededError):
            await account_service.request_password_reset(
                'test@example.com', '127.0.0.1', 'test'
            )


class TestResetPassword:
    """Tests for AccountService.reset_password()."""

    def _valid_token(self, user_id: UUID) -> PasswordResetToken:
        return PasswordResetToken(
            id=uuid7(),
            user_id=user_id,
            token_hash='hash',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    @pytest.mark.asyncio
    async def test_valid_token_resets_and_audits(
        self,
        account_service: AccountService,
        mock_password_reset_token_repo: MagicMock,
        mock_user_repo: MagicMock,
        mock_audit_log_repo: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        """Gate 2: valid token resets, invalidates tokens, audits."""
        user_id = uuid7()
        mock_password_reset_token_repo.get_by_token_hash.return_value = (
            self._valid_token(user_id)
        )
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )

        result = await account_service.reset_password(
            'rawtoken', 'NewPass1!', '127.0.0.1', 'test-agent'
        )

        assert result is not None
        mock_user_repo.update_password.assert_awaited_once()
        mock_password_reset_token_repo.delete_by_user_id.assert_awaited_once_with(
            user_id
        )
        mock_password_reset_token_repo.mark_as_used.assert_awaited_once()
        mock_audit_log_repo.insert.assert_awaited_once()
        audit = mock_audit_log_repo.insert.await_args.args[0]
        assert audit.action == AuditAction.PASSWORD_RESET
        assert audit.user_agent == 'test-agent'
        mock_email_service.send_password_reset_done_email.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_token_raises(
        self,
        account_service: AccountService,
        mock_password_reset_token_repo: MagicMock,
    ) -> None:
        """Expired token raises InvalidResetTokenError."""
        token = self._valid_token(uuid7())
        token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_password_reset_token_repo.get_by_token_hash.return_value = token

        with pytest.raises(InvalidResetTokenError):
            await account_service.reset_password(
                'rawtoken', 'NewPass1!', '127.0.0.1', 'test'
            )

    @pytest.mark.asyncio
    async def test_used_token_raises(
        self,
        account_service: AccountService,
        mock_password_reset_token_repo: MagicMock,
    ) -> None:
        """Used token raises InvalidResetTokenError (single-use)."""
        token = self._valid_token(uuid7())
        token.used_at = datetime.now(timezone.utc)
        mock_password_reset_token_repo.get_by_token_hash.return_value = token

        with pytest.raises(InvalidResetTokenError):
            await account_service.reset_password(
                'rawtoken', 'NewPass1!', '127.0.0.1', 'test'
            )

    @pytest.mark.asyncio
    async def test_suspended_account_raises(
        self,
        account_service: AccountService,
        mock_password_reset_token_repo: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """SUSPENDED account rejects the token uniformly."""
        user_id = uuid7()
        mock_password_reset_token_repo.get_by_token_hash.return_value = (
            self._valid_token(user_id)
        )
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            status=UserStatus.SUSPENDED,
        )

        with pytest.raises(InvalidResetTokenError):
            await account_service.reset_password(
                'rawtoken', 'NewPass1!', '127.0.0.1', 'test'
            )

    @pytest.mark.asyncio
    async def test_weak_password_raises_value_error(
        self,
        account_service: AccountService,
        mock_password_reset_token_repo: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """T-003: weak new password raises ValueError (400 at boundary)."""
        user_id = uuid7()
        mock_password_reset_token_repo.get_by_token_hash.return_value = (
            self._valid_token(user_id)
        )
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='test@example.com',
            status=UserStatus.ACTIVE,
        )

        with pytest.raises(ValueError):  # noqa: PT011
            await account_service.reset_password(
                'rawtoken', 'weak', '127.0.0.1', 'test'
            )


class TestRequestEmailChange:
    """Tests for AccountService.request_email_change()."""

    @pytest.mark.asyncio
    async def test_wrong_current_password_raises(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """Gate 1: mismatch raises and records a failure."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='old@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )

        with pytest.raises(InvalidCurrentPasswordError):
            await account_service.request_email_change(
                user_id=user_id,
                new_email='new@example.com',
                current_password='wrong',
                client_ip='127.0.0.1',
                user_agent='test',
            )
        mock_login_rate_limiter.record_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_email_raises(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """Gate 3: duplicate (incl. held previous_email) raises."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='old@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email_or_previous.return_value = User(
            id=uuid7(), username='other', email='new@example.com'
        )

        with pytest.raises(UserAlreadyExistsError):
            await account_service.request_email_change(
                user_id=user_id,
                new_email='new@example.com',
                current_password='OldPass1!',
                client_ip='127.0.0.1',
                user_agent='test',
            )

    @pytest.mark.asyncio
    async def test_success_creates_request_audits_and_sends(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
        mock_email_change_repo: MagicMock,
        mock_audit_log_repo: MagicMock,
        mock_email_service: MagicMock,
        mock_dual_rate_limiter: MagicMock,
    ) -> None:
        """Gates 1+3+4+6: success creates, audits, sends, consumes."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='old@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email_or_previous.return_value = None

        result = await account_service.request_email_change(
            user_id=user_id,
            new_email='new@example.com',
            current_password='OldPass1!',
            client_ip='127.0.0.1',
            user_agent='test-agent',
        )

        assert result is True
        mock_email_change_repo.delete_by_user_id.assert_awaited_once_with(
            user_id
        )
        mock_email_change_repo.create.assert_awaited_once()
        created = mock_email_change_repo.create.await_args.args[0]
        assert created.old_email == 'old@example.com'
        assert created.new_email == 'new@example.com'
        assert created.ip == '127.0.0.1'
        assert created.user_agent == 'test-agent'
        mock_audit_log_repo.insert.assert_awaited_once()
        audit = mock_audit_log_repo.insert.await_args.args[0]
        assert audit.action == AuditAction.EMAIL_CHANGE_REQUESTED
        mock_email_service.send_email_change_confirm_email.assert_awaited_once()
        mock_email_service.send_email_change_old_notification.assert_awaited_once()
        mock_dual_rate_limiter.consume_on_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rate_limited_raises(
        self,
        account_service: AccountService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
        mock_dual_rate_limiter: MagicMock,
    ) -> None:
        """Gate 6: check_allowed lockout raises."""
        user_id = uuid7()
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='old@example.com',
            password_hash=hash_password('OldPass1!'),
            status=UserStatus.ACTIVE,
        )
        mock_dual_rate_limiter.check_allowed.side_effect = (
            RateLimitExceededError('limited')
        )

        with pytest.raises(RateLimitExceededError):
            await account_service.request_email_change(
                user_id=user_id,
                new_email='new@example.com',
                current_password='OldPass1!',
                client_ip='127.0.0.1',
                user_agent='test',
            )


class TestConfirmEmailChange:
    """Tests for AccountService.confirm_email_change()."""

    def _request(self, user_id: UUID) -> EmailChangeRequest:
        return EmailChangeRequest(
            id=uuid7(),
            user_id=user_id,
            old_email='old@example.com',
            new_email='new@example.com',
            token_hash='hash',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            revert_token_hash='revert_hash',
        )

    @pytest.mark.asyncio
    async def test_valid_token_confirms_and_sets_hold(
        self,
        account_service: AccountService,
        mock_email_change_repo: MagicMock,
        mock_user_repo: MagicMock,
        mock_password_reset_token_repo: MagicMock,
        mock_audit_log_repo: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        """Gates 2+3: confirm sets hold, invalidates reset tokens, audits."""
        user_id = uuid7()
        mock_email_change_repo.get_by_token_hash.return_value = self._request(
            user_id
        )
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='old@example.com',
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email_or_previous.return_value = None

        result = await account_service.confirm_email_change(
            'rawtoken', '127.0.0.1', 'test-agent'
        )

        assert result is not None
        mock_user_repo.update_email.assert_awaited_once_with(
            user_id, 'new@example.com'
        )
        mock_user_repo.set_email_hold.assert_awaited_once_with(
            user_id, 'old@example.com'
        )
        mock_password_reset_token_repo.delete_by_user_id.assert_awaited_once_with(
            user_id
        )
        mock_email_change_repo.mark_as_used.assert_awaited_once()
        mock_audit_log_repo.insert.assert_awaited_once()
        audit = mock_audit_log_repo.insert.await_args.args[0]
        assert audit.action == AuditAction.EMAIL_CHANGED
        mock_email_service.send_email_changed_notice.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_token_raises(
        self,
        account_service: AccountService,
        mock_email_change_repo: MagicMock,
    ) -> None:
        request = self._request(uuid7())
        request.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_email_change_repo.get_by_token_hash.return_value = request

        with pytest.raises(InvalidResetTokenError):
            await account_service.confirm_email_change(
                'rawtoken', '127.0.0.1', 'test'
            )

    @pytest.mark.asyncio
    async def test_duplicate_new_email_raises(
        self,
        account_service: AccountService,
        mock_email_change_repo: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        user_id = uuid7()
        mock_email_change_repo.get_by_token_hash.return_value = self._request(
            user_id
        )
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='old@example.com',
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_email_or_previous.return_value = User(
            id=uuid7(), username='other', email='new@example.com'
        )

        with pytest.raises(UserAlreadyExistsError):
            await account_service.confirm_email_change(
                'rawtoken', '127.0.0.1', 'test'
            )


class TestRevertEmailChange:
    """Tests for AccountService.revert_email_change()."""

    def _request(self, user_id: UUID) -> EmailChangeRequest:
        return EmailChangeRequest(
            id=uuid7(),
            user_id=user_id,
            old_email='old@example.com',
            new_email='new@example.com',
            token_hash='confirm_hash',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            revert_token_hash='revert_hash',
        )

    @pytest.mark.asyncio
    async def test_valid_revert_restores_and_clears_hold(
        self,
        account_service: AccountService,
        mock_email_change_repo: MagicMock,
        mock_user_repo: MagicMock,
        mock_password_reset_token_repo: MagicMock,
        mock_audit_log_repo: MagicMock,
        mock_email_service: MagicMock,
    ) -> None:
        """Gates 2+4: revert restores old email, clears hold, audits."""
        user_id = uuid7()
        mock_email_change_repo.get_by_revert_token_hash.return_value = (
            self._request(user_id)
        )
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='new@example.com',
            previous_email='old@example.com',
            email_changed_at=datetime.now(timezone.utc),
            status=UserStatus.ACTIVE,
        )

        result = await account_service.revert_email_change(
            'rawrevert', '127.0.0.1', 'test-agent'
        )

        assert result is not None
        mock_user_repo.revert_email.assert_awaited_once_with(user_id)
        mock_password_reset_token_repo.delete_by_user_id.assert_awaited_once_with(
            user_id
        )
        mock_email_change_repo.mark_revert_as_used.assert_awaited_once()
        mock_audit_log_repo.insert.assert_awaited_once()
        audit = mock_audit_log_repo.insert.await_args.args[0]
        assert audit.action == AuditAction.EMAIL_CHANGE_REVERTED
        mock_email_service.send_email_change_reverted_notice.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revert_after_hold_expiry_raises(
        self,
        account_service: AccountService,
        mock_email_change_repo: MagicMock,
        mock_user_repo: MagicMock,
    ) -> None:
        """Gate 4: revert after the hold window is rejected."""
        user_id = uuid7()
        mock_email_change_repo.get_by_revert_token_hash.return_value = (
            self._request(user_id)
        )
        mock_user_repo.get_by_id.return_value = User(
            id=user_id,
            username='testuser',
            email='new@example.com',
            previous_email='old@example.com',
            email_changed_at=(
                datetime.now(timezone.utc) - timedelta(hours=49)
            ),
            status=UserStatus.ACTIVE,
        )

        with pytest.raises(InvalidResetTokenError):
            await account_service.revert_email_change(
                'rawrevert', '127.0.0.1', 'test'
            )

    @pytest.mark.asyncio
    async def test_used_revert_token_raises(
        self,
        account_service: AccountService,
        mock_email_change_repo: MagicMock,
    ) -> None:
        request = self._request(uuid7())
        request.revert_used_at = datetime.now(timezone.utc)
        mock_email_change_repo.get_by_revert_token_hash.return_value = request

        with pytest.raises(InvalidResetTokenError):
            await account_service.revert_email_change(
                'rawrevert', '127.0.0.1', 'test'
            )


class TestLogin:
    """Tests for SessionService.login()."""

    @pytest.mark.asyncio
    async def test_login_success_returns_session_and_csrf_token(
        self,
        session_service: SessionService,
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
            result = await session_service.login(
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
        session_service: SessionService,
        mock_user_repo: MagicMock,
    ) -> None:
        """AC-2: Unknown email -> dummy verify + generic 401."""
        mock_user_repo.get_by_email.return_value = None

        with pytest.raises(AuthenticationError):
            await session_service.login(
                email='unknown@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

    @pytest.mark.asyncio
    async def test_login_wrong_password_increments_failures_raises_generic(  # noqa: E501
        self,
        session_service: SessionService,
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
            await session_service.login(
                email='test@example.com',
                password='WrongPass1!',
                client_ip='127.0.0.1',
            )

        mock_login_rate_limiter.record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_unknown_email_records_ip_attempt(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """FR-007: no-user attempts count toward the per-IP window."""
        mock_user_repo.get_by_email.return_value = None

        with pytest.raises(AuthenticationError):
            await session_service.login(
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
        session_service: SessionService,
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
            await session_service.login(
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
        session_service: SessionService,
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
            await session_service.login(
                email='test@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

    @pytest.mark.asyncio
    async def test_login_locked_account_rejects_without_verify(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_login_rate_limiter: MagicMock,
    ) -> None:
        """AC-3: Lockout branch rejects without burning Argon2 CPU."""
        mock_login_rate_limiter.check_login_allowed.side_effect = (
            RateLimitExceededError('Account locked')
        )

        with pytest.raises(RateLimitExceededError):
            await session_service.login(
                email='test@example.com',
                password='StrongPass1!',
                client_ip='127.0.0.1',
            )

        mock_user_repo.get_by_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_eleventh_session_raises_too_many_active(
        self,
        session_service: SessionService,
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
                await session_service.login(
                    email='test@example.com',
                    password='StrongPass1!',
                    client_ip='127.0.0.1',
                )


class TestValidateSession:
    """Tests for SessionService.validate_session()."""

    @pytest.mark.asyncio
    async def test_validate_session_writes_last_activity_eagerly(
        self,
        session_service: SessionService,
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

        result = await session_service.validate_session(session_id)

        assert result is not None
        assert result.user is not None
        assert result.is_impersonation is False
        assert result.impersonator_session_id is None
        mock_session_repo.update_last_activity.assert_called_once()
        # FR-005: the idle window slides forward from the request time.
        call = mock_session_repo.update_last_activity.call_args
        assert call.args[2] - call.args[1] == timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_validate_session_idle_expired_deactivates_raises(
        self,
        session_service: SessionService,
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
            await session_service.validate_session(session.id)

        mock_session_repo.deactivate.assert_called_once_with(session.id)

    @pytest.mark.asyncio
    async def test_validate_session_absolute_expired_deactivates_raises(
        self,
        session_service: SessionService,
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
            await session_service.validate_session(session.id)

        mock_session_repo.deactivate.assert_called_once_with(session.id)


class TestStopImpersonationService:
    """Tests for SessionService.stop_impersonation() admin re-validation.

    The plan names validate_session as the re-validation mechanism for
    the linked admin session at stop time. An admin session that
    idle- or absolute-expired during impersonation must cause stop to
    raise AuthenticationError and the admin session to be deactivated,
    rather than succeeding against a dead admin session.
    """

    @pytest.mark.asyncio
    async def test_idle_expired_admin_session_raises_and_deactivates(
        self,
        session_service: SessionService,
        mock_session_repo: MagicMock,
    ) -> None:
        now = datetime.now(timezone.utc)
        admin_id = uuid7()
        admin_session_id = uuid7()
        impersonation_session_id = uuid7()

        impersonation_session = SessionDomain(
            id=impersonation_session_id,
            user_id=uuid7(),
            is_active=True,
            issued_at=now - timedelta(minutes=20),
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
            absolute_expires_at=now + timedelta(minutes=40),
            ip_address='127.0.0.1',
            user_agent='pytest',
            impersonator_id=admin_id,
            impersonator_session_id=admin_session_id,
        )
        admin_session = SessionDomain(
            id=admin_session_id,
            user_id=admin_id,
            is_active=True,
            issued_at=now - timedelta(hours=2),
            last_activity=now - timedelta(minutes=45),  # past idle 30 min
            expires_at=now - timedelta(minutes=15),  # idle expired
            absolute_expires_at=now + timedelta(hours=6),
            ip_address='127.0.0.1',
            user_agent='pytest',
        )
        # First get_by_id: impersonation session. Second: admin
        # session via re-validation.
        mock_session_repo.get_by_id.side_effect = [
            impersonation_session,
            admin_session,
        ]

        with pytest.raises(AuthenticationError):
            await session_service.stop_impersonation(impersonation_session_id)

        # Admin session must have been deactivated by re-validation.
        mock_session_repo.deactivate.assert_called_with(admin_session_id)

    @pytest.mark.asyncio
    async def test_absolute_expired_admin_session_raises(
        self,
        session_service: SessionService,
        mock_session_repo: MagicMock,
    ) -> None:
        now = datetime.now(timezone.utc)
        admin_id = uuid7()
        admin_session_id = uuid7()
        impersonation_session_id = uuid7()

        impersonation_session = SessionDomain(
            id=impersonation_session_id,
            user_id=uuid7(),
            is_active=True,
            issued_at=now - timedelta(minutes=20),
            last_activity=now,
            expires_at=now + timedelta(minutes=30),
            absolute_expires_at=now + timedelta(minutes=40),
            ip_address='127.0.0.1',
            user_agent='pytest',
            impersonator_id=admin_id,
            impersonator_session_id=admin_session_id,
        )
        admin_session = SessionDomain(
            id=admin_session_id,
            user_id=admin_id,
            is_active=True,
            issued_at=now - timedelta(hours=12),
            last_activity=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=25),
            absolute_expires_at=now - timedelta(hours=1),  # absolute expired
            ip_address='127.0.0.1',
            user_agent='pytest',
        )
        mock_session_repo.get_by_id.side_effect = [
            impersonation_session,
            admin_session,
        ]

        with pytest.raises(AuthenticationError):
            await session_service.stop_impersonation(impersonation_session_id)

        mock_session_repo.deactivate.assert_called_with(admin_session_id)


class TestLogout:
    """Tests for SessionService.logout() and logout_all()."""

    @pytest.mark.asyncio
    async def test_logout_deactivates_only_current_session(
        self,
        session_service: SessionService,
        mock_session_repo: MagicMock,
    ) -> None:
        """AC-6: logout invalidates only the current session."""
        session_id = uuid7()

        await session_service.logout(session_id)

        mock_session_repo.deactivate.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_logout_all_revokes_all_and_returns_count(
        self,
        session_service: SessionService,
        mock_session_repo: MagicMock,
    ) -> None:
        """AC-6: logout_all revokes every active session, returns count."""
        user_id = uuid7()
        mock_session_repo.revoke_all_for_user.return_value = 5

        count = await session_service.logout_all(user_id)

        assert count == 5
        mock_session_repo.revoke_all_for_user.assert_called_once_with(
            user_id, None
        )

    @pytest.mark.asyncio
    async def test_auth_logs_contain_only_allowed_keys(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        caplog: object,
    ) -> None:
        """AC-7: Log records contain none of the NFR-005 excluded fields."""
        caplog.set_level(logging.INFO)

        # Trigger a login that fails generically (no user)
        mock_user_repo.get_by_email.return_value = None

        with pytest.raises(AuthenticationError):
            await session_service.login(
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


class TestLoginContractFixes:
    """Review 2026-07-21: settings consumption + session-record contract."""

    @staticmethod
    def _active_user(user_id: object) -> User:
        return User(
            id=user_id,  # type: ignore[arg-type]
            username='testuser',
            email='test@example.com',
            password_hash='$argon2id$v=19$m=65536,t=3,p=4$mockhash',
            status=UserStatus.ACTIVE,
        )

    async def _login_ok(
        self,
        session_service: SessionService,
        **kwargs: object,
    ) -> object:
        args: dict[str, object] = {
            'email': 'test@example.com',
            'password': 'StrongPass1!',
            'client_ip': '127.0.0.1',
        }
        args.update(kwargs)
        with patch(
            'questr.domains.users.service.verify_password', return_value=True
        ):
            return await session_service.login(**args)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_login_reads_lifetimes_from_settings(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Review Issue 1: session lifetimes come from settings."""
        monkeypatch.setattr(settings, 'SESSION_IDLE_MINUTES', 5)
        monkeypatch.setattr(settings, 'SESSION_ABSOLUTE_HOURS', 1)
        monkeypatch.setattr(settings, 'SESSION_REMEMBER_DAYS', 2)
        mock_user_repo.get_by_email.return_value = self._active_user(uuid7())
        mock_session_repo.count_active_for_user.return_value = 0

        await self._login_ok(session_service)
        created = mock_session_repo.create.call_args.args[0]
        assert created.expires_at - created.issued_at == timedelta(minutes=5)
        assert created.absolute_expires_at - created.issued_at == timedelta(
            hours=1
        )

        mock_session_repo.create.reset_mock()
        await self._login_ok(session_service, remember_me=True)
        created = mock_session_repo.create.call_args.args[0]
        assert created.absolute_expires_at - created.issued_at == timedelta(
            days=2
        )

    @pytest.mark.asyncio
    async def test_login_reads_session_cap_from_settings(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Review Issue 1: the concurrent-session cap comes from settings."""
        monkeypatch.setattr(settings, 'MAX_CONCURRENT_SESSIONS', 3)
        mock_user_repo.get_by_email.return_value = self._active_user(uuid7())
        mock_session_repo.count_active_for_user.return_value = 3

        with pytest.raises(TooManyActiveSessionsError):
            await self._login_ok(session_service)

    @pytest.mark.asyncio
    async def test_login_persists_user_agent(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
    ) -> None:
        """Review Issue 2 / FR-013: the session record stores User-Agent."""
        mock_user_repo.get_by_email.return_value = self._active_user(uuid7())
        mock_session_repo.count_active_for_user.return_value = 0

        await self._login_ok(session_service, user_agent='TestAgent/1.0')
        created = mock_session_repo.create.call_args.args[0]
        assert created.user_agent == 'TestAgent/1.0'

    @pytest.mark.asyncio
    async def test_login_truncates_user_agent_to_512(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
    ) -> None:
        """Design §5: over-length User-Agent is truncated (codepoint-safe)."""
        mock_user_repo.get_by_email.return_value = self._active_user(uuid7())
        mock_session_repo.count_active_for_user.return_value = 0

        await self._login_ok(session_service, user_agent='A' * 600)
        created = mock_session_repo.create.call_args.args[0]
        assert created.user_agent == 'A' * 512

    @pytest.mark.asyncio
    async def test_login_stores_valid_ip_as_is(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
    ) -> None:
        """Design §5: a parseable IP is stored unchanged."""
        mock_user_repo.get_by_email.return_value = self._active_user(uuid7())
        mock_session_repo.count_active_for_user.return_value = 0

        await self._login_ok(session_service, client_ip='203.0.113.7')
        created = mock_session_repo.create.call_args.args[0]
        assert created.ip_address == '203.0.113.7'

    @pytest.mark.asyncio
    async def test_login_sanitizes_garbage_ip_to_unknown(
        self,
        session_service: SessionService,
        mock_user_repo: MagicMock,
        mock_session_repo: MagicMock,
    ) -> None:
        """Design §5: a non-IP X-Forwarded-For value becomes 'unknown'."""
        mock_user_repo.get_by_email.return_value = self._active_user(uuid7())
        mock_session_repo.count_active_for_user.return_value = 0

        await self._login_ok(session_service, client_ip='not-an-ip-address')
        created = mock_session_repo.create.call_args.args[0]
        assert created.ip_address == 'unknown'


class TestRoleServiceChangeRole:
    """Tests for RoleService.change_role() planned signature.

    Planned signature: ``change_role(*, actor, target_id, new_role,
    ip, user_agent) -> AuditLog`` with ip/user_agent recorded on the
    audit row (F5). The service fetches the target itself
    (needs old_role).
    """

    @pytest.fixture
    def role_service(
        self,
        mock_user_repo: MagicMock,
        mock_audit_log_repo: MagicMock,
    ) -> RoleService:
        return RoleService(
            user_repo=mock_user_repo,
            audit_repo=mock_audit_log_repo,
        )

    @pytest.mark.asyncio
    async def test_change_role_returns_audit_log_with_ip_user_agent(
        self,
        role_service: RoleService,
        mock_user_repo: MagicMock,
        mock_audit_log_repo: MagicMock,
    ) -> None:
        actor = User(
            id=uuid7(),
            username='admin',
            role=UserRole.SUPERUSER,
            status=UserStatus.ACTIVE,
        )
        target = User(
            id=uuid7(),
            username='target',
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        updated = User(
            id=target.id,
            username='target',
            role=UserRole.SUPERUSER,
            status=UserStatus.ACTIVE,
        )
        mock_user_repo.get_by_id.return_value = target
        mock_user_repo.update_role = AsyncMock(return_value=updated)
        persisted = AuditLog(
            id=uuid7(),
            action=AuditAction.ROLE_GRANTED,
            actor_id=actor.id,
            target_id=target.id,
            ip_address='1.2.3.4',
            user_agent='pytest-role-ua',
        )
        mock_audit_log_repo.insert = AsyncMock(return_value=persisted)

        result = await role_service.change_role(
            actor=actor,
            target_id=target.id,
            new_role=UserRole.SUPERUSER,
            ip='1.2.3.4',
            user_agent='pytest-role-ua',
        )

        # Service returns the persisted AuditLog.
        assert result is persisted
        mock_user_repo.get_by_id.assert_called_once_with(target.id)
        # The AuditLog passed to the repo carries ip/user_agent (F5).
        sent = mock_audit_log_repo.insert.call_args.args[0]
        assert isinstance(sent, AuditLog)
        assert sent.ip_address == '1.2.3.4'
        assert sent.user_agent == 'pytest-role-ua'
        assert sent.action == AuditAction.ROLE_GRANTED

    @pytest.mark.asyncio
    async def test_change_role_unknown_target_raises(
        self,
        role_service: RoleService,
        mock_user_repo: MagicMock,
    ) -> None:
        mock_user_repo.get_by_id.return_value = None

        with pytest.raises(AuthenticationError):
            await role_service.change_role(
                actor=User(id=uuid7(), role=UserRole.SUPERUSER),
                target_id=uuid7(),
                new_role=UserRole.SUPERUSER,
                ip='1.2.3.4',
                user_agent='ua',
            )
