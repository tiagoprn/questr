# POST /api/v1/auth/me/password - change the authenticated user's password
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

# 2. Change the password (CSRF double-submit: cookie + header)
POST {{host}}/api/v1/auth/me/password
X-CSRF-Token: {{csrf_token}}
Content-Type: application/json
{
    "current_password": "{{password}}",
    "new_password": "{{new_password}}"
}

HTTP 200
[Asserts]
jsonpath "$.message" == "Password changed"

# 3. Re-login with the new password succeeds
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{email}}",
    "password": "{{new_password}}",
    "remember_me": false
}

HTTP 200
