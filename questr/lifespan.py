from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    # Startup
    yield
    # Shutdown
    # TODO: Add cleanup code here (e.g., database engine disposal)
    pass
