class QuestrException(Exception):
    """Base exception for questr application."""

    pass


class StructuredQuestrException(QuestrException):
    """Base exception carrying a machine-readable error_code.

    Args:
        error_code: Machine-readable identifier for the error type.
        message: Optional human-readable message (passed to Exception).
    """

    def __init__(self, error_code: str = '', message: str = '') -> None:
        self.error_code = error_code
        super().__init__(message)


class ResourceNotFoundError(QuestrException):
    """Raised when a requested resource is not found."""

    pass


class InvalidGameStateError(QuestrException):
    """Raised when a game state transition is invalid."""

    pass


class AuthenticationError(QuestrException):
    """Raised for authentication failures."""

    pass


class EmailNotVerifiedError(StructuredQuestrException):
    """Raised when user tries to login without email verification."""

    def __init__(self, message: str = '') -> None:
        super().__init__(error_code='email_not_verified', message=message)


class AccountSuspendedError(StructuredQuestrException):
    """Raised when account is suspended."""

    def __init__(self, message: str = '') -> None:
        super().__init__(error_code='account_suspended', message=message)


class AccountBannedError(StructuredQuestrException):
    """Raised when account is banned."""

    def __init__(self, message: str = '') -> None:
        super().__init__(error_code='account_banned', message=message)


class TooManyActiveSessionsError(StructuredQuestrException):
    """Raised when user exceeds the concurrent session limit."""

    def __init__(self, message: str = '') -> None:
        super().__init__(
            error_code='too_many_active_sessions', message=message
        )


class RateLimiterUnavailableError(StructuredQuestrException):
    """Raised when the rate limiter backend is unavailable."""

    def __init__(self, message: str = '') -> None:
        super().__init__(
            error_code='rate_limiter_unavailable', message=message
        )


class InvalidVerificationTokenError(QuestrException):
    """Raised for invalid/expired verification tokens."""

    pass


class UserAlreadyExistsError(QuestrException):
    """Raised when username or email already exists."""

    pass


class RateLimitExceededError(StructuredQuestrException):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = '') -> None:
        super().__init__(error_code='rate_limit_exceeded', message=message)
