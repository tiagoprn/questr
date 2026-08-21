# POST /api/v1/auth/forgot-password - request a password reset (uniform 200)
# 1. Signup a fresh account (unique per run)
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

# 2. Request a password reset - uniform 200 regardless of account state
POST {{host}}/api/v1/auth/forgot-password
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}"
}

HTTP 200
[Asserts]
jsonpath "$.message" == "If an account with this email exists, a password reset link has been sent."
