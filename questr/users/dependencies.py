from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from questr.common.rate_limiter import RedisRateLimiter
from questr.common.redis import get_redis
from questr.common.services.email_service import (
    BaseEmailService,
    get_email_service,
)
from questr.orm.base import get_async_session
from questr.settings import settings
from questr.users.repository import (
    EmailVerificationRepository,
    UserRepository,
)
from questr.users.service import AuthService


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRepository:
    return UserRepository(session)


async def get_verification_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EmailVerificationRepository:
    return EmailVerificationRepository(session)


async def get_rate_limiter() -> RedisRateLimiter:
    redis = get_redis()
    return RedisRateLimiter(
        redis=redis,
        max_requests=settings.RATE_LIMIT_RESEND_MAX,
        window_seconds=settings.RATE_LIMIT_RESEND_WINDOW_HOURS * 3600,
    )


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


async def get_auth_service(
    user_repo: Annotated[
        UserRepository, Depends(get_user_repository)
    ],
    verification_repo: Annotated[
        EmailVerificationRepository,
        Depends(get_verification_repository),
    ],
    email_service: Annotated[
        BaseEmailService, Depends(get_email_service)
    ],
    rate_limiter: Annotated[
        RedisRateLimiter, Depends(get_rate_limiter)
    ],
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        verification_repo=verification_repo,
        email_service=email_service,
        rate_limiter=rate_limiter,
    )


T_UserRepo = Annotated[
    UserRepository, Depends(get_user_repository)
]
T_VerificationRepo = Annotated[
    EmailVerificationRepository,
    Depends(get_verification_repository),
]
T_AuthService = Annotated[AuthService, Depends(get_auth_service)]
T_ClientIP = Annotated[str, Depends(get_client_ip)]
