# Pragmatic Clean Architecture

> *This architecture draws from Clean Architecture's enduring principles (isolated business logic, encapsulation, explicit domain boundaries) while rejecting its ritualistic ceremony. The result is a codebase that is easy to navigate: fewer files, explicit contracts, and no abstraction without justification.*

---

## Table of Contents

1. [Strategic Domain Boundaries](#1-strategic-domain-boundaries)
2. [Three-File Structure](#2-three-file-structure)
3. [Project Structure](#3-project-structure)
4. [Cross-Domain Communication](#4-cross-domain-communication)
5. [Abstraction Decision Gate](#5-abstraction-decision-gate)
6. [Testing Philosophy](#6-testing-philosophy)
7. [Boundaries Without Ceremony](#7-boundaries-without-ceremony)
8. [Quick Reference & Anti-Patterns](#8-quick-reference--anti-patterns)
9. [Persistence](#9-persistence)
10. [Dependencies / DI](#10-dependencies--di)
11. [Multi-Layer DTOs](#11-multi-layer-dtos)
12. [App Factory & Lifespan](#12-app-factory--lifespan)
13. [Settings](#13-settings)
14. [Database Migrations](#14-database-migrations)
15. [Lint Rules](#15-lint-rules)

---

## 1. Strategic Domain Boundaries

Before writing a single line of logic, identify the major business domains. Each domain becomes a folder under `questr/domains/`.

**Current domains:**

| Domain | Responsibility |
|---|---|
| `users` | Authentication, user management, email verification, session lifecycle (login, sessions, logout) |
| `hello` | Sample domain / health check |

**Rule:** No cross-domain imports between domain modules. A file inside `questr/domains/users/` must not import from `questr/domains/hello/` or any other domain. This is enforced by lint rule **QTR002** (see [Lint Rules](#15-lint-rules)).

**Exception:** `api.py` files (the HTTP adapter layer) may import from `orchestrators/` — see [Cross-Domain Communication](#4-cross-domain-communication).

---

## 2. Three-File Structure

Inside each domain, start with exactly three files:

```
domains/users/
    api.py        # HTTP handlers, Pydantic schemas, FastAPI DI wiring
    service.py    # Domain functions + business logic + use cases
    repository.py # Domain dataclasses + persistence (ORM queries, _to_domain mapping)
```

Domains without persistence (e.g., the stateless `hello` sample) need only
`api.py` and `service.py` -- `repository.py` is omitted because there is no
ORM model and no `_to_domain()` mapping to host. The three-file structure is a
ceiling, not a floor: a domain starts with the files it needs and grows toward
three, never past it without justification.

### Responsibilities

| File | Contains | Is allowed to import |
|---|---|---|
| `api.py` | `APIRouter` routes, Pydantic request/response models, `Depends()` providers, type aliases (`T_AccountService`, `T_SessionService`) | `service.py`, `repository.py`, `infrastructure/`, `app/dependencies.py`, `common/`, `settings` |
| `service.py` | Pure domain functions, business logic, service/use case classes | `repository.py`, `common/`, `infrastructure/`, `settings` |
| `repository.py` | Domain dataclasses, repository classes with `_to_domain()` mappers | `infrastructure/orm/`, `common/` |

### Why Domain Dataclasses Live in `repository.py`

Domain dataclasses (`User`, `EmailVerification`) are defined in `repository.py` rather than `service.py` for two reasons:

1. **Co-location with mapping logic.** The `_to_domain()` method that converts ORM models to domain objects lives in the same file as the domain dataclass it produces. The dataclass and its mapper change together — separating them would couple two files that are logically one unit.

2. **The persistence boundary defines the contract.** The repository is where infrastructure (`infrastructure/orm/models.py`) meets domain code. Defining the domain dataclass at this boundary makes the mapping contract explicit: `service.py` imports `User` from `repository.py`, not from `infrastructure/orm/models.py`, which would violate QTR001.

`service.py` imports domain dataclasses from `repository.py`, which is allowed by the dependency direction below. This keeps the three-file structure intact without adding a fourth file.

**Scope of this rule:** it covers only **persistence-bound domain entities** --
those backed by an ORM model and mapped via `_to_domain()` (e.g., `User`,
`Session`, `EmailVerification`). Use-case **result value objects** that have no
ORM counterpart and no persistence mapping (e.g., `PasswordValidationResult`)
belong with the use-case logic that produces them, in `service.py`. The
distinguishing test is the presence of a `_to_domain()` mapper: if a dataclass
has one, it lives in `repository.py`; if not, it stays in `service.py`.

### Dependency Direction

```
api.py  →  service.py  →  repository.py
```

Never backward. `repository.py` imports nothing from `api.py` or `service.py`. This keeps the dependency acyclic and explicit.

### Strong Types at Module Contracts

Use type aliases to make module boundaries self-documenting:

```python
# app/dependencies.py
from typing import Annotated
from fastapi import Depends
T_ClientIP = Annotated[str, Depends(get_client_ip)]
```

Domain primitives are defined as dataclasses in `repository.py` (the persistence boundary) and re-exported as needed.

---

## 3. Project Structure

```
questr/
  app/               # Cross-cutting wiring (middleware, DI, dependencies)
    middleware.py     # CsrfMiddleware — automatic CSRF enforcement
    dependencies.py   # FastAPI Depends functions, type alias definitions
  domains/
    users/
      api.py         # HTTP routes + Pydantic schemas + Depends wiring
      service.py     # AccountService (signup, verify, resend) + SessionService (login, validate, logout)
      repository.py  # User + EmailVerification + Session dataclasses + repos
    hello/
      api.py         # Hello endpoint + response schema
      service.py     # get_greeting() (time-of-day greeting)
  orchestrators/     # Cross-domain coordination (top-level, not inside domains/)
  infrastructure/
    orm/
      base.py        # SQLAlchemy declarative base + async engine/session
      models.py      # ORM models (thin, using Mapped[] style)
    email.py         # BaseEmailService, SmtpEmailService, ConsoleEmailService, factory
    rate_limiter.py  # RedisRateLimiter + get_rate_limiter() factory
    login_rate_limiter.py  # LoginRateLimiter + get_login_rate_limiter() factory
    redis.py         # Redis connection pool
  common/            # Shared domain-agnostic types
    enums.py         # UserRole, UserStatus
    exceptions.py    # QuestrException hierarchy
  api/
    router.py        # Root APIRouter: includes all domain routers
  factory.py         # App factory (create_app)
  lifespan.py        # FastAPI lifespan (startup/shutdown)
  settings.py        # Configuration (Pydantic BaseSettings)
  __init__.py        # Package marker (empty)
  __main__.py        # Entry point for `python -m questr` (delegates to shell.main)
  shell.py           # Interactive query shell (QTR001 tooling exception)

migrations/          # Alembic database migrations (repo root; see alembic.ini)

tests/
  behavior/
    conftest.py      # Shared fixtures (FastAPI app + HTTP client)
    test_signup.py   # Happy-path signup test through HTTP boundary
    test_hello.py    # Parametrized hello endpoint test
  domains/
    users/
      test_domain.py       # Pure unit tests for domain functions
      test_service.py      # Mock-based service behavior tests
      test_repository.py   # Real-DB integration tests
      test_router.py       # Full HTTP integration tests
    hello/
      test_router.py       # Hello endpoint tests
```

---

### The `app/` Layer: Cross-Cutting Wiring

The `app/` package (at `questr/app/`) is not a domain — it exists for cross-cutting
concerns that span multiple domains or layer the request lifecycle:

- `middleware.py` — `CsrfMiddleware` (``BaseHTTPMiddleware``) enforces the CSRF
double-submit + synchronizer token contract on state-changing requests,
returning direct ``JSONResponse`` 403s (since Starlette middleware raises
cannot be caught by ``app.add_exception_handler``).
- `dependencies.py` — shared FastDI type aliases and `Depends()` providers.

**Import rule (TD-007):** The ``app/`` package exchanges with domains in two
directions, governed separately:

- **(a) ``app/`` -> domains (reversal, justified):** ``app/`` MAY import from
domain repositories. This reverses the usual domain dependency direction; it is
justified because ``app/middleware.py`` needs session data without pulling
``SessionService`` into a cross-cutting concern. It violates neither QTR001 (no
ORM import) nor QTR002 (not a cross-domain import).
- **(b) domains -> ``app/`` (restricted):** Domain ``service.py`` and
``repository.py`` MUST NOT import from ``app/``. Domain ``api.py`` -- the HTTP
adapter, not business logic -- is permitted to import *only*
``app/dependencies.py`` for shared type aliases and ``Depends()`` providers; it
MUST NOT import ``app/middleware.py``. This carve-out mirrors the QTR002
``api.py``/orchestrator exception: the HTTP adapter is the seam where cross-cutting
wiring is allowed to enter a domain, while domain logic stays insulated.

### Rate Limiters

The project has two distinct rate limiter classes, each serving a different purpose:

| Class | File | Purpose | Fail-closed |
|---|---|---|---|
| ``RedisRateLimiter`` | ``infrastructure/rate_limiter.py`` | Resend-verification throttling (existing) | Accidentally (uncaught Redis errors → 500) |
| ``LoginRateLimiter`` | ``infrastructure/login_rate_limiter.py`` | Per-account lockout + per-IP throttle for login | Deliberately (``RateLimiterUnavailableError`` → 503) |

The ``LoginRateLimiter`` is a dedicated class because login requires:
(1) two independent counters with different windows (per-account 15 min, per-IP
10 min), (2) a per-account lockout state machine (5 failures → 30 min lockout),
(3) reset-on-success, (4) deliberate fail-closed posture. Bolting these onto
``RedisRateLimiter`` would complicate its interface for all callers.

## 4. Cross-Domain Communication

### Default Pattern: Orchestrator

When a feature requires coordination between two or more domains, create an **orchestrator** in `questr/orchestrators/`.

```
questr/orchestrators/
    __init__.py
```

**Why orchestrators are top-level (not inside any domain):**

1. **Orchestrators own no business logic** — only sequencing. Putting them inside `domains/` implies they are a business concept, which they are not.
2. **Every domain module in `domains/` follows the no-cross-import rule.** Orchestrators would be the only exception, creating ambiguity: *"is this a domain or isn't it?"*
3. **The top-level `orchestrators/` makes the cross-domain nature visually obvious** in every file path.

### Call Chain

```
api.py  →  orchestrator  →  service.py (domain A) + service.py (domain B)
```

The `api.py` can import from `orchestrators/` because `api.py` is an HTTP adapter, not domain logic. The orchestrator imports from multiple domain `service.py` files.

### Decision Gate

| Pattern | When to use | Example |
|---|---|---|
| **Orchestrator** (default) | One operation coordinates N domains | "Sign up user → create billing account → send welcome email" |
| **Domain Events** | Multiple consumers of a domain fact exist | "User verified → send email + update analytics + trigger campaign" |
| **Port at Domain Boundary** | External contract pollution is real | "Stripe integration requires `Charge` objects that must not leak into domain" |

> **Forward-looking note:** Future domains may evolve into domain events or boundary ports. When that need arises, apply the [Abstraction Decision Gate](#5-abstraction-decision-gate) below.

---

## 5. Abstraction Decision Gate

Before introducing any abstraction (interface, use case class, DTO, adapter, or shared module), answer these three questions:

| Question | If yes | If no |
|---|---|---|
| Have you swapped this dependency in the past 2 years? | Interface justified | Encapsulation sufficient |
| Is this logic needed in a second confirmed, existing place? | Extract to shared module | Do not extract |
| Will this third-party contract pollute your domain? | ACL justified | Encapsulation sufficient |

### What is an ACL (Anti-Corruption Layer)?

An Anti-Corruption Layer is a thin adapter that sits between your domain and an external system (third-party API, legacy database, external service). Its job is to translate the external system's model into your domain's model, preventing the external system's concepts, data structures, and quirks from bleeding into your domain logic.

**Example:** Integrating with Stripe for payments — the ACL translates Stripe's `Charge` object into your domain's `Payment` object. If you later switch to Adyen, only the ACL changes; your domain never knew about Stripe's model.

### Applied Example: Email Service

The `BaseEmailService` abstraction is **justified** because:

- **Question 3 answered yes:** SMTP libraries (`aiosmtplib`) would pollute the domain with transport concepts (`start_tls`, `authentication`). The ACL (`BaseEmailService`) keeps the domain clean.
- **Question 2 answered no (but still justified):** Only one consumer (`AccountService`) needs email sending today, but question 3 overrides — the external contract pollution risk is real.

> **Rule:** No interface, use case class, DTO, or adapter shall be introduced without answering these three questions first.

---

## 6. Testing Philosophy

### Minimum Requirement

Behavior tests in `tests/behavior/` are the **minimum testing requirement**. Every feature must have at least one behavior test covering its primary happy path through the HTTP boundary.

### Test Structure

```
tests/
  behavior/
    conftest.py      # Shared fixtures (FastAPI app, HTTP client, test DB)
    test_signup.py   # "A user can sign up" — happy path + duplicate error
    test_hello.py    # "Hello endpoint returns correct greeting"
  domains/
    users/           # Per-domain unit + integration tests
      test_domain.py       # Pure unit tests for domain functions
      test_service.py      # Mock-based service behavior tests
      test_repository.py   # Real-DB integration tests
      test_router.py       # Full HTTP integration tests
    hello/
      test_router.py
```

### Guidelines

- **Tests assert behavior (outcomes), not implementation (internal calls).** A test that asserts *what* a module does is durable. A test that asserts *which internal classes were called* is brittle.
- Behavior test files have 1–3 parametrized test cases covering the happy path and the most critical error path. Exhaustive edge-case coverage stays in per-domain test directories.
- Mocking concrete classes is standard practice; interfaces are not required for testability.
- Behavior tests serve as:
  - **Living documentation** of what the system does
  - **Smoke tests** that catch regressions in core workflows
  - **Stable contracts** that survive refactoring

---

## 7. Boundaries Without Ceremony

This architecture uses four coherence mechanisms to replace the ceremony of a full layered architecture:

### 1. Folder-per-domain with no-cross-import lint rules

Each domain lives in its own folder under `domains/`. Lint rule **QTR002** (see [Lint Rules](#15-lint-rules)) prevents cross-domain imports mechanically.

### 2. Strong types at module contracts

Type aliases (`T_ClientIP`), domain dataclasses (`User`, `Email`), and strict import boundaries make contracts explicit without interfaces. The type system documents what crosses each boundary.

### 3. Behavior-level tests

Every feature has at least one behavior test that exercises the full HTTP stack. These tests are the regression insurance that makes complicated layered abstractions unnecessary.

### 4. Lint rules preventing ORM access outside repository files

Lint rule **QTR001** (see [Lint Rules](#15-lint-rules)) prevents `infrastructure.orm.models` from being imported anywhere except `repository.py` files. This enforces the persistence encapsulation boundary mechanically.

### Contrast: Canonical Clean Architecture vs. This Approach

For a simple auth feature (signup, verify email, resend verification), a canonical Clean Architecture setup would produce files spread across horizontal layers:

```
interfaces/controllers/auth_controller.py
interfaces/presenters/user_presenter.py
interfaces/serializers/user_serializer.py
application/use_cases/signup_use_case.py
application/use_cases/verify_email_use_case.py
application/use_cases/resend_verification_use_case.py
application/repositories/user_repository_interface.py
application/repositories/email_verification_repository_interface.py
application/services/email_service_interface.py
domain/entities/user.py
domain/entities/email_verification.py
domain/services/password_validation_service.py
domain/services/username_normalization_service.py
domain/value_objects/email.py
infrastructure/persistence/user_orm.py
infrastructure/persistence/email_verification_orm.py
infrastructure/email/smtp_email_service.py
infrastructure/email/console_email_service.py
```

**18 files** — each layer, each interface, each use case gets its own file.

Now the equivalent using this architecture:

```
# Domain (3 files — merged by concern, not by layer)
domains/users/api.py           # Merges: auth_controller + user_presenter +
                               #         user_serializer + DI wiring
domains/users/service.py       # Merges: signup + verify + resend use cases +
                               #         password_validation + username_normalization
domains/users/repository.py    # Merges: user + email_verification domain types +
                               #         user_repository + email_verification_repository
                               #         (no interfaces — concrete class is sufficient)

# Infrastructure (2 files — merged by concern)
infrastructure/orm/models.py   # Merges: user_orm + email_verification_orm
infrastructure/email.py        # Merges: email_service_interface + smtp + console impls

```

**5 files instead of 18.** The savings come from:

- **No interface files** for repositories (concrete classes are mockable in Python — no interface needed)
- **No per-use-case files** (group related use cases in one `service.py`)
- **No per-entity files** (domain dataclasses live alongside the service logic that operates on them)
- **No per-layer separation** (HTTP, schemas, and DI wiring are all part of the API boundary — they belong in `api.py`)
- **No per-implementation files** for infrastructure (Smtp + Console live in one `email.py`)

**Both respect the same principles:**

- ✅ Business logic isolated from HTTP and persistence
- ✅ Encapsulation — callers don't know if the DB is PostgreSQL or SQLite
- ✅ Explicit domain boundary — `users/` does not import `hello/`
- ✅ Ubiquitous language — `User`, `EmailVerification`, `signup`
- ✅ Testable — behavior tests pass through the HTTP boundary

**The difference is ceremony, not principle adherence.** Every interface, use-case class, and layer in the Clean Architecture version exists to help a developer navigate a codebase they don't know from a diagram — at the cost of 3× the file count. The four mechanisms above provide the same coherence guarantees with a fraction of the file count.

---

## 8. Quick Reference & Anti-Patterns

### Principles Always Apply

| Principle | What it means in practice |
|---|---|
| **Business logic isolated** | Domain functions and services never import FastAPI, SQLAlchemy, or Pydantic |
| **Encapsulation** | Repository `_to_domain()` methods shield domain code from ORM model changes |
| **Ubiquitous language** | Names are consistent across the codebase: `User`, `signup`, `verify_email` |
| **Explicit boundaries** | `domains/` folders with no-cross-import lint rules |
| **Testable** | Every feature has a behavior test through the HTTP boundary |

### Patterns Apply Only When Justified

| Pattern | Applies when |
|---|---|
| Abstract interface / port | Multiple implementations exist or external contract pollution is real |
| Separate DTO | One of the three layers (API / domain / ORM) has substantially different fields |
| Domain event | Multiple independent consumers need to react to a fact |
| Use case class | A single use case has enough conditional logic to justify its own file |

### Anti-Patterns: Avoid

| Anti-Pattern | Why |
|---|---|
| **Repository interfaces** | Python's mocks make them unnecessary; a concrete class is mockable |
| **Per-entity files** | Group domain dataclasses in `repository.py` — they're passive data, not behavior |
| **Per-use-case files** | One `service.py` per domain with grouped methods is sufficient until proven otherwise |
| **Pre-emptive abstraction** | "We might need a second implementation" — no. Wait until you do. |
| **Global `common/` dumping ground** | Shared code must pass the three-question gate; don't extract "just in case" |

---

## 9. Persistence

The ORM layer uses **SQLAlchemy with `DeclarativeBase`** (SQLAlchemy 2.x style) and modern `Mapped[]` style column definitions. The async engine and session factory live in `infrastructure/orm/base.py`, providing the `get_async_session` dependency used across all repositories. UUIDv7 values are used for primary keys (provided by Python's standard `uuid` module as `uuid7()`).

**Example:** Thin ORM models using `Mapped[]` style.

```python
# infrastructure/orm/models.py
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import UUID as SAUUID

from questr.common.enums import UserRole, UserStatus
from questr.infrastructure.orm.base import Base


class UserORMModel(Base):
    __tablename__ = 'users'

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
```

### Example: User Repository

```python
# domains/users/repository.py
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from questr.common.enums import UserRole, UserStatus
from questr.infrastructure.orm.models import UserORMModel


@dataclass
class User:
    id: UUID | None = None
    username: str = ''
    email: str = ''
    # ...


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
            # ...
        )
```

---

## 10. Dependencies / DI

FastAPI's built-in `Depends()` is the only dependency injection mechanism used. Each domain's `api.py` declares its own `Depends()` providers inline. Shared dependencies (e.g., `get_client_ip`) live in `app/dependencies.py`.

```python
# app/dependencies.py
from typing import Annotated
from fastapi import Depends, Request


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


T_ClientIP = Annotated[str, Depends(get_client_ip)]
```

```python
# domains/users/api.py
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from questr.app.dependencies import T_ClientIP
from questr.infrastructure.email import (
    BaseEmailService,
    get_email_service,
)
from questr.infrastructure.login_rate_limiter import (
    LoginRateLimiter,
    get_login_rate_limiter,
)
from questr.infrastructure.orm.base import get_async_session
from questr.infrastructure.rate_limiter import (
    RedisRateLimiter,
    get_rate_limiter,
)
from questr.domains.users.repository import (
    EmailVerificationRepository,
    SessionRepository,
    UserRepository,
)
from questr.domains.users.service import AccountService, SessionService


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRepository:
    return UserRepository(session)


async def get_verification_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EmailVerificationRepository:
    return EmailVerificationRepository(session)


async def get_session_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SessionRepository:
    return SessionRepository(session)


async def get_account_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    verification_repo: Annotated[
        EmailVerificationRepository,
        Depends(get_verification_repository),
    ],
    email_service: Annotated[BaseEmailService, Depends(get_email_service)],
    rate_limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
) -> AccountService:
    return AccountService(
        user_repo=user_repo,
        verification_repo=verification_repo,
        email_service=email_service,
        rate_limiter=rate_limiter,
    )


async def get_session_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    session_repo: Annotated[
        SessionRepository, Depends(get_session_repository)
    ],
    login_rate_limiter: Annotated[
        LoginRateLimiter, Depends(get_login_rate_limiter)
    ],
) -> SessionService:
    return SessionService(
        user_repo=user_repo,
        session_repo=session_repo,
        login_rate_limiter=login_rate_limiter,
    )
```

---

## 11. Multi-Layer DTOs

The codebase maintains two representations of data:

| Layer | File | Purpose |
|---|---|---|
| API Schema | `api.py` (Pydantic models) | Request validation + response serialization |
| Domain | `repository.py` (dataclasses) | Pure business objects |
| ORM | `infrastructure/orm/models.py` (SQLAlchemy) | Database persistence |

**Mapping strategy:**

- **ORM → Domain:** The `_to_domain()` method in `repository.py` maps ORM models to domain dataclasses. This protects business logic from persistence coupling.
- **Domain → API Schema:** `model_validate()` in route handlers maps domain objects to Pydantic response models.

The ORM→domain mapping is kept because the domain layer must not know about SQLAlchemy columns. The API schema is folded into `api.py` to avoid a separate file for what is often a 1:1 field mapping.

---

## 12. App Factory & Lifespan

The app factory pattern maps directly to FastAPI. Startup and shutdown resources (database engine and Redis connection pool) are managed through the `lifespan` async context manager.

```python
# lifespan.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from questr.infrastructure.redis import close_redis
from questr.infrastructure.orm.base import engine


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
from questr.app.middleware import CsrfMiddleware
from questr.common.exceptions import (  # ... 9 exception handlers below ...
    AccountBannedError,
    AccountSuspendedError,
    AuthenticationError,
    EmailNotVerifiedError,
    InvalidVerificationTokenError,
    RateLimitExceededError,
    RateLimiterUnavailableError,
    TooManyActiveSessionsError,
    UserAlreadyExistsError,
)
from questr.lifespan import lifespan


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title='questr',
        description='Game tracking application backend',
        version='0.1.0',
        lifespan=lifespan,
    )

    app.add_middleware(CsrfMiddleware)

    # ... 9 exception handlers registered (one per custom exception) ...

    app.include_router(api_router)
    return app
```

---

## 13. Settings

Environment-aware configuration via **Pydantic `BaseSettings`** with automatic `.env` file loading.

```python
# settings.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = 'questr'
    DEBUG: bool = False
    POSTGRES_USER: str = 'questr'
    POSTGRES_PASSWORD: str = 'qB2xSEEJ-Q.UI3'
    POSTGRES_DB: str = 'questr_db'
    POSTGRES_HOST: str = '127.0.0.1'
    REDIS_HOST: str = '127.0.0.1'

    @property
    def DATABASE_URL(self) -> str:
        return (
            f'postgresql+psycopg://{self.POSTGRES_USER}'
            f':{self.POSTGRES_PASSWORD}'
            f'@{self.POSTGRES_HOST}:5432/{self.POSTGRES_DB}'
        )

    @property
    def REDIS_URL(self) -> str:
        return f'redis://{self.REDIS_HOST}:6379/0'

    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = 'localhost'
    SMTP_PORT: int = 1025
    SMTP_USER: str = ''
    SMTP_PASSWORD: str = ''
    SMTP_USE_STARTTLS: bool = True
    EMAIL_FROM: str = 'noreply@questr.app'
    APP_URL: str = 'http://localhost:8000'
    RATE_LIMIT_RESEND_MAX: int = 3
    RATE_LIMIT_RESEND_WINDOW_HOURS: int = 1

    # Login throttling
    LOGIN_PER_ACCOUNT_MAX_ATTEMPTS: int = 5
    LOGIN_PER_ACCOUNT_WINDOW_MINUTES: int = 15
    LOGIN_LOCKOUT_MINUTES: int = 30
    LOGIN_PER_IP_MAX_ATTEMPTS: int = 20
    LOGIN_PER_IP_WINDOW_MINUTES: int = 10

    # Session lifetime
    SESSION_IDLE_MINUTES: int = 30
    SESSION_ABSOLUTE_HOURS: int = 8
    SESSION_REMEMBER_DAYS: int = 30

    # Session caps / cookie security
    MAX_CONCURRENT_SESSIONS: int = 10
    SECURE_COOKIE: bool = True

    @property
    def app_url(self) -> str:
        return self.APP_URL.rstrip('/')

    model_config = {'env_file': '.env', 'extra': 'ignore'}


settings = Settings()
```

---

## 14. Database Migrations

Database schema changes are managed with **Alembic**. Migrations are stored in `migrations/`. Alembic is configured in `migrations/env.py` to import `Base` from `questr.infrastructure.orm.base` with async support.

**Makefile commands:**

```makefile
db-create-migration:  ## Create a new migration. Usage: make db-create-migration MSG="description"
	@alembic revision --autogenerate -m "$(MSG)"

db-upgrade:  ## Apply all pending migrations
	@alembic upgrade head

db-downgrade:  ## Rollback last migration
	@alembic downgrade -1
```

---

## 15. Lint Rules

Two custom lint rules are enforced via `scripts/lint_custom.py` (run with `uv run python scripts/lint_custom.py`).

### QTR001: No ORM Imports Outside Repository Files

ORM models (`infrastructure.orm.models`) must only be imported in production
files ending in `repository.py`, plus the documented `shell.py` tooling
exception. The rule scans the `questr/` package only; the `tests/` tree is out
of scope (factory-boy factories legitimately import ORM models per
[coding-guidelines.md](./coding-guidelines.md)). The matcher covers both import
shapes: `from ...orm.models import X` and `from ...orm import models`.

**Violation:**
```python
# domains/users/service.py
from questr.infrastructure.orm.models import UserORMModel  # ⛔ VIOLATION (Form B)
from questr.infrastructure.orm import models                # ⛔ VIOLATION (Form C)
```

**Allowed:**
```python
# domains/users/repository.py
from questr.infrastructure.orm.models import UserORMModel  # ✅ ALLOWED

# shell.py (documented tooling exception)
from questr.infrastructure.orm import models as _orm_models  # ✅ ALLOWED
```

### QTR002: No Cross-Domain Imports Between Domain Modules

A file inside `questr/domains/{X}` must not import from `questr/domains/{Y}` where X ≠ Y.

**Violation:**
```python
# domains/users/service.py
from questr.domains.hello import service as hello_service  # ⛔ VIOLATION
```

**Allowed — orchestrator exception:**
```python
# orchestrators/generate_report.py
from questr.domains.reports import service as reports_service   # ✅ ALLOWED
from questr.domains.billing import service as billing_service   # ✅ ALLOWED
```
