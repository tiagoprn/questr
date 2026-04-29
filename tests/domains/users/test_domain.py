# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
import hashlib

# noqa: PLR6301,PLR2004
from questr.domains.users.service import (
    generate_verification_token,
    normalize_username,
    validate_password,
)


class TestNormalizeUsername:
    def test_trims_whitespace(self) -> None:
        assert normalize_username('  john  ') == 'john'

    def test_lowercases(self) -> None:
        assert normalize_username('JohnDoe') == 'johndoe'

    def test_converts_unicode_to_ascii(self) -> None:
        assert normalize_username('joão') == 'joao'

    def test_removes_special_chars(self) -> None:
        assert normalize_username('john.doe!@#') == 'johndoe'

    def test_preserves_allowed_chars(self) -> None:
        assert normalize_username('john_doe-123') == 'john_doe-123'


class TestValidatePassword:
    def test_valid_password(self) -> None:
        result = validate_password('StrongPass1!')
        assert result.is_valid is True
        assert result.errors == []

    def test_too_short(self) -> None:
        result = validate_password('Short1!')
        assert result.is_valid is False
        assert 'Password must be at least 8 characters' in result.errors

    def test_missing_uppercase(self) -> None:
        result = validate_password('weakpass1!')
        assert result.is_valid is False
        assert (
            'Password must contain at least 1 uppercase letter'
            in result.errors
        )

    def test_missing_lowercase(self) -> None:
        result = validate_password('WEAKPASS1!')
        assert result.is_valid is False
        assert (
            'Password must contain at least 1 lowercase letter'
            in result.errors
        )

    def test_missing_number(self) -> None:
        result = validate_password('WeakPass!!')
        assert result.is_valid is False
        assert 'Password must contain at least 1 number' in result.errors

    def test_missing_special_char(self) -> None:
        result = validate_password('WeakPass11')
        assert result.is_valid is False
        assert any('special character' in e for e in result.errors)

    def test_returns_all_errors_at_once(self) -> None:
        result = validate_password('weak')
        assert result.is_valid is False
        assert len(result.errors) > 1


class TestGenerateVerificationToken:
    def test_returns_tuple(self) -> None:
        result = generate_verification_token()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_raw_token_length(self) -> None:
        raw_token, token_hash = generate_verification_token()
        assert len(raw_token) > 20
        assert len(token_hash) == 64

    def test_token_hash_is_sha256(self) -> None:
        raw_token, token_hash = generate_verification_token()
        expected = hashlib.sha256(raw_token.encode()).hexdigest()
        assert token_hash == expected
