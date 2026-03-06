# User Signup Use Case

## Description
Allows a new user to create an account in the Questr application.

## Preconditions
- None (this is the first step for new users)

## Postconditions
- New user account is created in the database
- Password is securely hashed
- User can authenticate via the Login Use Case

## Steps

### 1. Validate Input
The system receives the user's registration data:
- `username` (required, string, 3-50 characters)
- `email` (required, valid email format)
- `password` (required, minimum 8 characters)

**Validation Rules:**
- Username must be unique
- Email must be unique
- Email must be valid format (see ARCHITECTURE.md: Email value object)
- Password must meet minimum strength requirements

### 2. Check Existing User
The service queries the user repository to check if username or email already exists.

**Error Handling:**
- If username already exists → Return "Username already taken" error
- If email already exists → Return "Email already registered" error

### 3. Hash Password
The system securely hashes the user's password before storing.

**Technical Requirement (per TODO.md):**
- Must use `pwdlib[argon2]` for password hashing
- Never store plaintext passwords
- This is a mandatory security requirement

### 4. Create User Record
The domain layer creates a new User entity:
- Generate unique user ID
- Store username (normalized/trimmed)
- Store email (lowercase, normalized)
- Store hashed password
- Set created_at timestamp

**Architecture Note (per ARCHITECTURE.md):**
- Domain layer handles the User entity creation
- Repository layer handles persistence to database
- Service layer orchestrates the operation

### 5. Return Response
The system returns the created user data (excluding sensitive information):

```json
{
  "id": 123,
  "username": "newuser",
  "email": "user@example.com",
  "created_at": "2026-03-06T10:00:00Z"
}
```

**Note:** Password is NOT returned in the response.

## Error Responses

| Status Code | Condition |
|-------------|-----------|
| 400 | Missing required fields |
| 400 | Invalid email format |
| 400 | Password does not meet requirements |
| 409 | Username already exists |
| 409 | Email already registered |

## Post-Signup Behavior
- User must use the **Login Use Case** to authenticate
- User can then access protected resources and use core features (backlog management, game tracking, etc.)

## Related Documentation
- README.md: Questr application purpose and features
- <https://fastapidozero.dunossauro.com/estavel/06/>: Password hashing with pwdlib[argon2]
- ARCHITECTURE.md: Email value object for validation
- ARCHITECTURE.md: Domain layer (User entity), Repository layer, Service layer
- ARCHITECTURE.md: Schemas for request/response validation
