# Hurl — API Integration Testing

This directory contains HTTP request scenarios using [Hurl](https://hurl.dev), a command-line tool that runs HTTP requests defined in a plain-text format.

## What is Hurl

[Hurl](https://hurl.dev) is an HTTP client and testing tool that lets you define API requests and expected responses in a simple text format. It supports:

- Templating via variable files (`.vars`)
- Assertions on status codes, response headers, and body
- Chaining multiple requests in a single file
- Test reporting

In this project, Hurl is used to exercise the API end-to-end for two purposes: creating development seed data (e.g., users via signup) and running integration flows that validate multi-step request chains (e.g., the login + /me + logout round-trip).

## How it works

Each API call is defined by two files working together:

### Hurl file (`.hurl`)

Defines the HTTP request and expected response. It uses `{{variable}}` placeholders for parameterised values.

Example — `hurl/auth/signup.hurl`:

```hurl
POST {{host}}/api/v1/auth/signup
accept: application/json
Content-Type: application/json
{
    "username": "{{username}}",
    "email": "{{email}}",
    "first_name": "{{first_name}}",
    "last_name": "{{last_name}}",
    "password": "{{password}}",
    "password_confirmation": "{{password_confirmation}}"
}

HTTP 201
```

The file sends a POST request and asserts that the response has HTTP status `201` (Created).

### Variable file (`.vars`)

Supplies the values for the placeholders. One file per user or scenario.

Example — `hurl/vars/auth/signup/user_001.vars`:

```properties
host=http://kvm-labs:8000
username=tiago002
email=tiago+second@gmail.com
first_name=tiago
last_name=lima002
password=SSelysium08!
password_confirmation=SSelysium08!
```

### Adding a new user

1. Create a new `.vars` file under `hurl/vars/auth/signup/` with a unique set of credentials.

2. Add a `@hurl` line to the `dev-hurl-create-users` target in the `Makefile`:

   ```makefile
   @hurl --very-verbose \
       --variables-file hurl/vars/auth/signup/user_00N.vars \
       hurl/auth/signup.hurl
   ```

## Makefile target: `dev-hurl-create-users`

```makefile
dev-hurl-create-users:  ## create default users through the API
                        ## (requires the dev-server up)
	@hurl --very-verbose \
	    --variables-file hurl/vars/auth/signup/user_001.vars \
	    hurl/auth/signup.hurl
	@hurl --very-verbose \
	    --variables-file hurl/vars/auth/signup/user_002.vars \
	    hurl/auth/signup.hurl
	@hurl --very-verbose \
	    --variables-file hurl/vars/auth/signup/user_003.vars \
	    hurl/auth/signup.hurl
```

### What it does

1. Makes a POST request to the signup endpoint for each user variable file.

2. Each call asserts HTTP `201` (Created) — the call fails if the backend returns an error.

3. Runs **sequentially** because each call depends on the server state.

### Prerequisites

- The development server must be running:
  ```bash
  make dev-server
  ```
- Hurl must be installed — see [hurl.dev](https://hurl.dev).

### Usage

```bash
make dev-hurl-create-users
```

## Makefile target: `dev-hurl-auth-flow`

Exercises the full authentication round-trip against the `tiago+third@gmail.com` account seeded by `dev-hurl-create-users` (see `hurl/vars/auth/signup/user_002.vars`).

### Hurl file — `hurl/auth/auth-flow.hurl`

```hurl
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
```

### Variable file — `hurl/vars/auth/flow/user_001.vars`

```properties
host=http://kvm-labs:8000
email=tiago+third@gmail.com
password=SSelysium08!
remember_me=false
```

### What it does

1. **`POST /api/v1/auth/login`** — authenticates as `tiago+third@gmail.com` and asserts HTTP `200`. The response sets two cookies: `session_id` (HttpOnly, path `/api/v1/auth`) and `csrf_token` (path `/`).

2. **`GET /api/v1/auth/me`** — sends the `session_id` cookie (forwarded automatically by hurl) and asserts HTTP `200`. This proves the session cookie is functional, not merely present.

3. **`POST /api/v1/auth/logout`** — sends the `session_id` cookie (forwarded automatically by hurl) and the `X-CSRF-Token` header (captured from the login response) and asserts HTTP `200`. The response deletes both cookies via `Set-Cookie` with `Max-Age=0`.

4. **`GET /api/v1/auth/me`** — after logout, hurl no longer has the `session_id` cookie, so the request goes out unauthenticated. The server returns HTTP `401`, which closes the validation loop: valid session -> invalidated session.

The login response sets a `csrf_token` cookie alongside the `session_id` cookie. The `CsrfMiddleware` enforces a **double-submit pattern** on state-changing requests: the `csrf_token` cookie must be accompanied by an `X-CSRF-Token` request header carrying the same value. The hurl file captures the token from the login response (`[Captures] csrf_token: cookie "csrf_token"`) and forwards it as a header on the logout request (`X-CSRF-Token: {{csrf_token}}`). The `session_id` cookie, by contrast, flows automatically via hurl's shared cookie jar — no capture needed for that one.

### Prerequisites

- The development server must be running:
  ```bash
  make dev-server
  ```
- The `tiago+third@gmail.com` account must already exist (run `make dev-hurl-create-users` first).
- Hurl must be installed — see [hurl.dev](https://hurl.dev).

### Usage

```bash
make dev-hurl-auth-flow
```
