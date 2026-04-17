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

## Database Migrations

This project uses Alembic for database migrations. Use these Makefile commands:

| Command | Description |
| :-- | :-- |
| `make db-create-migration MSG="description"` | Create a new auto-generated migration |
| `make db-upgrade` | Apply all pending migrations |
| `make db-downgrade` | Rollback the last migration |

### Workflow

1. Modify ORM models in `questr/orm/models.py`
2. Run `make db-create-migration MSG="Add users table"` to generate a migration
3. Review the generated migration file
4. Run `make db-upgrade` to apply it
5. To rollback: `make db-downgrade`

## Documentation

### API

- Swagger: <http://kvm-labs:8000/docs>
- Redoc: <http://kvm-labs:8000/redoc>
