from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from questr.api.router import api_router
from questr.app.middleware import CsrfMiddleware
from questr.common.exceptions import (
    AccountBannedError,
    AccountSuspendedError,
    AuthenticationError,
    AuthorizationError,
    EmailNotVerifiedError,
    InvalidVerificationTokenError,
    RateLimiterUnavailableError,
    RateLimitExceededError,
    SelfImpersonationError,
    SuperuserImpersonationError,
    TargetNotActiveError,
    TooManyActiveSessionsError,
    UserAlreadyExistsError,
)
from questr.lifespan import lifespan
from questr.settings import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title='questr',
        description='Comics, mangas and game tracking application backend',
        version='0.1.0',
        lifespan=lifespan,
        docs_url='/docs' if settings.SERVE_DOCS else None,
        redoc_url='/redoc' if settings.SERVE_DOCS else None,
        openapi_url='/openapi.json' if settings.SERVE_DOCS else None,
    )

    app.add_middleware(CsrfMiddleware)

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
    app.add_exception_handler(
        AccountBannedError,
        _account_banned_handler,
    )
    app.add_exception_handler(
        AuthenticationError,
        _authentication_error_handler,
    )
    app.add_exception_handler(
        EmailNotVerifiedError,
        _email_not_verified_handler,
    )
    app.add_exception_handler(
        TooManyActiveSessionsError,
        _too_many_active_sessions_handler,
    )
    app.add_exception_handler(
        RateLimiterUnavailableError,
        _rate_limiter_unavailable_handler,
    )
    app.add_exception_handler(
        AuthorizationError,
        _authorization_error_handler,
    )
    app.add_exception_handler(
        SelfImpersonationError,
        _self_impersonation_handler,
    )
    app.add_exception_handler(
        SuperuserImpersonationError,
        _superuser_impersonation_handler,
    )
    app.add_exception_handler(
        TargetNotActiveError,
        _target_not_active_handler,
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
        content={'detail': str(exc), 'error_code': 'rate_limited'},
    )


async def _account_suspended_handler(
    request: Request, exc: AccountSuspendedError
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={'detail': str(exc), 'error_code': 'account_suspended'},
    )


async def _account_banned_handler(
    request: Request, exc: AccountBannedError
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={'detail': str(exc), 'error_code': 'account_banned'},
    )


async def _authentication_error_handler(
    request: Request, exc: AuthenticationError
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={'detail': str(exc)},
    )


async def _email_not_verified_handler(
    request: Request, exc: EmailNotVerifiedError
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            'detail': str(exc),
            'error_code': 'email_not_verified',
        },
    )


async def _too_many_active_sessions_handler(
    request: Request, exc: TooManyActiveSessionsError
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            'detail': str(exc),
            'error_code': 'too_many_active_sessions',
            'recovery': ['logout_all'],
        },
    )


async def _rate_limiter_unavailable_handler(
    request: Request, exc: RateLimiterUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={'detail': str(exc)},
    )


async def _authorization_error_handler(
    request: Request, exc: AuthorizationError
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={'detail': str(exc), 'error_code': 'authorization'},
    )


async def _self_impersonation_handler(
    request: Request, exc: SelfImpersonationError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            'detail': str(exc),
            'error_code': 'self_impersonation',
        },
    )


async def _superuser_impersonation_handler(
    request: Request, exc: SuperuserImpersonationError
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            'detail': str(exc),
            'error_code': 'superuser_impersonation',
        },
    )


async def _target_not_active_handler(
    request: Request, exc: TargetNotActiveError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            'detail': str(exc),
            'error_code': 'target_not_active',
        },
    )
