# GET /api/v1/auth/me/email/confirm/{token} - confirm an email change
#
# new_email is supplied via --variable (Makefile: per-run unique) so it is
# stable across every occurrence in this file but unique across runs, which
# avoids the email-uniqueness collision on repeat runs.
#
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

# 2. Verify the email via the Mailpit token
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

# 3. Login + request the email change
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}",
    "password": "!HurlTest123",
    "remember_me": false
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"

POST {{host}}/api/v1/auth/me/email
X-CSRF-Token: {{csrf_token}}
Content-Type: application/json
{
    "new_email": "{{new_email}}",
    "current_password": "!HurlTest123"
}

HTTP 200

# 4. Fetch the confirm email (sent to the NEW address) and capture the confirm token
GET {{mailpit}}/api/v1/search?query=to%3A%22{{new_email}}%22%20subject%3A%22Confirm%20your%20new%20Questr%20email%22
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{new_email}}"
[Captures]
confirm_message_id: jsonpath "$.messages[0].ID"

GET {{mailpit}}/api/v1/message/{{confirm_message_id}}
HTTP 200
[Captures]
confirm_token: regex "email/confirm/([A-Za-z0-9_-]+)"

# 5. Confirm via GET (token consumed on GET)
GET {{host}}/api/v1/auth/me/email/confirm/{{confirm_token}}

HTTP 200
[Asserts]
jsonpath "$.message" == "Email changed successfully"

# 6. Login with the new email succeeds
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{new_email}}",
    "password": "!HurlTest123",
    "remember_me": false
}

HTTP 200