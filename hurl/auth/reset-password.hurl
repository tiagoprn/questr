# POST /api/v1/auth/reset-password - full password reset journey
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

# 2. Request a password reset
POST {{host}}/api/v1/auth/forgot-password
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}"
}

HTTP 200

# 3. Wait for the reset email to land in Mailpit
GET {{mailpit}}/api/v1/messages?limit=1
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{account_email}}"
[Captures]
message_id: jsonpath "$.messages[0].ID"

# 4. Fetch the message body and capture the reset token
GET {{mailpit}}/api/v1/message/{{message_id}}
HTTP 200
[Captures]
reset_token: regex "reset-password#token=([A-Za-z0-9_-]+)"

# 5. Reset the password with the single-use token
POST {{host}}/api/v1/auth/reset-password
accept: application/json
Content-Type: application/json
{
    "token": "{{reset_token}}",
    "new_password": "!HurlTest456"
}

HTTP 200
[Asserts]
jsonpath "$.message" == "Password reset successfully"

# 6. Re-login with the new password succeeds
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}",
    "password": "!HurlTest456",
    "remember_me": false
}

HTTP 200
