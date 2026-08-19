# POST /api/v1/auth/resend-verification - resend for PENDING accounts (no user enumeration)
# 1. Signup a fresh account (unique per run via newUuid)
POST {{host}}/api/v1/auth/signup
accept: application/json
Content-Type: application/json
{
    "username": "hurl-{{newUuid}}",
    "email": "hurl-{{newUuid}}@questr.dev",
    "first_name": "Hurl",
    "last_name": "Test",
    "password": "!HurlTest123",
    "password_confirmation": "!HurlTest123"
}

HTTP 201
[Captures]
account_email: jsonpath "$.email"

# 2. Resend the verification email for the just-created account
POST {{host}}/api/v1/auth/resend-verification
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}"
}

HTTP 200
[Asserts]
jsonpath "$.message" == "If an account with this email exists, a new verification email has been sent."