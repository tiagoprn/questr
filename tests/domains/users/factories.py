from datetime import datetime, timedelta, timezone
from uuid import uuid7

import factory
from factory.faker import Faker

from questr.common.enums import UserRole, UserStatus
from questr.infrastructure.orm.models import (
    EmailVerificationORMModel,
    SessionORMModel,
    UserORMModel,
)


class UserFactory(factory.Factory):
    class Meta:
        model = UserORMModel

    id = factory.LazyFunction(uuid7)
    username = Faker('user_name')
    email = Faker('email')
    first_name = Faker('first_name')
    last_name = Faker('last_name')
    # NOTE: do not remove the 2 comments below, they must stay because it
    # is non-obvious to a human.
    # password_hash uses a placeholder Argon2 hash string.
    # For tests that need real hashing, we'll use
    # the `hash_password()` utility.
    password_hash = factory.LazyFunction(
        lambda: '$argon2id$v=19$m=65536,t=3,p=4$mockhash'
    )
    role = UserRole.USER
    status = UserStatus.PENDING


class EmailVerificationFactory(factory.Factory):
    class Meta:
        model = EmailVerificationORMModel

    id = factory.LazyFunction(uuid7)
    user_id = factory.LazyFunction(uuid7)
    token_hash = Faker('sha256')
    expires_at = factory.LazyFunction(
        lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )
    used_at = None


class SessionFactory(factory.Factory):
    class Meta:
        model = SessionORMModel

    id = factory.LazyFunction(uuid7)
    user_id = factory.LazyFunction(uuid7)
    issued_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    last_activity = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    expires_at = factory.LazyFunction(
        lambda: datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    absolute_expires_at = factory.LazyFunction(
        lambda: datetime.now(timezone.utc) + timedelta(hours=8)
    )
    remember_me = False
    ip_address = factory.Faker('ipv4')
    user_agent = 'Mozilla/5.0 Test'
    csrf_token_hash = factory.Faker('sha256')
    is_active = True
