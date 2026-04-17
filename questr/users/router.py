from fastapi import APIRouter, status

from questr.common.exceptions import UserAlreadyExistsError
from questr.users.dependencies import T_AuthService, T_ClientIP
from questr.users.schemas import (
    PasswordValidationError,
    ResendVerificationRequest,
    ResendVerificationResponse,
    SignupRequest,
    SignupResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)

router = APIRouter(prefix='/v1/auth', tags=['auth'])


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
    try:
        user = await service.signup(
            username=payload.username,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            password=payload.password,
            password_confirmation=payload.password_confirmation,
            client_ip=client_ip,
        )
    except UserAlreadyExistsError:
        raise
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
