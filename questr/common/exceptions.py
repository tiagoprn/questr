class QuestrException(Exception):
    """Base exception for questr application."""

    pass


class ResourceNotFoundError(QuestrException):
    """Raised when a requested resource is not found."""

    pass


class InvalidGameStateError(QuestrException):
    """Raised when a game state transition is invalid."""

    pass
