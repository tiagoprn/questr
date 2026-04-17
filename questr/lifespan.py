from contextlib import asynccontextmanager

from fastapi import FastAPI

from questr.common.redis import close_redis
from questr.orm.base import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()
    await close_redis()
