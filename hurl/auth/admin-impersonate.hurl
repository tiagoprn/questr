# POST /api/v1/auth/admin/impersonate - start impersonation as a target user
# 1. Login as the seed ACTIVE USER to discover a target_id (no user-list endpoint)
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
csrf_token: cookie "csrf_token"

# 1b. Logout the target user (free the session before switching to the superuser)
POST {{host}}/api/v1/auth/logout
X-CSRF-Token: {{csrf_token}}

HTTP 200

# 2. Login as the SUPERUSER (replaces the session cookie)
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

# 3. Impersonate the target (CSRF double-submit: cookie + header)
POST {{host}}/api/v1/auth/admin/impersonate
Content-Type: application/json
X-CSRF-Token: {{csrf_token}}
{
    "target_id": "{{target_id}}",
    "reason": "hurl e2e test"
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"
session_id: cookie "session_id"

# 4. Confirm the session is now the impersonated target
GET {{host}}/api/v1/auth/me

HTTP 200
[Asserts]
jsonpath "$.is_impersonation" == true
jsonpath "$.user.id" == "{{target_id}}"

# 5. Stop impersonation - restore the admin session (explicit Cookie; the
#    jar holds two csrf_token cookies with different paths after impersonate)
POST {{host}}/api/v1/auth/admin/impersonate/stop
Cookie: session_id={{session_id}}; csrf_token={{csrf_token}}
X-CSRF-Token: {{csrf_token}}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"
session_id: cookie "session_id"

# 6. Logout the admin session (cleanup - avoids accumulating toward the
#    10-concurrent-session cap on repeated runs)
POST {{host}}/api/v1/auth/logout
Cookie: session_id={{session_id}}; csrf_token={{csrf_token}}
X-CSRF-Token: {{csrf_token}}

HTTP 200