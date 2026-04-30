.PHONY: help
SHELL := /bin/bash
PROJECT_NAME = questr
PYTHON_VERSION = 3.14

help:  ## This help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

clean:  ## Clean python bytecodes, optimized files, logs, cache, coverage...
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@find . -name "*.pyo" -delete 2>/dev/null || true
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -f .coverage
	@rm -rf htmlcov/
	@rm -fr .pytest_cache/
	@rm -fr .ruff_cache/
	@rm -f coverage.xml
	@rm -f *.log

install:  ## Install dependencies using uv
	@echo "Creating virtual environment with Python $(PYTHON_VERSION)..."
	@uv venv --python $(PYTHON_VERSION)
	@echo "Installing dependencies..."
	@uv sync
	@echo "Generating lock file..."
	@uv lock
	@echo "Installation complete!"

dev:  ## Run development server
	@uv run uvicorn questr.factory:create_app --reload --host 0.0.0.0 --port 8000

lint:  ## Run ruff linter to enforce coding practices
	@printf '\n --- \n >>> Running linter...<<<\n'
	@ruff check questr/ tests/
	@printf '\n FINISHED! \n --- \n'

lint-autofix:  ## Run ruff linter and autofix fixable errors
	@printf '\n --- \n >>> Running linter with autofix...<<<\n'
	@ruff check --fix questr/ tests/
	@printf '\n FINISHED! \n --- \n'

style:  ## Run ruff to check code style
	@echo 'running ruff format check...'
	@ruff format --check questr/ tests/

style-autofix:  ## Run ruff to format code
	@echo 'running ruff format...'
	@ruff format questr/ tests/

architecture-lint:  ## Run custom architecture lint rules
	@printf '\n --- \n >>> Running architecture lint...<<<\n'
	@uv run python scripts/lint_custom.py
	@printf '\n FINISHED! \n --- \n'

ci:  ## Run full CI pipeline (style + lint + architecture-lint)
	@printf '\n --- \n >>> Running CI pipeline...<<<\n'
	@$(MAKE) style
	@$(MAKE) lint
	@$(MAKE) architecture-lint
	@printf '\n CI PIPELINE FINISHED! \n --- \n'

test:  ## Run the test suite
	@uv run pytest -v

test-pattern:  ## Run tests matching a pattern. Usage: make test-pattern PATTERN="test_foo or test_bar"
	@uv run pytest -k "$(PATTERN)" -vvv

test-coverage:  ## Run the test coverage report
	@uv run pytest --cov=questr --cov-report=term-missing --cov-report=html

docker-up:  ## Start docker containers
	@docker compose up -d

docker-down:  ## Stop docker containers
	@docker compose down

docker-logs:  ## Show docker logs
	@docker compose logs -f

db-create-migration:  ## Create a new migration. Usage: make db-create-migration MSG="description"
	@alembic revision --autogenerate -m "$(MSG)"

db-upgrade:  ## Apply all pending migrations
	@alembic upgrade head

db-downgrade:  ## Rollback last migration
	@alembic downgrade -1

clean-postgres-data:
	$(GUARD_CHECK)
	@echo "Stopping and removing containers..."
	@set -a && source .env && set +a && docker compose down --volumes # This stops and removes containers THEN removes volumes.
	@echo "Removing PostgreSQL data directory: ./db_data/postgresql..."
	@sudo rm -rf ./db_data/postgresql/* # Use sudo for permissions, target only contents. Ensure this path is correct.
	@echo "PostgreSQL data directory cleaned."

live-restore: clean-postgres-data start-db-only restore-db-after-start  ## Perform live db restore from a given db dump file, auto-starting the containers after finished. Usage: make live-restore FILE=./backups/file.dump

start-db-only:
	$(GUARD_CHECK)
	@echo "Starting only the PostgreSQL container..."
	# Log the environment variables that should be set before docker compose up
	@echo "Makefile env check: POSTGRES_USER='${POSTGRES_USER}', POSTGRES_DB='${POSTGRES_DB}', POSTGRES_PASSWORD='${POSTGRES_PASSWORD}'"
	# Export environment variables from .env to ensure they are available to the docker compose command.
	@set -a && source .env && set +a && \
	docker compose -p $(shell basename $(PWD)) \
		-f docker-compose.yml \
		up -d db
	@echo "Giving PostgreSQL a moment to initialize and become ready..."
	@sleep 10 # Give it some time to initialize and pass its internal checks.
	@echo "PostgreSQL container started. Proceeding."

restore-db-after-start:
	$(GUARD_CHECK)
	@echo "Running database restore script after DB is up..."
	@if [ -z "$(FILE)" ]; then \
		echo "Error: No FILE specified."; \
		echo "Usage: make live-restore FILE=./backups/my_backup.dump"; \
		exit 1; \
	fi
	@./scripts/pg_restore.sh "$(FILE)"

dump-db:  ## Perform a database backup using pg_dump
	@echo "Running database dump script..."
	@./scripts/pg_dump.sh

pgcli:  ## Starts pgcli (requires it installed with uv tool)
	@echo "Starting pgcli..."
	@./scripts/pg_cli.sh

fix-permissions:  ## Make the scripts executable
	chmod +x scripts/*.sh
