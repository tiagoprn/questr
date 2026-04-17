from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from questr.api.router import api_router
from questr.common.exceptions import (
    AccountSuspendedError,
    InvalidVerificationTokenError,
    RateLimitExceededError,
    UserAlreadyExistsError,
)
from questr.lifespan import lifespan


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title='questr',
        description='Game tracking application backend',
        version='0.1.0',
        lifespan=lifespan,
    )

    app.add_exception_handler(
        UserAlreadyExistsError,
        _user_already_exists_handler,
    )
    app.add_exception_handler(
        InvalidVerificationTokenError,
        _invalid_token_handler,
    )
    app.add_exception_handler(
        RateLimitExceededError,
        _rate_limit_handler,
    )
    app.add_exception_handler(
        AccountSuspendedError,
        _account_suspended_handler,
    )

    app.include_router(api_router)
    return app


async def _user_already_exists_handler(
    request: Request, exc: UserAlreadyExistsError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={'detail': str(exc)},
    )


async def _invalid_token_handler(
    request: Request, exc: InvalidVerificationTokenError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={'detail': str(exc)},
    )


async def _rate_limit_handler(
    request: Request, exc: RateLimitExceededError
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={'detail': str(exc)},
    )


async def _account_suspended_handler(
    request: Request, exc: AccountSuspendedError
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={'detail': str(exc)},
    )
