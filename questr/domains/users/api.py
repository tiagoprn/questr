from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from questr.app.dependencies import T_ClientIP
from questr.common.enums import UserRole, UserStatus
from questr.common.exceptions import AuthenticationError
from questr.common.permissions import Permission, require_permission
from questr.domains.users.repository import (
    AuditLogRepository,
    EmailChangeRepository,
    EmailVerificationRepository,
    PasswordResetTokenRepository,
    SessionRepository,
    UserRepository,
)
from questr.domains.users.service import (
    AccountService,
    RoleService,
    SessionService,
)
from questr.infrastructure.dual_rate_limiter import (
    DualRateLimiter,
    get_dual_rate_limiter,
    get_dual_rate_limiter_email_change,
)
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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResetPasswordResponse(BaseModel):
    message: str


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class ChangeEmailResponse(BaseModel):
    message: str


class ConfirmEmailChangeResponse(BaseModel):
    message: str


class RevertEmailChangeResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class _UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
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


class ImpersonateRequest(BaseModel):
    target_id: UUID
    reason: str | None = None


class ChangeRoleRequest(BaseModel):
    target_id: UUID
    new_role: UserRole


class MeResponse(BaseModel):
    user: _UserResponse
    csrf_token: str
    is_impersonation: bool = False
    impersonator_session_id: str | None = None


# ── Dependencies ──────────────────────────────────────────────────────


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRepository:
    return UserRepository(session)


async def get_verification_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EmailVerificationRepository:
    return EmailVerificationRepository(session)


async def get_password_reset_token_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PasswordResetTokenRepository:
    return PasswordResetTokenRepository(session)


async def get_email_change_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EmailChangeRepository:
    return EmailChangeRepository(session)


async def get_account_service(  # noqa: PLR0913,PLR0917
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    verification_repo: Annotated[
        EmailVerificationRepository,
        Depends(get_verification_repository),
    ],
    email_service: Annotated[BaseEmailService, Depends(get_email_service)],
    rate_limiter: Annotated[RedisRateLimiter, Depends(get_rate_limiter)],
    login_rate_limiter: Annotated[
        LoginRateLimiter, Depends(get_login_rate_limiter)
    ],
    password_reset_token_repo: Annotated[
        PasswordResetTokenRepository,
        Depends(get_password_reset_token_repository),
    ],
    audit_repo: Annotated[
        AuditLogRepository, Depends(get_audit_log_repository)
    ],
    dual_rate_limiter: Annotated[
        DualRateLimiter, Depends(get_dual_rate_limiter)
    ],
    email_change_rate_limiter: Annotated[
        DualRateLimiter, Depends(get_dual_rate_limiter_email_change)
    ],
    email_change_repo: Annotated[
        EmailChangeRepository, Depends(get_email_change_repository)
    ],
) -> AccountService:
    return AccountService(
        user_repo=user_repo,
        verification_repo=verification_repo,
        email_service=email_service,
        rate_limiter=rate_limiter,
        login_rate_limiter=login_rate_limiter,
        password_reset_token_repo=password_reset_token_repo,
        audit_repo=audit_repo,
        dual_rate_limiter=dual_rate_limiter,
        email_change_rate_limiter=email_change_rate_limiter,
        email_change_repo=email_change_repo,
    )


T_UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
T_VerificationRepo = Annotated[
    EmailVerificationRepository,
    Depends(get_verification_repository),
]
T_AccountService = Annotated[AccountService, Depends(get_account_service)]


async def get_session_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> SessionRepository:
    return SessionRepository(session)


T_SessionRepo = Annotated[SessionRepository, Depends(get_session_repository)]
T_LoginRateLimiter = Annotated[
    LoginRateLimiter, Depends(get_login_rate_limiter)
]


async def get_audit_log_repository(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuditLogRepository:
    return AuditLogRepository(session)


T_AuditLogRepo = Annotated[
    AuditLogRepository, Depends(get_audit_log_repository)
]


async def get_session_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    session_repo: Annotated[
        SessionRepository, Depends(get_session_repository)
    ],
    audit_repo: T_AuditLogRepo,
    login_rate_limiter: Annotated[
        LoginRateLimiter, Depends(get_login_rate_limiter)
    ],
) -> SessionService:
    return SessionService(
        user_repo=user_repo,
        session_repo=session_repo,
        audit_repo=audit_repo,
        login_rate_limiter=login_rate_limiter,
    )


T_SessionService = Annotated[SessionService, Depends(get_session_service)]


async def get_role_service(
    user_repo: T_UserRepo,
    audit_repo: T_AuditLogRepo,
) -> RoleService:
    return RoleService(
        user_repo=user_repo,
        audit_repo=audit_repo,
    )


T_RoleService = Annotated[RoleService, Depends(get_role_service)]


async def get_current_user(
    request: Request,
    session_service: T_SessionService,
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Extract session from cookie and return user + CSRF token."""
    session_id = request.cookies.get('session_id')
    if session_id is None:
        raise AuthenticationError('Not authenticated')
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise AuthenticationError('Not authenticated') from None
    try:
        principal = await session_service.validate_session(session_uuid)
    except AuthenticationError:
        # FR-005: persist the expired-session invalidation. On the
        # exception path the get_async_session teardown commit is
        # skipped (the 401 propagates through the yield point), so
        # without this commit the deactivation would be rolled back.
        await db_session.commit()
        raise
    # The CSRF token isn't stored in the service; the API layer
    # re-echoes it from the session. We rely on the cookie.
    csrf_token = request.cookies.get('csrf_token', '')
    return {
        'user': principal.user,
        'csrf_token': csrf_token,
        'is_impersonation': principal.is_impersonation,
        'impersonator_session_id': principal.impersonator_session_id,
    }


T_CurrentUser = Annotated[dict, Depends(get_current_user)]


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
    service: T_AccountService,
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
    service: T_AccountService,
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
    service: T_AccountService,
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
    request: Request,
    service: T_SessionService,
    client_ip: T_ClientIP,
) -> LoginResponse:
    result = await service.login(
        email=payload.email,
        password=payload.password,
        client_ip=client_ip,
        remember_me=payload.remember_me,
        user_agent=request.headers.get('user-agent', ''),
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
    responses={
        401: {'description': 'Not authenticated'},
    },
)
async def logout(
    request: Request,
    service: T_SessionService,
    _current: T_CurrentUser,
) -> LogoutResponse:
    # get_current_user guarantees a syntactically valid session cookie.
    session_uuid = UUID(request.cookies['session_id'])
    await service.logout(session_uuid)

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
    responses={
        401: {'description': 'Not authenticated'},
    },
)
async def logout_all(
    service: T_SessionService,
    current: T_CurrentUser,
) -> LogoutAllResponse:
    user = current['user']
    revoked = await service.logout_all(user.id)

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
    current: T_CurrentUser,
) -> MeResponse:
    return MeResponse(
        user=_UserResponse.model_validate(current['user']),
        csrf_token=current['csrf_token'],
        is_impersonation=current.get('is_impersonation', False),
        impersonator_session_id=(
            str(current['impersonator_session_id'])
            if current.get('impersonator_session_id')
            else None
        ),
    )


@router.post(
    '/me/password',
    response_model=ChangePasswordResponse,
    responses={
        400: {'description': 'Invalid current password or weak new password'},
        401: {'description': 'Not authenticated'},
    },
)
async def change_password_route(  # noqa: PLR0913,PLR0917
    payload: ChangePasswordRequest,
    current: T_CurrentUser,
    service: T_AccountService,
    session_service: T_SessionService,
    request: Request,
    client_ip: T_ClientIP,
) -> ChangePasswordResponse:
    """Change the authenticated user's password.

    Gate 5 is composed here: other sessions are revoked, the current
    session is kept and its CSRF token rotated.
    """
    user = current['user']
    user_agent = request.headers.get('user-agent', '')

    await service.change_password(
        user_id=user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        client_ip=client_ip,
        user_agent=user_agent,
    )

    current_session_id = UUID(request.cookies['session_id'])
    await session_service.logout_all(
        user.id, except_session_id=current_session_id
    )
    csrf_raw = await session_service.rotate_csrf(current_session_id)

    response = Response(
        content=ChangePasswordResponse(
            message='Password changed'
        ).model_dump_json(),
        media_type='application/json',
        status_code=200,
    )
    response.set_cookie(
        key='csrf_token',
        value=csrf_raw,
        path='/',
        secure=settings.SECURE_COOKIE,
        httponly=False,
        samesite='lax',
    )
    return response


@router.post(
    '/forgot-password',
    response_model=ForgotPasswordResponse,
    responses={
        429: {'description': 'Rate limit exceeded'},
    },
)
async def forgot_password_route(
    payload: ForgotPasswordRequest,
    service: T_AccountService,
    request: Request,
    client_ip: T_ClientIP,
) -> ForgotPasswordResponse:
    """Request a password reset. Uniform response (no enumeration)."""
    user_agent = request.headers.get('user-agent', '')
    await service.request_password_reset(
        email=payload.email,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return ForgotPasswordResponse(
        message='If an account with this email exists, '
        'a password reset link has been sent.'
    )


@router.post(
    '/reset-password',
    response_model=ResetPasswordResponse,
    responses={
        400: {'description': 'Invalid/expired token or weak password'},
    },
)
async def reset_password_route(
    payload: ResetPasswordRequest,
    service: T_AccountService,
    session_service: T_SessionService,
    request: Request,
    client_ip: T_ClientIP,
) -> ResetPasswordResponse:
    """Reset a password with a single-use token.

    Gate 5: all of the user's sessions are revoked (pre-auth route).
    """
    user_agent = request.headers.get('user-agent', '')
    user = await service.reset_password(
        token=payload.token,
        new_password=payload.new_password,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    await session_service.logout_all(user.id)
    return ResetPasswordResponse(message='Password reset successfully')


@router.post(
    '/me/email',
    response_model=ChangeEmailResponse,
    responses={
        400: {'description': 'Invalid current password or duplicate email'},
        401: {'description': 'Not authenticated'},
    },
)
async def change_email_route(
    payload: ChangeEmailRequest,
    current: T_CurrentUser,
    service: T_AccountService,
    request: Request,
    client_ip: T_ClientIP,
) -> ChangeEmailResponse:
    """Request an email change (auth required, CSRF auto-protected)."""
    user = current['user']
    user_agent = request.headers.get('user-agent', '')
    await service.request_email_change(
        user_id=user.id,
        new_email=payload.new_email,
        current_password=payload.current_password,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return ChangeEmailResponse(
        message='A confirmation link has been sent to the new email.'
    )


@router.get(
    '/me/email/confirm/{token}',
    response_model=ConfirmEmailChangeResponse,
    responses={
        400: {'description': 'Invalid or expired token'},
    },
)
async def confirm_email_change_route(
    token: str,
    service: T_AccountService,
    session_service: T_SessionService,
    request: Request,
    client_ip: T_ClientIP,
) -> ConfirmEmailChangeResponse:
    """Confirm an email change via a single-use token (mirrors verify-email).

    Interim one-step GET-consume; see SECURITY.md. Gate 5: all of the
    user's sessions are revoked.
    """
    user_agent = request.headers.get('user-agent', '')
    user = await service.confirm_email_change(
        token=token,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    await session_service.logout_all(user.id)
    return ConfirmEmailChangeResponse(message='Email changed successfully')


@router.get(
    '/me/email/revert/{token}',
    response_model=RevertEmailChangeResponse,
    responses={
        400: {'description': 'Invalid or expired token'},
    },
)
async def revert_email_change_route(
    token: str,
    service: T_AccountService,
    session_service: T_SessionService,
    request: Request,
    client_ip: T_ClientIP,
) -> RevertEmailChangeResponse:
    """Revert an email change via a single-use token (mirrors verify-email).

    Interim one-step GET-consume; see SECURITY.md. Gate 5: all of the
    user's sessions are revoked.
    """
    user_agent = request.headers.get('user-agent', '')
    user = await service.revert_email_change(
        revert_token=token,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    await session_service.logout_all(user.id)
    return RevertEmailChangeResponse(message='Email change reverted')


@router.post(
    '/admin/impersonate',
    dependencies=[Depends(require_permission(Permission.IMPERSONATE_USERS))],
    responses={
        400: {'description': 'Self impersonation'},
        403: {'description': 'Superuser target or missing permission'},
        404: {'description': 'Target user not found'},
        409: {'description': 'Target not active'},
    },
)
async def start_impersonation_route(
    payload: ImpersonateRequest,
    current: T_CurrentUser,
    user_repo: T_UserRepo,
    session_service: T_SessionService,
    request: Request,
) -> Response:
    """Start an impersonation session as the target user."""
    admin_user = current['user']
    admin_session_id = UUID(request.cookies.get('session_id', ''))

    target_user = await user_repo.get_by_id(payload.target_id)
    if target_user is None:
        from fastapi.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse(
            status_code=404,
            content={'detail': 'User not found'},
        )

    client_ip = request.client.host if request.client else '127.0.0.1'
    user_agent = request.headers.get('user-agent', '')

    result = await session_service.start_impersonation(
        admin_user=admin_user,
        admin_session_id=admin_session_id,
        target_user=target_user,
        client_ip=client_ip,
        user_agent=user_agent,
        reason=payload.reason,
    )

    session = result['session']
    response = Response(status_code=200)
    response.set_cookie(
        key='session_id',
        value=str(session.id),
        path='/api/v1/auth',
        secure=settings.SECURE_COOKIE,
        httponly=True,
        samesite='lax',
    )
    response.set_cookie(
        key='csrf_token',
        value=result['csrf_token'],
        path='/api/v1/auth',
        secure=settings.SECURE_COOKIE,
        httponly=False,
        samesite='lax',
    )
    return response


@router.post(
    '/admin/impersonate/stop',
    responses={
        401: {'description': 'Not authenticated or session expired'},
    },
)
async def stop_impersonation_route(
    current: T_CurrentUser,
    session_service: T_SessionService,
    request: Request,
) -> Response:
    """Stop impersonation and restore the admin session.

    The ``is_impersonation`` gate protects against replay (a
    non-impersonation session calling this endpoint). The service
    re-validates the linked admin session; if it expired or was
    deactivated mid-impersonation, the response degrades to a 401
    JSON error so the frontend routes to login (no 500, no session
    flip).
    """
    session_id_str = request.cookies.get('session_id')
    if session_id_str is None:
        return _unauthorized_response()

    try:
        session_uuid = UUID(session_id_str)
    except ValueError:
        return _unauthorized_response()

    try:
        result = await session_service.stop_impersonation(
            impersonation_session_id=session_uuid,
        )
    except AuthenticationError:
        return _unauthorized_response()

    admin_session_id = result['admin_session_id']
    csrf_raw = result['csrf_token']

    response = Response(status_code=200)
    response.set_cookie(
        key='session_id',
        value=str(admin_session_id),
        path='/api/v1/auth',
        secure=settings.SECURE_COOKIE,
        httponly=True,
        samesite='lax',
    )
    response.set_cookie(
        key='csrf_token',
        value=csrf_raw,
        path='/api/v1/auth',
        secure=settings.SECURE_COOKIE,
        httponly=False,
        samesite='lax',
    )
    return response


@router.post(
    '/admin/roles',
    dependencies=[Depends(require_permission(Permission.MANAGE_ROLES))],
    responses={
        403: {'description': 'Missing permission or self-change'},
        404: {'description': 'Target user not found'},
        422: {'description': 'Invalid role or target id'},
    },
)
async def change_role_route(
    payload: ChangeRoleRequest,
    current: T_CurrentUser,
    user_repo: T_UserRepo,
    role_service: T_RoleService,
    request: Request,
) -> Response:
    """Change a user's role. The actor may NOT change their own role
    (blocks self-demotion lockout).
    """
    actor = current['user']

    target = await user_repo.get_by_id(payload.target_id)
    if target is None:
        from fastapi.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse(
            status_code=404,
            content={'detail': 'User not found'},
        )

    # Guard: no self-change
    if target.id == actor.id:
        from fastapi.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse(
            status_code=403,
            content={
                'detail': 'Cannot change your own role',
                'error_code': 'self_role_change',
            },
        )

    client_ip = request.client.host if request.client else '127.0.0.1'
    user_agent = request.headers.get('user-agent', '')

    await role_service.change_role(
        actor=actor,
        target_id=payload.target_id,
        new_role=payload.new_role,
        ip=client_ip,
        user_agent=user_agent,
    )

    return Response(status_code=200)


def _unauthorized_response() -> Response:
    """Return a 401 JSON response for failed authentication."""
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    return JSONResponse(
        status_code=401,
        content={'detail': 'Not authenticated'},
    )
