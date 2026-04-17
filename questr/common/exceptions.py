class QuestrException(Exception):
    """Base exception for questr application."""

    pass


class ResourceNotFoundError(QuestrException):
    """Raised when a requested resource is not found."""

    pass


class InvalidGameStateError(QuestrException):
    """Raised when a game state transition is invalid."""

    pass


class AuthenticationError(QuestrException):
    """Raised for authentication failures."""

    pass


class EmailNotVerifiedError(QuestrException):
    """Raised when user tries to login without email verification."""

    pass


class AccountSuspendedError(QuestrException):
    """Raised when account is suspended or banned."""

    pass


class InvalidVerificationTokenError(QuestrException):
    """Raised for invalid/expired verification tokens."""

    pass


class UserAlreadyExistsError(QuestrException):
    """Raised when username or email already exists."""

    pass


class RateLimitExceededError(QuestrException):
    """Raised when rate limit is exceeded."""

    pass
