# Hurl — API Integration Testing

This directory contains HTTP request scenarios using [Hurl](https://hurl.dev), a command-line tool that runs HTTP requests defined in a plain-text format.

## What is Hurl

[Hurl](https://hurl.dev) is an HTTP client and testing tool that lets you define API requests and expected responses in a simple text format. It supports:

- Templating via variable files (`.vars`)
- Assertions on status codes, response headers, and body
- Chaining multiple requests in a single file
- Test reporting

In this project, Hurl is used to create development seed data by calling the API endpoints.

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
