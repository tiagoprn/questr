# Software Architecture: Simple Feature-Oriented Clean Architecture

## Definition

This implements Clean Architecture with a Feature-First approach, combining Domain-Driven Design principles with a practical organization strategy.

Instead of traditional horizontal layers (controllers, services, repositories) that span across the entire application, the codebase is organized around feature modules (users, auth, games) that then have the layers defined inside each one of them.

So, it has clear domain, service, and repository layers inside each feature module. It keeps all code for a feature (HTTP, use cases, domain, persistence) co-located for fast iteration, while enforcing clear dependency rules so it can comfortably grow into richer DDD, Clean, or Hexagonal styles as the system evolves.

## When to Use

For a **project that will live a while and already has non-trivial rules**, this FastAPI structure is still quite fast because everything for a feature is co-located, and the pattern is standardized enough that adding the extra files isn't heavy.

## Characteristics

- **Feature-Oriented**: Each module represents a complete, independent feature rather than a technical layer
- **Encapsulation**: All necessary components (domain logic, repositories, services, API endpoints) reside within their respective feature modules, keeping related code together for better understanding
- **Modularity**: Features are designed with minimal dependencies between each other, ensuring changes to one feature have minimal impact on others
- **Contextual Clarity**: Developers can understand and modify a complete feature in one location without navigating across disparate technical layers
- **Scalability**: Easier to scale teams since developers can work on separate features without conflicts
- **Balanced Design**: The structure maintains clean architecture principles while prioritizing practical maintainability

This approach creates a codebase that is both well-structured and pragmatic, balancing architectural purity with development efficiency.

### Project Structure

```bash
questr/
├── __init__.py
├── common/                    # Shared utilities/code
│   ├── __init__.py
│   ├── exceptions.py          # Shared exception classes
│   ├── enums.py               # Shared enums (UserRole, UserStatus)
│   ├── rate_limiter.py        # Redis-based sliding window rate limiter
│   ├── redis.py               # Redis connection pool
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── game_rating.py
│   │   └── email.py           # Email value object using email-validator
│   └── services/
│       ├── __init__.py
│       └── email_service.py   # Pluggable email service (SMTP / Console)
├── games/                     # Game feature module
│   ├── __init__.py
│   ├── domain.py              # Game business logic
│   ├── repository.py          # Game data access
│   ├── service.py             # Game operations (holds the use cases)
│   ├── schemas.py             # Pydantic request/response models
│   ├── dependencies.py        # FastAPI Depends providers (dependency injection) for this feature
│   └── router.py              # Game API endpoints (APIRouter)
├── users/                     # User feature module
│   ├── __init__.py
│   ├── domain.py
│   ├── repository.py
│   ├── service.py
│   ├── schemas.py
│   ├── dependencies.py
│   └── router.py
├── orm/                       # Database configuration
│   ├── __init__.py
│   ├── base.py                # SQLAlchemy declarative base + async engine/session
│   └── models.py              # ORM models (thin, using Mapped[] style)
├── api/
│   ├── __init__.py
│   └── router.py              # Root APIRouter: includes all feature routers
├── migrations/                 # Alembic database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── lifespan.py                # FastAPI lifespan (startup/shutdown)
├── factory.py                 # App factory (create_app)
└── settings.py                # Configuration (Pydantic BaseSettings)
```

### Overview

| LAYER               | ROLE                                                                                  | CAN COMMUNICATE WITH         | MUST NOT COMMUNICATE WITH                              |
|---------------------|---------------------------------------------------------------------------------------|------------------------------|--------------------------------------------------------|
| Schemas             | Pydantic request/response validation and serialization                                | Pydantic                     | ORM models, Repositories, Domain, Services, Routers    |
| Router              | API endpoints via `APIRouter`                                                         | Services, Schemas, Depends   | Repositories, Domain, ORM models                       |
| Dependencies        | FastAPI `Depends` providers: inject sessions, services, current user                  | Services, ORM session        | Domain directly, Routes                                |
| Services            | Use cases (orchestrate domain & repositories)                                         | Repositories, Domain         | ORM models, Routers                                    |
| Domain (Core Logic) | Pure Python objects with business logic                                               | Nothing                      | ORM models, Repositories, Services, Routers            |
| Repositories        | Persistence (translation between ORM & pure domain objects, ORM read/write queries)   | ORM models, Domain           | Services, Routers                                      |
| ORM models          | Thin SQLAlchemy models                                                                | SQLAlchemy                   | Domain, Repositories, Services, Routers                |

### Key Concepts Explained

#### Value Objects

Value objects are small, simple types that represent single values in your domain. They have no identity — two value objects with the same data are considered equal. Their main purpose is to encapsulate validation and behavior related to that specific value.

Think of them as enhanced primitives: instead of passing around raw strings or integers, you pass objects that know how to validate themselves and can include related behavior.

**Example:** `Email` as a value object for user registration using the `email-validator` library for RFC-compliant validation.

```python
# common/value_objects/email.py
from email_validator import EmailNotValidError, validate_email


class Email:
    """Email value object using email-validator for RFC-compliant validation."""

    def __init__(self, value: str) -> None:
        try:
            result = validate_email(value, check_deliverability=False)
            self._value = result.normalized
        except EmailNotValidError as exc:
            raise ValueError(f"Invalid email address: {value}") from exc

    @property
    def value(self) -> str:
        return self._value

    @property
    def domain(self) -> str:
        return self._value.split("@")[1]

    @property
    def local_part(self) -> str:
        return self._value.split("@")[0]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Email):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)
```

**Why use value objects?**

- **Validation in one place**: Instead of validating emails in every service or router, the `Email` class handles it with RFC compliance via `email-validator`
- **Self-documenting code**: Functions that take `Email` instead of `str` are clearer
- **Built-in behavior**: Methods like `domain` and `local_part` live with the data they operate on

```python
# Using the value object
def register_user(email: Email, name: str) -> User:
    # Email is already validated — no need for extra checks
    ...
```

#### Email Service

A pluggable email service in `common/services/` (not inside a feature module) so future features can send emails without cross-domain dependencies. Three implementations exist:

- `BaseEmailService` — abstract base defining the interface
- `SmtpEmailService` — production implementation using `aiosmtplib`
- `ConsoleEmailService` — development-only implementation that logs instead of sending

```python
# common/services/email_service.py
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseEmailService(ABC):
    @abstractmethod
    async def send_verification_email(
        self, to_email: str, token: str
    ) -> bool:
        """Send verification email. Returns True on success."""
        ...


class SmtpEmailService(BaseEmailService):
    """Email service using SMTP (e.g., Mailpit for local dev)."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email

    async def send_verification_email(
        self, to_email: str, token: str
    ) -> bool:
        import aiosmtplib
        from email.message import EmailMessage

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = "Verify your Questr account"
        message.set_content(
            f"Click the following link to verify your email: POST /api/v1/auth/verify-email with body: {{'token': '{token}'}}"
        )

        try:
            await aiosmtplib.send(
                message,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=True,
            )
            return True
        except Exception:
            logger.exception("Failed to send verification email to %s", to_email)
            return False


class ConsoleEmailService(BaseEmailService):
    """Development-only email service that logs instead of sending."""

    async def send_verification_email(
        self, to_email: str, token: str
    ) -> bool:
        logger.info(
            "[DEV] Would send verification email to %s with token: %s",
            to_email,
            token,
        )
        return True


def get_email_service() -> BaseEmailService:
    """Factory function to get the configured email service."""
    from questr.settings import settings

    if settings.EMAIL_ENABLED:
        return SmtpEmailService(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            from_email=settings.EMAIL_FROM,
        )
    return ConsoleEmailService()
```

#### Rate Limiting

Redis-based sliding window rate limiter using sorted sets for atomic, TTL-based counting. Used for endpoints that need throttling (e.g., resend-verification).

```python
# common/rate_limiter.py
import time
from redis.asyncio import Redis


class RedisRateLimiter:
    """Rate limiter using Redis sorted sets with sliding window."""

    def __init__(
        self, redis: Redis, max_requests: int = 3, window_seconds: int = 3600
    ) -> None:
        self.redis = redis
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed using a sliding window counter."""
        now = time.time()
        window_start = now - self.window_seconds
        redis_key = f"rate_limit:{key}"

        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.zremrangebyscore(redis_key, 0, window_start)
            await pipe.zadd(redis_key, {str(now): now})
            await pipe.expire(redis_key, self.window_seconds)
            await pipe.zcard(redis_key)
            results = await pipe.execute()

        request_count = results[-1]
        return request_count <= self.max_requests
```

#### Domain

Domain objects encapsulate core business logic, rules, and behaviors central to the application. They represent the "what" of the system. Domain objects are pure Python — they have zero knowledge of FastAPI, SQLAlchemy, or Pydantic.

**Example:** `User` and `EmailVerification` domain objects.

```python
# users/domain.py
from dataclasses import dataclass
from uuid import UUID
from questr.common.enums import UserRole, UserStatus


@dataclass
class User:
    """User domain object."""
    id: UUID | None = None
    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    password_hash: str = ""
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING


@dataclass
class EmailVerification:
    """Email verification domain object."""
    id: UUID | None = None
    user_id: UUID | None = None
    token_hash: str = ""
    expires_at: datetime | None = None
    used_at: datetime | None = None
```

#### Repository

Repositories abstract data access logic and provide methods to retrieve and persist domain objects. In FastAPI, repositories receive an async SQLAlchemy `AsyncSession` injected via `Depends`.

**Example:** `UserRepository` handling user ORM and retrieval.

```python
# users/repository.py
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from questr.orm.models import UserORMModel
from questr.users.domain import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user: User) -> User:
        orm_user = UserORMModel(
            id=user.id,
            username=user.username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            password_hash=user.password_hash,
            role=user.role,
            status=user.status,
        )
        self.session.add(orm_user)
        await self.session.flush()
        return self._to_domain(orm_user)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(UserORMModel).where(UserORMModel.username == username)
        )
        orm_user = result.scalar_one_or_none()
        return self._to_domain(orm_user) if orm_user else None

    @staticmethod
    def _to_domain(orm_user: UserORMModel) -> User:
        return User(
            id=orm_user.id,
            username=orm_user.username,
            email=orm_user.email,
            first_name=orm_user.first_name,
            last_name=orm_user.last_name,
            password_hash=orm_user.password_hash,
            role=orm_user.role,
            status=orm_user.status,
        )
```

#### Service

Services coordinate complex operations involving multiple domain objects or repositories. They implement application use cases and orchestrate business processes. In FastAPI, services are typically instantiated via `Depends` in a feature's `dependencies.py` — they are not singletons.

**Example:** `AuthService` handling signup, verify-email, and resend-verification use cases.

```python
# users/service.py
from questr.common.exceptions import UserAlreadyExistsError
from questr.common.rate_limiter import RedisRateLimiter
from questr.common.services.email_service import BaseEmailService
from questr.users.domain import (
    User,
    generate_verification_token,
    normalize_username,
    validate_password,
)
from questr.users.repository import (
    EmailVerificationRepository,
    UserRepository,
)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        verification_repo: EmailVerificationRepository,
        email_service: BaseEmailService,
        rate_limiter: RedisRateLimiter,
    ) -> None:
        self.user_repo = user_repo
        self.verification_repo = verification_repo
        self.email_service = email_service
        self.rate_limiter = rate_limiter

    async def signup(
        self,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        password: str,
        password_confirmation: str,
        client_ip: str,
    ) -> User:
        if password != password_confirmation:
            raise ValueError("Passwords do not match")

        result = validate_password(password)
        if not result.is_valid:
            raise ValueError("; ".join(result.errors))

        normalized_username = normalize_username(username)

        existing = await self.user_repo.get_by_username(normalized_username)
        if existing:
            raise UserAlreadyExistsError("Username already exists")
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise UserAlreadyExistsError("Email already exists")

        user = User(
            id=uuid7(),
            username=normalized_username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=hash_password(password),
            role=UserRole.USER,
            status=UserStatus.PENDING,
        )
        return await self.user_repo.create(user)
```

#### Dependencies

`dependencies.py` is a FastAPI-specific file inside each feature module. It contains `Depends` provider functions that wire up repositories, services, rate limiters, and the email service to the async DB session.

**Example:** User dependencies.

```python
# users/dependencies.py
from typing import Annotated
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from questr.orm.base import get_async_session
from questr.settings import settings
from questr.users.repository import (
    EmailVerificationRepository,
    UserRepository,
)
from questr.users.service import AuthService


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRepository:
    return UserRepository(session)


async def get_verification_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EmailVerificationRepository:
    return EmailVerificationRepository(session)


async def get_rate_limiter() -> RedisRateLimiter:
    from questr.common.redis import get_redis
    redis = get_redis()
    return RedisRateLimiter(
        redis=redis,
        max_requests=settings.RATE_LIMIT_RESEND_MAX,
        window_seconds=settings.RATE_LIMIT_RESEND_WINDOW_HOURS * 3600,
    )


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_auth_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    verification_repo: Annotated[
        EmailVerificationRepository, Depends(get_verification_repository)
    ],
    email_service: Annotated[
        BaseEmailService, Depends(get_email_service)
    ],
    rate_limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        verification_repo=verification_repo,
        email_service=email_service,
        rate_limiter=rate_limiter,
    )


T_AuthService = Annotated[AuthService, Depends(get_auth_service)]
T_ClientIP = Annotated[str, Depends(get_client_ip)]
```

#### Schemas

Schemas are **Pydantic `BaseModel`** subclasses — FastAPI uses them natively for request body validation and response serialization.

**Example:** Auth request/response Pydantic models.

```python
# users/schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from questr.common.enums import UserRole, UserStatus


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    password: str
    password_confirmation: str


class SignupResponse(BaseModel):
    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    status: UserStatus

    model_config = {"from_attributes": True}
```

#### Router

`router.py` files are the HTTP entry points of each feature module. They define the API endpoints using FastAPI's `APIRouter`, keeping route declarations co-located with the rest of the feature's code.

Each handler is declared as `async def`, so it participates naturally in FastAPI's async request lifecycle without blocking the event loop. Request bodies are typed as Pydantic schema parameters — FastAPI validates incoming JSON against them automatically and returns clean error responses when validation fails. Outgoing data is controlled by the `response_model` parameter on the route decorator, which both serializes the response and drives the auto-generated OpenAPI documentation.

**Example:** Auth API endpoints.

```python
# users/router.py
from fastapi import APIRouter, status

from questr.common.exceptions import (
    InvalidVerificationTokenError,
    RateLimitExceededError,
    UserAlreadyExistsError,
)
from questr.users.dependencies import T_AuthService, T_ClientIP
from questr.users.schemas import (
    ResendVerificationRequest,
    ResendVerificationResponse,
    SignupRequest,
    SignupResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": PasswordValidationError},
        409: {"description": "Username or email already exists"},
    },
)
async def signup(
    payload: SignupRequest,
    service: T_AuthService,
    client_ip: T_ClientIP,
) -> SignupResponse:
    user = await service.signup(
        username=payload.username,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password=payload.password,
        password_confirmation=payload.password_confirmation,
        client_ip=client_ip,
    )
    return SignupResponse.model_validate(user)


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    responses={400: {"description": "Invalid or expired token"}},
)
async def verify_email(
    payload: VerifyEmailRequest,
    service: T_AuthService,
) -> VerifyEmailResponse:
    user = await service.verify_email(payload.token)
    return VerifyEmailResponse.model_validate(user)


@router.post(
    "/resend-verification",
    response_model=ResendVerificationResponse,
    responses={429: {"description": "Rate limit exceeded"}},
)
async def resend_verification(
    payload: ResendVerificationRequest,
    service: T_AuthService,
    client_ip: T_ClientIP,
) -> ResendVerificationResponse:
    await service.resend_verification(email=payload.email, client_ip=client_ip)
    return ResendVerificationResponse(
        message="If an account with this email exists, "
        "a new verification email has been sent."
    )
```

#### Persistence

The ORM layer uses **SQLAlchemy with `DeclarativeBase`** (SQLAlchemy 2.x style) and modern `Mapped[]` style column definitions. The async engine and session factory live in `orm/base.py`, providing the `get_async_session` dependency used across all repositories. UUIDv7 values are used for primary keys (provided by Python 3.14's `uuid` module as `uuid7()`).

**Example:** Thin ORM models using `Mapped[]` style.

```python
# orm/models.py
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import UUID as SAUUID

from questr.common.enums import UserRole, UserStatus
from questr.orm.base import Base


class UserORMModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(SAUUID, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(1024), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.USER, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), default=UserStatus.PENDING, nullable=False
    )


class EmailVerificationORMModel(Base):
    __tablename__ = "email_verifications"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[UUID] = mapped_column(SAUUID, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        SAUUID, ForeignKey("users.id"), unique=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

#### Exception Handling

Domain exceptions are mapped to HTTP status codes via exception handlers registered in `factory.py`. Each exception class lives in `common/exceptions.py`.

**Example:** Domain exceptions and their HTTP mappings.

```python
# common/exceptions.py
class QuestrException(Exception):
    """Base exception for all questr domain exceptions."""
    pass


class UserAlreadyExistsError(QuestrException):
    """Raised when username or email already exists."""
    pass


class InvalidVerificationTokenError(QuestrException):
    """Raised for invalid/expired verification tokens."""
    pass


class RateLimitExceededError(QuestrException):
    """Raised when rate limit is exceeded."""
    pass
```

```python
# factory.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from questr.common.exceptions import (
    InvalidVerificationTokenError,
    RateLimitExceededError,
    UserAlreadyExistsError,
)


def create_app() -> FastAPI:
    app = FastAPI(title="questr", lifespan=lifespan)

    app.add_exception_handler(
        UserAlreadyExistsError,
        lambda request, exc: JSONResponse(
            status_code=409, content={"detail": str(exc)}
        ),
    )
    app.add_exception_handler(
        InvalidVerificationTokenError,
        lambda request, exc: JSONResponse(
            status_code=400, content={"detail": str(exc)}
        ),
    )
    app.add_exception_handler(
        RateLimitExceededError,
        lambda request, exc: JSONResponse(
            status_code=429, content={"detail": str(exc)}
        ),
    )

    app.include_router(api_router)
    return app
```

#### API Router Registration

`api/router.py` aggregates all feature routers into a single root `APIRouter` which is then included in the app factory.

**Example:** Root router setup.

```python
# api/router.py
from fastapi import APIRouter

from questr.users.router import router as users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(users_router)
```

#### App Factory & Lifespan

The app factory pattern maps directly to FastAPI. Startup and shutdown resources (database engine and Redis connection pool) are managed through the `lifespan` async context manager.

**Example:** Lifespan and app factory.

```python
# lifespan.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from questr.common.redis import close_redis
from questr.orm.base import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()
    await close_redis()
```

```python
# factory.py
from fastapi import FastAPI

from questr.api.router import api_router
from questr.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="questr", version="0.1.0", lifespan=lifespan)
    app.include_router(api_router)
    return app
```

#### Settings

Replace plain module-level constants with **Pydantic `BaseSettings`** for environment-aware configuration with automatic `.env` file loading.

```python
# settings.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "questr"
    DEBUG: bool = False
    DATABASE_URL: str = (
        "postgresql+psycopg://app_user:app_password"
        "@questr_database:5432/app_db"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Email settings
    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@questr.app"

    # Rate limiting
    RATE_LIMIT_RESEND_MAX: int = 3
    RATE_LIMIT_RESEND_WINDOW_HOURS: int = 1

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

#### Database Migrations

Database schema changes are managed with **Alembic**. Migrations are stored in `migrations/`. Initialize Alembic with `alembic init migrations`, configure `migrations/env.py` to import `Base` from `questr.orm.base`, and use async support.

**Makefile commands:**

```makefile
db-create-migration:  ## Create a new migration. Usage: make db-create-migration MSG="description"
	@alembic revision --autogenerate -m "$(MSG)"

db-upgrade:  ## Apply all pending migrations
	@alembic upgrade head

db-downgrade:  ## Rollback last migration
	@alembic downgrade -1
```

## Future Improvements

### When to Add Celery

The current architecture uses FastAPI's built-in `BackgroundTasks`, which is sufficient for most I/O-bound operations (API calls, sending emails, light data processing). As the application scales, we may need to add Celery when:

- **Distributed processing**: tasks need to run across multiple worker processes or servers
- **Complex retry policies**: we need exponential backoff, dead letter queues, or task chaining
- **Scheduled tasks at scale**: we need reliable periodic tasks that persist across application restarts
- **Rate limiting**: we need to throttle task execution rates
- **Task result storage**: we need to store and retrieve task results programmatically

When the time comes to add Celery, the feature-first organization will make it straightforward to introduce a `workers/` module without disrupting existing code.
