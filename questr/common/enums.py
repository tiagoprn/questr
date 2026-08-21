from enum import Enum


class UserRole(str, Enum):
    USER = 'user'
    SUPERUSER = 'superuser'


class UserStatus(str, Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    BANNED = 'banned'


class AuditAction(str, Enum):
    IMPERSONATION_START = 'impersonation_start'
    IMPERSONATION_END = 'impersonation_end'
    ROLE_GRANTED = 'role_granted'
    ROLE_REVOKED = 'role_revoked'
    PASSWORD_CHANGED = 'password_changed'
    PASSWORD_RESET = 'password_reset'
    EMAIL_CHANGE_REQUESTED = 'email_change_requested'
    EMAIL_CHANGED = 'email_changed'
    EMAIL_CHANGE_REVERTED = 'email_change_reverted'
