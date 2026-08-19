# POST /api/v1/auth/admin/roles - change a user's role (SUPERUSER only)
# 1. Signup a fresh throwaway account (unique per run) - sends the verification email
POST {{host}}/api/v1/auth/signup
accept: application/json
Content-Type: application/json
{
    "username": "hurl-{{newUuid}}",
    "email": "hurl-{{newUuid}}@questr.dev",
    "first_name": "Hurl",
    "last_name": "Roles",
    "password": "!HurlTest123",
    "password_confirmation": "!HurlTest123"
}

HTTP 201
[Captures]
account_id: jsonpath "$.id"
account_email: jsonpath "$.email"

# 2. Wait for the verification email (recipient-gated against pre-existing mail)
GET {{mailpit}}/api/v1/messages?limit=1
[Options]
retry: 20
retry-interval: 500
HTTP 200
[Asserts]
jsonpath "$.messages[0].To[0].Address" == "{{account_email}}"
[Captures]
message_id: jsonpath "$.messages[0].ID"

# 3. Capture the verification token
GET {{mailpit}}/api/v1/message/{{message_id}}
HTTP 200
[Captures]
verify_token: regex "verify-email/([A-Za-z0-9_-]+)"

# 4. Verify the throwaway account (now ACTIVE)
GET {{host}}/api/v1/auth/verify-email/{{verify_token}}
HTTP 200
[Asserts]
jsonpath "$.status" == "active"

# 5. Login as SUPERUSER
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{superuser_email}}",
    "password": "{{superuser_password}}",
    "remember_me": false
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"

# 6. Promote the throwaway to SUPERUSER (200, empty body)
POST {{host}}/api/v1/auth/admin/roles
Content-Type: application/json
X-CSRF-Token: {{csrf_token}}
{
    "target_id": "{{account_id}}",
    "new_role": "superuser"
}

HTTP 200

# 7. Login as the promoted throwaway (role change took effect)
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

# 8. Self-change rejected with self_role_change. This also proves the
#    promotion: a plain USER would fail the permission gate first with a
#    different 403, never reaching the self-guard.
POST {{host}}/api/v1/auth/admin/roles
Content-Type: application/json
X-CSRF-Token: {{csrf_token}}
{
    "target_id": "{{account_id}}",
    "new_role": "user"
}

HTTP 403
[Asserts]
jsonpath "$.error_code" == "self_role_change"

# 9. Restore: the original SUPERUSER demotes the throwaway back to USER
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{superuser_email}}",
    "password": "{{superuser_password}}",
    "remember_me": false
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"

POST {{host}}/api/v1/auth/admin/roles
Content-Type: application/json
X-CSRF-Token: {{csrf_token}}
{
    "target_id": "{{account_id}}",
    "new_role": "user"
}

HTTP 200