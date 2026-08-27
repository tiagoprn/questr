from contextlib import asynccontextmanager

from fastapi import FastAPI

from questr.infrastructure.orm.base import engine
from questr.infrastructure.redis import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    app.state.started = False
    app.state.started = True
    yield
    app.state.started = False
    await engine.dispose()
    await close_redis()
