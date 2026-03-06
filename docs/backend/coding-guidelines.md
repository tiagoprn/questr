# Coding Guidelines

## Dependency Management
- This is a **Python 3.14** project. Use `uv` for all dependency management and virtual environment setup. Never use `poetry` or `pip`.

## Code Style
- Use `ruff` as the code formatter and linter.
- Configure `ruff` in `pyproject.toml` as follows:

```toml
[tool.ruff]
line-length = 79

[tool.ruff.lint]
preview = true
select = ['I', 'F', 'E', 'W', 'PL', 'PT']

[tool.ruff.format]
preview = true
quote-style = 'single'
```

## Database
- Use **PostgreSQL** (in a Docker container) as the database. Never use SQLite, translate any SQLite command/query/code to its PostgreSQL equivalent.
- Use `psycopg[binary]` as the Python driver.
- Run migrations with Alembic before starting the app: `alembic upgrade head`.

## Configuration
- Manage all settings with `pydantic-settings`.
- Declare `Annotated` dependency types at the top of each module, prefixed with `T_` by convention.
  - Example: `T_Session = Annotated[Session, Depends(get_session)]`

## Pydantic Models
- Always configure Pydantic models with `ConfigDict(from_attributes=True)` to allow ORM-to-schema conversion.
- Use `.model_validate(obj).model_dump()` for converting DB objects to schemas.

## Testing
- Use **testcontainers** (`testcontainers-python`) for integration tests against PostgreSQL — never mock the DB with SQLite.
- Use `factory-boy` to create model instances in tests (use `LazyAttribute` for derived fields).
- Use `freezegun` to control time-dependent behavior in tests.
- Set fixture scope deliberately: `scope='session'` for the DB engine, `scope='function'` for individual sessions.

## Docker
- Use `docker compose` for local development and deployment.
- Use an `entrypoint.sh` script (via `ENTRYPOINT` in `docker compose`) to run migrations before starting the app with `uvicorn`.
- Use `pg_isready` to verify the database is online before the app starts.
