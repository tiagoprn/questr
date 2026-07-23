# 1. Login -- establishes the session
POST {{host}}/api/v1/auth/login
accept: application/json
Content-Type: application/json
{
    "email": "{{email}}",
    "password": "{{password}}",
    "remember_me": {{remember_me}}
}

HTTP 200
[Captures]
csrf_token: cookie "csrf_token"

# 2. Verify session is functional via /me
GET {{host}}/api/v1/auth/me

HTTP 200

# 3. Logout -- invalidates the session (CSRF double-submit: cookie + header)
POST {{host}}/api/v1/auth/logout
X-CSRF-Token: {{csrf_token}}

HTTP 200

# 4. Post-logout /me -- session should be invalidated (401)
GET {{host}}/api/v1/auth/me

HTTP 401
