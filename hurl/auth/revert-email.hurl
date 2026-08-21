# POST /api/v1/auth/me/email/revert - revert an email change (pre-auth, two-step POST)
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
GET {{mailpit}}/api/v1/messages?limit=1
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{account_email}}"
[Captures]
message_id: jsonpath "$.messages[0].ID"

GET {{mailpit}}/api/v1/message/{{message_id}}
HTTP 200
[Captures]
verify_token: regex "verify-email/([A-Za-z0-9_-]+)"

GET {{host}}/api/v1/auth/verify-email/{{verify_token}}
HTTP 200

# 3. Login + request + confirm the email change
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
    "new_email": "hurl-{{newUuid}}-new@questr.dev",
    "current_password": "!HurlTest123"
}

HTTP 200

GET {{mailpit}}/api/v1/messages?limit=1
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "hurl-{{newUuid}}-new@questr.dev"
[Captures]
confirm_message_id: jsonpath "$.messages[0].ID"

GET {{mailpit}}/api/v1/message/{{confirm_message_id}}
HTTP 200
[Captures]
confirm_token: regex "email/confirm/([A-Za-z0-9_-]+)"

POST {{host}}/api/v1/auth/me/email/confirm
Content-Type: application/json
{
    "token": "{{confirm_token}}"
}

HTTP 200

# 4. Fetch the OLD-address notification carrying the revert link (search Mailpit)
GET {{mailpit}}/api/v1/search?query=to%3A%22{{account_email}}%22
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{account_email}}"
[Captures]
revert_message_id: jsonpath "$.messages[0].ID"

GET {{mailpit}}/api/v1/message/{{revert_message_id}}
HTTP 200
[Captures]
revert_token: regex "email/revert/([A-Za-z0-9_-]+)"

# 5. Revert via POST (two-step: token consumed only by POST)
POST {{host}}/api/v1/auth/me/email/revert
Content-Type: application/json
{
    "token": "{{revert_token}}"
}

HTTP 200
[Asserts]
jsonpath "$.message" == "Email change reverted"

# 6. Login with the OLD email succeeds again
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}",
    "password": "!HurlTest123",
    "remember_me": false
}

HTTP 200