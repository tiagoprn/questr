from typing import Annotated

from fastapi import Depends, Request

from questr.infrastructure.rate_limiter import RedisRateLimiter


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


T_ClientIP = Annotated[str, Depends(get_client_ip)]
