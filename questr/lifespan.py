from contextlib import asynccontextmanager

from fastapi import FastAPI

from questr.infrastructure.redis import close_redis
from questr.infrastructure.orm.base import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    yield
    await engine.dispose()
    await close_redis()
