# Questr

A web application to manage your gaming backlog — track progress, log hours, write reviews, and get insights about your gaming habits.

This is a full revamp of my original Questrya project, rebuilt from the ground up as a long-term pet project designed to evolve over time.

## Features

- **Multi-user support**: each user manages their own game library
- **Game tracking**: log progress, hours played, personal notes, and reviews
- **Backlog management**: add and organize games you plan to play
- **Periodic reports**: Wrapped-style summaries of games added, started, and finished, filterable by current year, current month, or a custom date range

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

- Activate the uv virtualenv:

```bash

source .venv/bin/activate

```

- Run the migrations:

```bash

make db-upgrade

```

- Raise the development server:

```bash

make dev-server

```

- Mailpit WebUI is available at: <http://kvm-labs:8025/>


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

### ADR

An Architecture Decision Record was created to address a lint/type-checker issue
with sandbox scripts executed via the shell.

**Problem:** Scripts run by `make shell` receive variables like `session`,
`UserORMModel`, and `select` dynamically at runtime via `runpy.run_path()`.
Static analysis tools (`ruff`, `ty`) flag these names as undefined.

**Decision:** A static sandbox package was created at
`scripts/fast_shell/__init__.py` that re-exports all ORM models and type
declarations. The shell injects the runtime session into this module before
executing scripts. New sandbox scripts import from `scripts.fast_shell`
instead of relying on dynamic globals, making all names resolvable by
static analysis tools.

- **ruff:** Zero violations after the change
- **ty:** All checks pass
- **Execution:** Sandbox scripts work correctly

For the full ADR, see:
`/storage/src/pi-session/codesimple/adr.20260526-095507.md`

### API

- Swagger (interactive): <http://kvm-labs:8000/docs>
- Redoc (only documentation): <http://kvm-labs:8000/redoc>
