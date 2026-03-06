# User Login Use Case

## Description
Allows an existing user to authenticate and receive access tokens for API requests.

## Preconditions
- User must have an active account (created via Signup Use Case)
- User must have valid credentials (username/email and password)

## Postconditions
- User receives a valid access token
- User receives a valid refresh token
- User session is recorded in the system

## Steps

### 1. Validate Input
The system receives the user's credentials:
- `username` or `email` (required, string)
- `password` (required, string)

Validate that both fields are provided and non-empty.

### 2. Retrieve User
The service queries the user repository to find the user by username or email.

**Error Handling:**
- If user is not found → Return "Invalid credentials" error
- If multiple matches found → Return "Invalid credentials" error

### 3. Verify Password
The system verifies the provided password against the stored hashed password.

**Technical Requirement (per <<https://fastapidozero.dunossauro.com/estavel/06/>>):**
- Passwords must be hashed using `pwdlib[argon2]` algorithm
- Never store plaintext passwords

**Error Handling:**
- If password does not match → Return "Invalid credentials" error

### 4. Generate Access Token
The system generates a JWT access token.

**Token Specifications:**
- Token validity: **7 days** (168 hours)
- Token should contain: user_id, username, expiration timestamp
- Token must be signed with SECRET_KEY from settings

### 5. Generate Refresh Token
The system generates a refresh token.

**Token Specifications:**
- Token validity: **1 hour**
- Purpose: Used to obtain new access tokens without re-authentication
- Token should contain: user_id, token type identifier, expiration timestamp

**Technical Note (per ARCHITECTURE.md):**
- The refresh token mechanism keeps the user logged in while the access token is still valid
- See <https://coderslegacy.com/pyjwt-tutorial-token-authentication-in-python/> for implementation details on refresh token flow (Section "Refreshing JWT Tokens")

### 6. Return Response
The system returns the authentication response:

```json
{
  "access_token": "<jwt_token>",
  "refresh_token": "<refresh_token>",
  "token_type": "Bearer",
  "expires_in": 604800
}
```

## Error Responses

| Status Code | Condition |
|-------------|-----------|
| 400 | Missing username/email or password |
| 401 | Invalid credentials |

## Related Documentation
- <<https://fastapidozero.dunossauro.com/estavel/06/>>: Password hashing with pwdlib/argon2
- <https://coderslegacy.com/pyjwt-tutorial-token-authentication-in-python/>: Access token and refresh token implementation
- ARCHITECTURE.md: Service layer (UserService), Repository layer (UserRepository)
- ARCHITECTURE.md: Settings for SECRET_KEY configuration
