# POST /api/v1/auth/logout-all - revoke all active sessions for the current user
# 1. Login as a seeded, email-verified user
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{email}}",
    "password": "{{password}}",
    "remember_me": false
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"

# 2. Revoke all sessions (CSRF double-submit: cookie + header)
POST {{host}}/api/v1/auth/logout-all
X-CSRF-Token: {{csrf_token}}

HTTP 200
[Asserts]
jsonpath "$.message" == "All sessions revoked"
jsonpath "$.sessions_revoked" >= 1

# 3. Session is gone - /me returns 401
GET {{host}}/api/v1/auth/me
HTTP 401