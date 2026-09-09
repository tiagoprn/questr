# syntax=docker/dockerfile:1
# Production image for questr (Phase 1, change 008). Two-stage uv build on
# python:3.14-slim-trixie. Build context is the repo root; the ignore file is
# deploy/Dockerfile.dockerignore (BuildKit per-Dockerfile ignore).

# Pinned uv builder image; only /uv is taken from it.
FROM ghcr.io/astral-sh/uv:0.12.9 AS uv

FROM python:3.14-slim-trixie AS build

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Resolve dependencies first, bind-mounting only the lock inputs, so source
# edits do not bust the dependency layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project

# Install the project non-editable so importlib.metadata.version("questr")
# resolves inside the image.
COPY pyproject.toml uv.lock README.md LICENSE alembic.ini ./
COPY questr/ ./questr/
COPY migrations/ ./migrations/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


FROM python:3.14-slim-trixie AS runtime

RUN groupadd --system app && \
    useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=build --chown=app:app /app/.venv /app/.venv
# Migration artifacts live in the image so the one-off
# `docker compose run --rm app alembic upgrade head` works on the VM.
COPY --chown=app:app migrations/ ./migrations/
COPY --chown=app:app alembic.ini ./alembic.ini

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1

USER app

# Build-time smoke test: the app imports as a non-root user in isolation.
RUN python -Ic "import questr"

# exec-form CMD; --factory because the app is created by a factory function.
# Worker count comes from WEB_CONCURRENCY (uvicorn default). No --reload.
CMD ["uvicorn", "questr.factory:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
