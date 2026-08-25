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

# 2. Verify the email first. forgot-password on a PENDING account resends
#    the verification email (not a reset link) by design ("matrix D3"), so
#    the account must be ACTIVE before requesting a reset.
GET {{mailpit}}/api/v1/search?query=to%3A%22{{account_email}}%22%20subject%3A%22Verify%20your%20Questr%20account%22
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{account_email}}"
[Captures]
verify_message_id: jsonpath "$.messages[0].ID"

GET {{mailpit}}/api/v1/message/{{verify_message_id}}
HTTP 200
[Captures]
verify_token: regex "verify-email/([A-Za-z0-9_-]+)"

GET {{host}}/api/v1/auth/verify-email/{{verify_token}}
HTTP 200

# 3. Request a password reset (account is now ACTIVE)
POST {{host}}/api/v1/auth/forgot-password
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}"
}

HTTP 200

# 4. Wait for the reset email to land in Mailpit
GET {{mailpit}}/api/v1/search?query=to%3A%22{{account_email}}%22%20subject%3A%22Reset%20your%20Questr%20password%22
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{account_email}}"
[Captures]
reset_message_id: jsonpath "$.messages[0].ID"

# 5. Fetch the message body and capture the reset token
GET {{mailpit}}/api/v1/message/{{reset_message_id}}
HTTP 200
[Captures]
reset_token: regex "reset-password#token=([A-Za-z0-9_-]+)"

# 6. Reset the password with the single-use token
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

# 7. Re-login with the new password succeeds
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}",
    "password": "!HurlTest456",
    "remember_me": false
}

HTTP 200