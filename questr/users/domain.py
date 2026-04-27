from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from questr.common.enums import UserRole, UserStatus


@dataclass
class User:
    """User domain object."""

    id: UUID | None = None
    username: str = ''
    email: str = ''
    first_name: str = ''
    last_name: str = ''
    password_hash: str = ''
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING


@dataclass
class EmailVerification:
    """Email verification domain object."""

    id: UUID | None = None
    user_id: UUID | None = None
    token_hash: str = ''
    expires_at: datetime | None = None
    used_at: datetime | None = None


def normalize_username(username: str) -> str:
    username = username.strip()
    username = username.lower()
    username = (
        unicodedata.normalize('NFKD', username)
        .encode('ascii', 'ignore')
        .decode('ascii')
    )
    username = re.sub(r'[^a-z0-9_-]', '', username)
    return username


def generate_verification_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def get_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)


@dataclass
class PasswordValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


def validate_password(password: str) -> PasswordValidationResult:
    errors: list[str] = []

    if len(password) < 8:  # noqa: PLR2004
        errors.append('Password must be at least 8 characters')
    if not re.search(r'[A-Z]', password):
        errors.append(
            'Password must contain at least 1 uppercase letter'
        )
    if not re.search(r'[a-z]', password):
        errors.append(
            'Password must contain at least 1 lowercase letter'
        )
    if not re.search(r'\d', password):
        errors.append('Password must contain at least 1 number')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append(
            'Password must contain at least 1 special character '
            '(!@#$%^&*(),.?":{}|<>)'
        )

    return PasswordValidationResult(
        is_valid=len(errors) == 0, errors=errors
    )
