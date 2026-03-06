from fastapi import FastAPI

from questr.api.router import api_router
from questr.lifespan import lifespan


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title='questr',
        description='Game tracking application backend',
        version='0.1.0',
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app
