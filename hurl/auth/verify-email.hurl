# GET /api/v1/auth/verify-email/{token} - full email verification journey
# 1. Signup a fresh account (unique per run) - signup sends the verification email
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

# 2. Wait for the verification email for our account to land in Mailpit (retry while absent)
GET {{mailpit}}/api/v1/messages?limit=1
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{account_email}}"
[Captures]
message_id: jsonpath "$.messages[0].ID"

# 3. Fetch the message body and capture the verification token (hurl regex needs a capture group)
GET {{mailpit}}/api/v1/message/{{message_id}}
HTTP 200
[Captures]
verify_token: regex "verify-email/([A-Za-z0-9_-]+)"

# 4. Verify the email address
GET {{host}}/api/v1/auth/verify-email/{{verify_token}}
HTTP 200
[Asserts]
jsonpath "$.status" == "active"

# 5. Login now succeeds for the verified account
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{account_email}}",
    "password": "!HurlTest123",
    "remember_me": false
}
HTTP 200