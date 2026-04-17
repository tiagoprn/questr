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
