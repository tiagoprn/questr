from __future__ import annotations

from questr.common.exceptions import (
    AuthorizationError,
    StructuredQuestrException,
)
from questr.factory import create_app


class TestAuthorizationError:
    """AuthorizationError is a StructuredQuestrException with correct code."""

    def test_is_structured_exception(self) -> None:
        assert issubclass(AuthorizationError, StructuredQuestrException)

    def test_default_error_code(self) -> None:
        error = AuthorizationError()
        assert error.error_code == 'authorization'

    def test_custom_message(self) -> None:
        error = AuthorizationError(message='Access denied')
        assert error.error_code == 'authorization'
        assert str(error) == 'Access denied'

    def test_handler_registered_in_factory(self) -> None:
        """Verify factory.py registers the AuthorizationError handler."""
        app = create_app()
        handler = app.exception_handlers.get(AuthorizationError)
        assert handler is not None
