from enum import Enum


class UserRole(str, Enum):
    USER = 'user'
    SUPERUSER = 'superuser'


class UserStatus(str, Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    BANNED = 'banned'
