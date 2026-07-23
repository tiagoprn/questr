from __future__ import annotations

import pytest

from questr.common.exceptions import (
    AccountBannedError,
    AccountSuspendedError,
    EmailNotVerifiedError,
    RateLimiterUnavailableError,
    RateLimitExceededError,
    TooManyActiveSessionsError,
)
from questr.settings import settings


def test_structured_exception_exposes_error_code() -> None:
    """AC-2: StructuredQuestrException instances expose .error_code."""
    error = RateLimiterUnavailableError()
    assert hasattr(error, 'error_code')
    assert isinstance(error.error_code, str)
    assert len(error.error_code) > 0


class TestNewExceptionsAreStructured:
    """AC-2: New exceptions carry error_code."""

    @pytest.mark.parametrize(
        ('exception_cls', 'expected_code'),
        [
            (AccountBannedError, 'account_banned'),
            (TooManyActiveSessionsError, 'too_many_active_sessions'),
            (RateLimiterUnavailableError, 'rate_limiter_unavailable'),
        ],
    )
    def test_exception_has_correct_code(
        self,
        exception_cls: type,
        expected_code: str,
    ) -> None:
        error = exception_cls()
        assert error.error_code == expected_code


class TestExistingExceptionsRetrofitted:
    """AC-2: Existing exceptions now carry error_code."""

    @pytest.mark.parametrize(
        ('exception_cls', 'expected_code'),
        [
            (EmailNotVerifiedError, 'email_not_verified'),
            (AccountSuspendedError, 'account_suspended'),
            (RateLimitExceededError, 'rate_limited'),
        ],
    )
    def test_exception_has_correct_code(
        self,
        exception_cls: type,
        expected_code: str,
    ) -> None:
        error = exception_cls()
        assert error.error_code == expected_code


def test_settings_expose_login_and_session_constants() -> None:
    """AC-1: All ten settings exist with design defaults."""
    assert settings.LOGIN_PER_ACCOUNT_MAX_ATTEMPTS == 5  # noqa: PLR2004
    assert settings.LOGIN_PER_ACCOUNT_WINDOW_MINUTES == 15  # noqa: PLR2004
    assert settings.LOGIN_LOCKOUT_MINUTES == 30  # noqa: PLR2004
    assert settings.LOGIN_PER_IP_MAX_ATTEMPTS == 20  # noqa: PLR2004
    assert settings.LOGIN_PER_IP_WINDOW_MINUTES == 10  # noqa: PLR2004
    assert settings.SESSION_IDLE_MINUTES == 30  # noqa: PLR2004
    assert settings.SESSION_ABSOLUTE_HOURS == 8  # noqa: PLR2004
    assert settings.SESSION_REMEMBER_DAYS == 30  # noqa: PLR2004
    assert settings.MAX_CONCURRENT_SESSIONS == 10  # noqa: PLR2004
    assert settings.SECURE_COOKIE is False  # noqa: FBT003 -- dev default; prod is locked True via ENVIRONMENT=prod
