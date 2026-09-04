# Questr

A web application to manage your comics, mangas and games backlog — track progress, log hours, write reviews, and get insights about your habits.

This is a full revamp of my original Questrya project, rebuilt from the ground up as a long-term pet project designed to evolve over time.

## Features

- **Multi-user support**: each user manages their own library
- **Tracking**: log progress, hours played, personal notes, and reviews
- **Backlog management**: add and organize comics, mangas and games you plan to play
- **Periodic reports**: Wrapped-style summaries of comics, mangas and games added, started, and finished, filterable by current year, current month, or a custom date range.

## Tech Stack

### Backend

| Tool | Technology |
| :-- | :-- |
| Language | Python 3.14 |
| Package Manager | uv |
| Linter/Formatter | Ruff |
| Frameworks | FastAPI, SQLAlchemy |
| Database | PostgreSQL |

### Frontend

> Detailed docs coming soon.

### Ops

> Detailed docs coming soon.

## Documentation

### Local development server

> NOTE: if you want to quickly reset containers & restore db dump:

```bash

source .venv/bin/activate && \
make docker-reset-all && \
sleep 60 && \
make db-live-restore FILE=./backups/postgres/db-dumps/  ## dump file name here

```

Otherwise, follow the instructions below.

#### 01) Reset containers, setup database from migrations and raise dev server

```bash

source .venv/bin/activate && \
make docker-reset-all && \
sleep 60 && \
make db-upgrade  && \
make dev-server

```

After this, open a new terminal, because the `dev-server` command will hold it.

#### 02) Seed the db with users, activate 2 of them and promote "supe" to superuser

```bash

source .venv/bin/activate && \
make dev-hurl-create-users && \
make shell SCRIPT=scripts/fast_shell/verify_user.py EMAIL=tiago+third@gmail.com && \
make shell SCRIPT=scripts/fast_shell/verify_user.py EMAIL=tiago+supe@gmail.com && \
make dev-hurl-auth-flow && \
make shell SCRIPT=scripts/fast_shell/promote_superuser.py EMAIL=tiago+supe@gmail.com

```

> NOTE: Mailpit WebUI is available at: <http://kvm-labs:8025/>

### Database Migrations

This project uses Alembic for database migrations. Use these Makefile commands:

| Command | Description |
| :-- | :-- |
| `make db-create-migration MSG="description"` | Create a new auto-generated migration |
| `make db-upgrade` | Apply all pending migrations |
| `make db-downgrade` | Rollback the last migration |

#### Workflow

1. Modify ORM models in `questr/orm/models.py`
2. Run `make db-create-migration MSG="Add users table"` to generate a migration
3. Review the generated migration file
4. Run `make db-upgrade` to apply it
5. To rollback: `make db-downgrade`

### Shell support

Questr provides an IPython-based interactive shell for running queries
against the database with all ORM models, async session, and settings
auto-imported.

See the [full documentation](docs/backend/shell.md) for usage and details.

### API docs

The interactive API documentation (Swagger UI, ReDoc) and the OpenAPI schema
(`/openapi.json`) are served **only in development** (`ENVIRONMENT=dev`).
This is controlled by the `SERVE_DOCS` setting in `questr/settings.py`:

```python
SERVE_DOCS = (ENVIRONMENT == 'dev')
```

When `SERVE_DOCS` is false (e.g. `ENVIRONMENT=prod`), the three endpoints are
disabled at app construction (`docs_url=None`, `redoc_url=None`,
`openapi_url=None`) and return 404.

- Swagger UI: [http://kvm-labs:8000/docs](http://kvm-labs:8000/docs)
- ReDoc: [http://kvm-labs:8000/redoc](http://kvm-labs:8000/redoc)

### App version

The application version reported by the OpenAPI schema and the
`/health/ready` endpoint is read from a single source of truth: the
`version` field in `pyproject.toml`.

At runtime it is resolved once via `importlib.metadata.version('questr')`
in `questr/infrastructure/health.py` (exported as `APP_VERSION` and used by
`questr/factory.py` for the FastAPI `version`).

To bump the version:

1. Update `version` in `pyproject.toml`.
2. Reinstall the package (`uv sync` or `uv pip install -e .`) so the
   installed metadata reflects the new value.

No other file hardcodes the version.

### Backend Coding Architecture

The backend uses Clean Architecture, but in a pragmatic and non-convoluted way, using KISS principles and being a solid base that can be improved on in the future. You can find more details about that at <./docs/backend/ARCHITECTURE.md>.

Also, ADRs (Architecture Decision Records) can be found at <./docs/backend/ADRs/>.
> TODO: there are some more that must be moved from `/storage/src/qntuum/llm/okf/questr/adrs`

## Security

### API documentation access control

The OpenAPI schema (Swagger UI, Redoc, and `/openapi.json`) is **disabled** in
production. This prevents accidental exposure of the internal API surface to
unauthorised parties.

**Rationale:**

- The OpenAPI schema is a development aid, not a production feature. It
  enumerates every endpoint, request body schema, and response format, which
  provides unnecessary reconnaissance information to potential attackers.
- A `superuser` role was previously considered for gating these endpoints, but
  role escalation via direct database writes lacks auditability, accountability,
  and revocation. Any team member with database credentials can silently
  escalate privileges with no trace.
- The current approach uses the `ENVIRONMENT` discriminator: docs are served
  only when `ENVIRONMENT=dev`, and completely removed from the routing table
  in `prod`.

Documentation for the API should be delivered to integrators via a static
export (e.g., an OpenAPI YAML file) rather than through the running
application.
