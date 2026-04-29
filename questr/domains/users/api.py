from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from questr.app.dependencies import T_ClientIP, get_client_ip
from questr.common.enums import UserRole, UserStatus
from questr.infrastructure.email import (
    BaseEmailService,
    get_email_service,
)
from questr.infrastructure.orm.base import get_async_session
from questr.infrastructure.rate_limiter import (
    RedisRateLimiter,
    get_rate_limiter,
)
from questr.domains.users.repository import (
    EmailVerificationRepository,
    UserRepository,
)
from questr.domains.users.service import AuthService

router = APIRouter(prefix='/v1/auth', tags=['auth'])


# ── Schemas ──────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    username: str
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


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyEmailResponse(BaseModel):
    id: UUID
    username: str
    email: str
    status: UserStatus

    model_config = {'from_attributes': True}


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResendVerificationResponse(BaseModel):
    message: str


class PasswordValidationError(BaseModel):
    errors: list[str]


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


@router.post(
    '/verify-email',
    response_model=VerifyEmailResponse,
    responses={
        400: {'description': 'Invalid or expired token'},
    },
)
async def verify_email(
    payload: VerifyEmailRequest,
    service: T_AuthService,
) -> VerifyEmailResponse:
    user = await service.verify_email(payload.token)
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
    await service.resend_verification(
        email=payload.email, client_ip=client_ip
    )
    return ResendVerificationResponse(
        message='If an account with this email exists, '
        'a new verification email has been sent.'
    )
