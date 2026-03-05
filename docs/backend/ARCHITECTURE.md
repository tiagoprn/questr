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
│   ├── exceptions.py
│   └── value_objects/
│       ├── __init__.py
│       ├── game_rating.py
│       └── email.py
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
│   └── models.py              # ORM models (thin)
├── api/
│   ├── __init__.py
│   └── router.py              # Root APIRouter: includes all feature routers
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

**Example:** `Email` as a value object for user registration.

```python
# common/value_objects/email.py
class Email:
    def __init__(self, value: str) -> None:
        if not value or "@" not in value:
            raise ValueError(f"Invalid email address: {value}")
        self._value = value.lower()

    @property
    def value(self) -> str:
        return self._value

    def is_corporate(self) -> bool:
        return not self._value.endswith("@gmail.com")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Email):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)
```

**Why use value objects?**

- **Validation in one place**: Instead of validating emails in every service or router, the `Email` class handles it
- **Self-documenting code**: Functions that take `Email` instead of `str` are clearer
- **Built-in behavior**: Methods like `is_corporate()` live with the data they operate on

```python
# Using the value object
def register_user(email: Email, name: str) -> User:
    # Email is already validated - no need for extra checks
    if email.is_corporate():
        # Give corporate users premium access
        pass
    ...
```

#### Domain

Domain objects encapsulate core business logic, rules, and behaviors central to the application. They represent the "what" of the system. Domain objects are pure Python — they have zero knowledge of FastAPI, SQLAlchemy, or Pydantic.

**Example:** `Game` domain object containing game state management and business rules.

```python
# games/domain.py
from datetime import datetime
from common.exceptions import InvalidGameStateError

class Game:
    def __init__(self, id, title, platform, release_date, status, completion_date=None):
        self.id = id
        self.title = title
        self.platform = platform
        self.release_date = release_date
        self.status = status
        self.completion_date = completion_date

    def mark_completed(self, completion_date=None) -> None:
        if self.status == GameStatus.ABANDONED:
            raise InvalidGameStateError("Cannot complete an abandoned game")
        self.status = GameStatus.COMPLETED
        self.completion_date = completion_date or datetime.now()
```

#### Repository

Repositories abstract data access logic and provide methods to retrieve and persist domain objects. In FastAPI, repositories receive an async SQLAlchemy `AsyncSession` injected via `Depends`.

**Example:** `GameRepository` handling game ORM and retrieval.

```python
# games/repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from orm.models import GameModel
from games.domain import Game

class GameRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, game_id: int) -> Game | None:
        result = await self.session.execute(
            select(GameModel).where(GameModel.id == game_id)
        )
        game_model = result.scalar_one_or_none()
        return self._to_domain(game_model) if game_model else None

    async def get_backlog(self, user_id: int, status=None) -> list[Game]:
        query = select(GameModel).where(GameModel.user_id == user_id)
        if status:
            query = query.where(GameModel.status == status.value)
        result = await self.session.execute(query)
        return [self._to_domain(g) for g in result.scalars().all()]

    def _to_domain(self, model: GameModel) -> Game:
        return Game(
            id=model.id,
            title=model.title,
            platform=model.platform,
            release_date=model.release_date,
            status=GameStatus(model.status),
            completion_date=model.completion_date,
        )
```

#### Service

Services coordinate complex operations involving multiple domain objects or repositories. They implement application use cases and orchestrate business processes. In FastAPI, services are typically instantiated via `Depends` in a feature's `dependencies.py` — they are not singletons.

**Example:** `GameService` handling operations like game updates or status changes.

```python
# games/service.py
from games.repository import GameRepository
from users.repository import UserRepository
from games.domain import Game, GameStatus
from common.exceptions import ResourceNotFoundError

class GameService:
    def __init__(self, game_repository: GameRepository, user_repository: UserRepository) -> None:
        self.game_repository = game_repository
        self.user_repository = user_repository

    async def add_to_backlog(self, title: str, platform: str, release_date, user_id: int) -> Game:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User not found")

        game = Game(
            id=None,
            title=title,
            platform=platform,
            release_date=release_date,
            status=GameStatus.NOT_STARTED,
            user_id=user_id,
        )
        saved_game = await self.game_repository.save(game)

        # Queue background task to fetch additional game info
        from workers.tasks.game_tasks import fetch_game_metadata
        fetch_game_metadata.delay(saved_game.id)

        return saved_game
```

#### Dependencies

`dependencies.py` is a FastAPI-specific file inside each feature module. It contains `Depends` provider functions that wire up repositories and services to the async DB session.

**Example:** Game dependencies.

```python
# games/dependencies.py
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from orm.base import get_async_session
from games.repository import GameRepository
from users.repository import UserRepository
from games.service import GameService


async def get_game_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> GameRepository:
    return GameRepository(session)


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRepository:
    return UserRepository(session)


async def get_game_service(
    game_repo: Annotated[GameRepository, Depends(get_game_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> GameService:
    return GameService(game_repo, user_repo)
```

#### Background Tasks

Background tasks handle time-consuming operations that should run outside the main request flow. FastAPI provides a built-in `BackgroundTasks` mechanism that is suitable for most use cases without requiring additional infrastructure.

**Example:** Triggering a background task from a service.

```python
# games/service.py
from games.repository import GameRepository
from users.repository import UserRepository
from games.domain import Game, GameStatus
from common.exceptions import ResourceNotFoundError

async def fetch_game_metadata(game_id: int) -> None:
    """Fetch additional metadata for a game from external API."""
    # This runs in the same event loop, no separate process needed
    from orm.base import AsyncSessionLocal
    from games.repository import GameRepository

    async with AsyncSessionLocal() as session:
        repo = GameRepository(session)
        game = await repo.get_by_id(game_id)
        if not game:
            return
        # Fetch metadata from external API
        # Update game with additional details
        await repo.save(game)


class GameService:
    def __init__(self, game_repository: GameRepository, user_repository: UserRepository) -> None:
        self.game_repository = game_repository
        self.user_repository = user_repository

    async def add_to_backlog(self, title: str, platform: str, release_date, user_id: int, background_tasks=None) -> Game:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User not found")

        game = Game(
            id=None,
            title=title,
            platform=platform,
            release_date=release_date,
            status=GameStatus.NOT_STARTED,
            user_id=user_id,
        )
        saved_game = await self.game_repository.save(game)

        # Queue background task to fetch additional game info
        if background_tasks:
            background_tasks.add_task(fetch_game_metadata, saved_game.id)

        return saved_game
```

**Example:** Using background tasks in a router.

```python
# games/router.py
from typing import Annotated
from fastapi import APIRouter, Depends, BackgroundTasks, status
from games.schemas import GameCreate, GameResponse
from games.service import GameService, fetch_game_metadata
from games.dependencies import get_game_service
from users.dependencies import get_current_user
from users.domain import User

router = APIRouter(prefix="/games", tags=["games"])


@router.post("/", response_model=GameResponse, status_code=status.HTTP_201_CREATED)
async def add_game(
    payload: GameCreate,
    background_tasks: BackgroundTasks,
    service: Annotated[GameService, Depends(get_game_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GameResponse:
    game = await service.add_to_backlog(
        title=payload.title,
        platform=payload.platform,
        release_date=payload.release_date,
        user_id=current_user.id,
        background_tasks=background_tasks,
    )
    return GameResponse.model_validate(game)
```

> **NOTE:** BackgroundTasks runs within the same process and event loop as the FastAPI application. This is suitable for I/O-bound tasks like API calls, sending emails, or simple data processing. If we later need distributed task processing (multiple workers, complex retry policies, scheduled tasks across instances), then we will consider integrating Celery at that time.
```

#### Schemas

Schemas are **Pydantic `BaseModel`** subclasses — FastAPI uses them natively for request body validation and response serialization.

**Example:** `GameCreate` Pydantic models for request and response.

```python
# games/schemas.py
from datetime import date, datetime
from pydantic import BaseModel

class GameCreateRequest(BaseModel):
    title: str
    platform: str
    release_date: date | None = None

class GameCreateResponse(BaseModel):
    id: int
    title: str
    platform: str
    release_date: date | None
    status: str
    completion_date: datetime | None

    model_config = {"from_attributes": True}
```

#### Router

`router.py` files are the HTTP entry points of each feature module. They define the API endpoints using FastAPI's `APIRouter`, keeping route declarations co-located with the rest of the feature's code.

Each handler is declared as `async def`, so it participates naturally in FastAPI's async request lifecycle without blocking the event loop. Request bodies are typed as Pydantic schema parameters — FastAPI validates incoming JSON against them automatically and returns clean error responses when validation fails. Outgoing data is controlled by the `response_model` parameter on the route decorator, which both serializes the response and drives the auto-generated OpenAPI documentation. The authenticated user is provided via `Depends`, injected from `users/dependencies.py`.


**Example:** Game API endpoints.

```python
# games/router.py
from typing import Annotated
from fastapi import APIRouter, Depends, status
from games.schemas import GameCreate, GameResponse
from games.service import GameService
from games.dependencies import get_game_service
from users.dependencies import get_current_user
from users.domain import User

router = APIRouter(prefix="/games", tags=["games"])


@router.post("/", response_model=GameResponse, status_code=status.HTTP_201_CREATED)
async def add_game(
    payload: GameCreate,
    service: Annotated[GameService, Depends(get_game_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GameResponse:
    game = await service.add_to_backlog(
        title=payload.title,
        platform=payload.platform,
        release_date=payload.release_date,
        user_id=current_user.id,
    )
    return GameResponse.model_validate(game)
```

#### Persistence

The ORM layer uses **SQLAlchemy with `DeclarativeBase`** (SQLAlchemy 2.x style). The async engine and session factory live in `orm/base.py`, providing the `get_async_session` dependency used across all repositories.

**Example:** Thin ORM models and async session setup.

```python
# orm/base.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from questr.settings import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

```python
# orm/models.py
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey
from orm.base import Base

class GameModel(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    platform = Column(String(50), nullable=False)
    release_date = Column(Date)
    status = Column(String(20), nullable=False)
    completion_date = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
```

#### API Router Registration

`api/router.py` aggregates all feature routers into a single root `APIRouter` which is then included in the app factory.

**Example:** Root router setup.

```python
# api/router.py
from fastapi import APIRouter
from games.router import router as games_router
from users.router import router as users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(games_router)
api_router.include_router(users_router)
```

#### App Factory & Lifespan

The app factory pattern maps directly to FastAPI. Startup and shutdown resources (such as the database engine) are managed through the `lifespan` async context manager, which replaces any ad-hoc initialization hooks with a single, clean `async with` lifecycle tied to the application.


**Example:** Lifespan and app factory.

```python
# lifespan.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from orm.base import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
    await engine.dispose()
```

```python
# factory.py
from fastapi import FastAPI
from api.router import api_router
from lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="questr", lifespan=lifespan)
    app.include_router(api_router)
    return app
```

#### Settings

Replace plain module-level constants with **Pydantic `BaseSettings`** for environment-aware configuration with automatic `.env` file loading.

```python
# settings.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
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
