from uuid import UUID

from pydantic import BaseModel, EmailStr

from questr.common.enums import UserRole, UserStatus


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
