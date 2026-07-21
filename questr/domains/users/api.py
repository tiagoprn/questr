from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from questr.app.dependencies import T_ClientIP
from questr.common.enums import UserRole, UserStatus
from questr.common.exceptions import AuthenticationError
from questr.domains.users.repository import (
    EmailVerificationRepository,
    SessionRepository,
    UserRepository,
)
from questr.domains.users.service import AuthService
from questr.infrastructure.email import (
    BaseEmailService,
    get_email_service,
)
from questr.infrastructure.login_rate_limiter import (
    LoginRateLimiter,
    get_login_rate_limiter,
)
from questr.infrastructure.orm.base import get_async_session
from questr.infrastructure.rate_limiter import (
    RedisRateLimiter,
    get_rate_limiter,
)
from questr.settings import settings

router = APIRouter(prefix='/v1/auth', tags=['auth'])


# ── Schemas ──────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    username: str
    # NOTE: Email with `+` tag (e.g., user+tag@domain) is stored as-is
    # and treated as a distinct identity. `user+tag1@gmail.com` and
    # `user+tag2@gmail.com` are different users.
    email: EmailStr
    first_name: str
    last_name: str
    password: str
    password_confirmation: str


class SignupResponse(BaseModel):
    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    status: UserStatus

    model_config = {'from_attributes': True}


class VerifyEmailResponse(BaseModel):
    id: UUID
    username: str
    email: str
    status: UserStatus

    model_config = {'from_attributes': True}


class ResendVerificationRequest(BaseModel):
    email: EmailStr  # Exact match — full email including `+` tag


class ResendVerificationResponse(BaseModel):
    message: str


class PasswordValidationError(BaseModel):
    errors: list[str]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class _UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    user_status: UserStatus = Field(
        ...,
        alias='status',
        serialization_alias='user_status',
    )
    created_at: datetime | None = None

    model_config = {'from_attributes': True, 'populate_by_name': True}


class _SessionMeta(BaseModel):
    issued_at: datetime
    expires_at: datetime
    absolute_expires_at: datetime


class LoginResponse(BaseModel):
    user: _UserResponse
    session: _SessionMeta
    csrf_token: str


class LogoutResponse(BaseModel):
    message: str


class LogoutAllResponse(BaseModel):
    message: str
    sessions_revoked: int


class MeResponse(BaseModel):
    user: _UserResponse
    csrf_token: str


# ── Dependencies ──────────────────────────────────────────────────────


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRepository:
    return UserRepository(session)


async def get_verification_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EmailVerificationRepository:
    return EmailVerificationRepository(session)


async def get_auth_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    verification_repo: Annotated[
        EmailVerificationRepository,
        Depends(get_verification_repository),
    ],
    email_service: Annotated[BaseEmailService, Depends(get_email_service)],
    rate_limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        verification_repo=verification_repo,
        email_service=email_service,
        rate_limiter=rate_limiter,
    )


T_UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
T_VerificationRepo = Annotated[
    EmailVerificationRepository,
    Depends(get_verification_repository),
]
T_AuthService = Annotated[AuthService, Depends(get_auth_service)]


async def get_session_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SessionRepository:
    return SessionRepository(session)


T_SessionRepo = Annotated[SessionRepository, Depends(get_session_repository)]
T_LoginRateLimiter = Annotated[
    LoginRateLimiter, Depends(get_login_rate_limiter)
]


async def get_auth_service_v2(  # noqa: PLR0913, PLR0917
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    verification_repo: Annotated[
        EmailVerificationRepository,
        Depends(get_verification_repository),
    ],
    email_service: Annotated[BaseEmailService, Depends(get_email_service)],
    rate_limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    session_repo: Annotated[
        SessionRepository, Depends(get_session_repository)
    ],
    login_rate_limiter: Annotated[
        LoginRateLimiter, Depends(get_login_rate_limiter)
    ],
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        verification_repo=verification_repo,
        email_service=email_service,
        rate_limiter=rate_limiter,
        session_repo=session_repo,
        login_rate_limiter=login_rate_limiter,
    )


T_AuthServiceV2 = Annotated[AuthService, Depends(get_auth_service_v2)]


async def get_current_user(
    request: Request,
    auth_service: T_AuthServiceV2,
) -> dict:
    """Extract session from cookie and return user + CSRF token."""
    session_id = request.cookies.get('session_id')
    if session_id is None:
        raise AuthenticationError('Not authenticated')
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise AuthenticationError('Not authenticated') from None
    user = await auth_service.validate_session(session_uuid)
    # The CSRF token isn't stored in the service; the API layer
    # re-echoes it from the session. We rely on the cookie.
    csrf_token = request.cookies.get('csrf_token', '')
    return {'user': user, 'csrf_token': csrf_token}


# ── Routes ────────────────────────────────────────────────────────────


@router.post(
    '/signup',
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {'model': PasswordValidationError},
        409: {'description': 'Username or email already exists'},
    },
)
async def signup(
    payload: SignupRequest,
    service: T_AuthService,
    client_ip: T_ClientIP,
) -> SignupResponse:
    user = await service.signup(
        username=payload.username,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password=payload.password,
        password_confirmation=payload.password_confirmation,
        client_ip=client_ip,
    )
    return SignupResponse.model_validate(user)


@router.get(
    '/verify-email/{token}',
    response_model=VerifyEmailResponse,
    responses={
        400: {'description': 'Invalid or expired token'},
    },
)
async def verify_email(
    token: str,
    service: T_AuthService,
) -> VerifyEmailResponse:
    user = await service.verify_email(token)
    return VerifyEmailResponse.model_validate(user)


@router.post(
    '/resend-verification',
    response_model=ResendVerificationResponse,
    responses={
        429: {'description': 'Rate limit exceeded'},
    },
)
async def resend_verification(
    payload: ResendVerificationRequest,
    service: T_AuthService,
    client_ip: T_ClientIP,
) -> ResendVerificationResponse:
    await service.resend_verification(email=payload.email, client_ip=client_ip)
    return ResendVerificationResponse(
        message='If an account with this email exists, '
        'a new verification email has been sent.'
    )


@router.post(
    '/login',
    response_model=LoginResponse,
    responses={
        401: {'description': 'Invalid email or password'},
        403: {'description': 'Account state error'},
        429: {'description': 'Too many attempts'},
    },
)
async def login(
    payload: LoginRequest,
    service: T_AuthServiceV2,
    client_ip: T_ClientIP,
) -> LoginResponse:
    result = await service.login(
        email=payload.email,
        password=payload.password,
        client_ip=client_ip,
        remember_me=payload.remember_me,
    )
    user = result['user']
    session = result['session']
    csrf_raw = result['csrf_token']

    resp = LoginResponse(
        user=_UserResponse.model_validate(user),
        session=_SessionMeta(
            issued_at=session.issued_at,
            expires_at=session.expires_at,
            absolute_expires_at=session.absolute_expires_at,
        ),
        csrf_token=csrf_raw,
    )

    # Set cookies per TD-005
    secure = settings.SECURE_COOKIE
    resp = Response(
        content=resp.model_dump_json(by_alias=True),
        media_type='application/json',
        status_code=200,
    )
    resp.set_cookie(
        key='session_id',
        value=str(session.id),
        httponly=True,
        secure=secure,
        samesite='lax',
        path='/api/v1/auth',
    )
    resp.set_cookie(
        key='csrf_token',
        value=csrf_raw,
        httponly=False,
        secure=secure,
        samesite='lax',
        path='/',
    )
    return resp


@router.post(
    '/logout',
    response_model=LogoutResponse,
)
async def logout(
    request: Request,
    service: T_AuthServiceV2,
) -> LogoutResponse:
    session_id = request.cookies.get('session_id')
    if session_id:
        try:
            session_uuid = UUID(session_id)
            await service.logout(session_uuid)
        except ValueError:
            pass

    secure = settings.SECURE_COOKIE
    resp = Response(
        content=LogoutResponse(message='Logged out').model_dump_json(),
        media_type='application/json',
        status_code=200,
    )
    resp.delete_cookie(
        key='session_id',
        path='/api/v1/auth',
        secure=secure,
        httponly=True,
        samesite='lax',
    )
    resp.delete_cookie(
        key='csrf_token',
        path='/',
        secure=secure,
        httponly=False,
        samesite='lax',
    )
    return resp


@router.post(
    '/logout-all',
    response_model=LogoutAllResponse,
)
async def logout_all(
    request: Request,
    service: T_AuthServiceV2,
) -> LogoutAllResponse:
    session_id = request.cookies.get('session_id')
    user_id = None
    if session_id:
        try:
            session_uuid = UUID(session_id)
            session_obj = await service.session_repo.get_by_id(session_uuid)
            if session_obj:
                user_id = session_obj.user_id
        except ValueError:
            pass

    revoked = 0
    if user_id:
        revoked = await service.logout_all(user_id)

    secure = settings.SECURE_COOKIE
    resp = Response(
        content=LogoutAllResponse(
            message='All sessions revoked',
            sessions_revoked=revoked,
        ).model_dump_json(),
        media_type='application/json',
        status_code=200,
    )
    resp.delete_cookie(
        key='session_id',
        path='/api/v1/auth',
        secure=secure,
        httponly=True,
        samesite='lax',
    )
    resp.delete_cookie(
        key='csrf_token',
        path='/',
        secure=secure,
        httponly=False,
        samesite='lax',
    )
    return resp


@router.get(
    '/me',
    response_model=MeResponse,
    responses={
        401: {'description': 'Not authenticated'},
    },
)
async def me(
    current: Annotated[dict, Depends(get_current_user)],
) -> MeResponse:
    return MeResponse(
        user=_UserResponse.model_validate(current['user']),
        csrf_token=current['csrf_token'],
    )
