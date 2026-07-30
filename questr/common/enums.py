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
