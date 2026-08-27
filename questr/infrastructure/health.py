"""Kubernetes health endpoints for the questr application.

These endpoints are a cross-cutting infrastructure concern, not a business
domain. They live in ``infrastructure/`` and are wired at the app root by
``factory.py`` so the kubelet can reach them without the ``/api`` prefix.

Lazy import note: ``engine`` and ``get_redis`` are NOT name-bound at import
time. They are accessed via module attributes so tests can rebind
``questr.infrastructure.orm.base.engine`` and
``questr.infrastructure.redis._pool`` to testcontainers instances. A
name-bound import would freeze the dev-database engine into this module.
"""

import asyncio
import importlib.metadata
import logging
import time
from collections.abc import Awaitable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from questr.infrastructure import redis as redis_infra
from questr.infrastructure.orm import base
from questr.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=['health'])

APP_VERSION: str = importlib.metadata.version('questr')

_DATABASE_ERROR = 'database unreachable'
_REDIS_ERROR = 'redis unreachable'


def _elapsed_ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 1)


async def check_database() -> dict[str, bool | str | float]:
    """Return a health check dict for PostgreSQL connectivity."""
    start = time.monotonic()
    try:
        async with base.engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
    except Exception as exc:  # noqa: BLE001
        logger.warning('database health check failed: %s', exc)
        return {
            'healthy': False,
            'error': _DATABASE_ERROR,
            'latency_ms': _elapsed_ms(start),
        }
    return {
        'healthy': True,
        'latency_ms': _elapsed_ms(start),
    }


async def check_redis() -> dict[str, bool | str | float]:
    """Return a health check dict for Redis connectivity."""
    start = time.monotonic()
    redis = None
    try:
        redis = redis_infra.get_redis()
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning('redis health check failed: %s', exc)
        return {
            'healthy': False,
            'error': _REDIS_ERROR,
            'latency_ms': _elapsed_ms(start),
        }
    finally:
        # A from_pool client's aclose() releases the client without closing
        # the shared pool. Guard the close so a failure here can never convert
        # an unhealthy 503 into a 500 (the never-500 contract).
        if redis is not None:
            try:
                await redis.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning('redis health check aclose failed: %s', exc)
    return {
        'healthy': True,
        'latency_ms': _elapsed_ms(start),
    }


async def _run_checked(
    name: str, coro: Awaitable[dict[str, bool | str | float]], timeout: float
) -> dict[str, bool | str | float]:
    """Run a check coroutine under a timeout, normalizing timeouts."""
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning('%s health check timed out', name)
        return {
            'healthy': False,
            'error': f'{name} check timed out',
            'latency_ms': _elapsed_ms(start),
        }
    result.setdefault('latency_ms', _elapsed_ms(start))
    return result


@router.get('/health')
async def liveness() -> dict:
    """Report liveness: the process is up, independent of dependencies."""
    return {'status': 'alive'}


@router.get('/health/ready')
async def readiness() -> JSONResponse:
    """Report readiness by checking PostgreSQL and Redis concurrently."""
    timeout = settings.HEALTH_CHECK_TIMEOUT_SECONDS
    db_result, redis_result = await asyncio.gather(
        _run_checked('database', check_database(), timeout),
        _run_checked('redis', check_redis(), timeout),
    )
    checks = {'database': db_result, 'redis': redis_result}
    ready = all(check['healthy'] for check in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            'status': 'ready' if ready else 'not_ready',
            'checks': checks,
            'version': APP_VERSION,
        },
    )


@router.get('/health/started')
async def started(request: Request) -> JSONResponse:
    """Report startup state, which gates kubelet liveness and readiness."""
    is_started = getattr(request.app.state, 'started', False)
    return JSONResponse(
        status_code=200 if is_started else 503,
        content={'status': 'started' if is_started else 'not_started'},
    )
