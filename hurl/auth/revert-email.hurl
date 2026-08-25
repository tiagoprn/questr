# GET /api/v1/auth/me/email/revert/{token} - revert an email change
#
# Uses the seeded ACTIVE account tiago003 (tiago+third@gmail.com). The flow
# is idempotent: it confirms a change then reverts it, ending back at the
# original email. new_email is supplied via --variable (Makefile: per-run
# unique) so it is stable across this file but unique across runs, which
# avoids the 48h previous_email hold collision on repeat runs.
#
# 1. Login as the seeded active account. The address contains a "+", which
#    must be %2B-encoded inside Mailpit search URLs, so capture an
#    urlEncoded copy from the login response.
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}",
    "password": "{{account_password}}",
    "remember_me": false
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"
search_email: jsonpath "$.user.email" urlEncode

# 2. Request the email change (sends confirm link to new_email AND a revert
#    notification to the old address, both at request time)
POST {{host}}/api/v1/auth/me/email
X-CSRF-Token: {{csrf_token}}
Content-Type: application/json
{
    "new_email": "{{new_email}}",
    "current_password": "{{account_password}}"
}

HTTP 200

# 3. Fetch the confirm email (to the NEW address) and capture the confirm token
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

# 4. Confirm the email change
GET {{host}}/api/v1/auth/me/email/confirm/{{confirm_token}}

HTTP 200

# 5. Fetch the revert notification (sent to the OLD address at request time)
#    and capture the revert token. search_email is urlEncoded because the
#    address contains "+". messages[0] is newest-first, so it is this run's
#    notification even when prior runs left stale revert emails.
GET {{mailpit}}/api/v1/search?query=to%3A%22{{search_email}}%22%20subject%3A%22Your%20Questr%20email%20was%20changed%22
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

# 6. Revert the email change via GET
GET {{host}}/api/v1/auth/me/email/revert/{{revert_token}}

HTTP 200
[Asserts]
jsonpath "$.message" == "Email change reverted"

# 7. Login with the original email succeeds again
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}",
    "password": "{{account_password}}",
    "remember_me": false
}

HTTP 200