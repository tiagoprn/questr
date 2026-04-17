from email_validator import EmailNotValidError, validate_email


class Email:
    """Email value object using email-validator for RFC validation."""

    def __init__(self, value: str) -> None:
        try:
            result = validate_email(value, check_deliverability=False)
            self._value = result.normalized
        except EmailNotValidError as exc:
            raise ValueError(f'Invalid email address: {value}') from exc

    @property
    def value(self) -> str:
        return self._value

    @property
    def domain(self) -> str:
        return self._value.split('@')[1]

    @property
    def local_part(self) -> str:
        return self._value.split('@')[0]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Email):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return f'Email({self._value!r})'

    def __str__(self) -> str:
        return self._value
