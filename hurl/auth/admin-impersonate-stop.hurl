# POST /api/v1/auth/admin/impersonate/stop - stop impersonation, restore the admin session
# 1. Login as the seed ACTIVE USER to discover a target_id
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{target_email}}",
    "password": "{{target_password}}",
    "remember_me": false
}

HTTP 200
[Captures]
target_id: jsonpath "$.user.id"

# 2. Login as the SUPERUSER - capture admin id + csrf token
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
admin_id: jsonpath "$.user.id"
csrf_token: cookie "csrf_token"

# 3. Start impersonation (CSRF double-submit)
POST {{host}}/api/v1/auth/admin/impersonate
Content-Type: application/json
X-CSRF-Token: {{csrf_token}}
{
    "target_id": "{{target_id}}",
    "reason": "hurl e2e stop test"
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"
session_id: cookie "session_id"

# 4. Confirm we are impersonating the target
GET {{host}}/api/v1/auth/me
HTTP 200
[Asserts]
jsonpath "$.is_impersonation" == true
jsonpath "$.user.id" == "{{target_id}}"

# 5. Stop impersonation - restores admin session, rotates CSRF.
# Explicit Cookie header overrides the jar (the jar holds two csrf_token
# cookies with different paths/values after impersonate, which confuses the
# middleware's double-submit check).
POST {{host}}/api/v1/auth/admin/impersonate/stop
Cookie: session_id={{session_id}}; csrf_token={{csrf_token}}
X-CSRF-Token: {{csrf_token}}

HTTP 200

# 6. Confirm the admin identity is restored
GET {{host}}/api/v1/auth/me
HTTP 200
[Asserts]
jsonpath "$.is_impersonation" == false
jsonpath "$.user.id" == "{{admin_id}}"