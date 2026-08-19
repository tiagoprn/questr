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

# 4. Confirm the session is now the impersonated target
GET {{host}}/api/v1/auth/me

HTTP 200
[Asserts]
jsonpath "$.is_impersonation" == true
jsonpath "$.user.id" == "{{target_id}}"