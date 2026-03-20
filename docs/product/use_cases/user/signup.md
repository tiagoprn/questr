# User Signup Use Case

## Description
Allows a new user to create an account in the Questr application.

## Data Structures

### UserStatus Enum
```python
class UserStatus(str, Enum):
    PENDING = "pending"      # Email not verified, cannot authenticate
    ACTIVE = "active"       # Email verified, can authenticate
    SUSPENDED = "suspended" # Temporarily disabled by admin
    BANNED = "banned"       # Permanently disabled
```

## Preconditions
- None (this is the first step for new users)

## Postconditions
- New user account is created in the database
- Password is securely hashed
- User record is created with `status` set to `PENDING`
- User must verify email before authentication is permitted

## Steps

### 1. Validate Input
The system receives the user's registration data:
- `username` (required, string, 5-50 characters)
- `email` (required, valid email format)
- `password` (required, minimum 8 characters)
- `password_confirmation` (required, must match `password`)

**Validation Rules:**
- Username must be unique
- Username must be 5 to 50 characters in length
- Email must be unique
- Email must be valid format (see ARCHITECTURE.md: Email value object)
- Password must meet the following requirements:
  - At least 8 characters in length
  - At least 1 uppercase letter
  - At least 1 lowercase letter
  - At least 1 number
  - At least 1 special character (e.g., !@#$%^&*(),.?":{}|<>)
- `password_confirmation` must match `password`

### 2. Check Existing User
The service queries the user repository to check if username or email already exists.

**Error Handling:**
- If username already exists → Return "Username already taken" error
- If email already exists → Return "Email already registered" error

### 3. Hash Password
The system securely hashes the user's password before storing.

**Technical Requirement:**
- Must use `pwdlib[argon2]` for password hashing
- Never store plaintext passwords
- This is a mandatory security requirement

### 4. Create User Record
The domain layer creates a new User entity:

```python
# Generate unique user ID - UUIDv7 for time-ordered uniqueness
id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)

# Store username (normalized/trimmed)
username: Mapped[str] = mapped_column(String(50), unique=True)

# Store email (lowercase, normalized)
email: Mapped[str] = mapped_column(String(255), unique=True)

# Store hashed password (never plaintext)
password_hash: Mapped[str] = mapped_column(String(255))

# Store role (enum: user, superuser). Default role for new signups is "user"
role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)

# Store status. Default is PENDING until email is verified
# This controls authentication eligibility: only ACTIVE users can log in
status: Mapped[UserStatus] = mapped_column(
    Enum(UserStatus),
    default=UserStatus.PENDING  # Email verification required
)
```

**Architecture Note (per ARCHITECTURE.md):**
- Domain layer handles the User entity creation
- Repository layer handles persistence to database
- Service layer orchestrates the operation

### 5. Send Verification Email
The system sends a verification email to the user's email address containing a confirmation link.

**Email Requirements:**
- Email must contain a unique confirmation token/link
- Token must expire after a defined period (e.g., 24 hours)
- Link must direct user to a confirmation endpoint with token

### 6. Return Response
The system returns the created user data (excluding sensitive information):

```json
{
  "id": "0195f3a2-1c7b-7e4d-a3b2-1d4e5f6a7b8c",
  "username": "newuser",
  "email": "user@example.com",
  "created_at": "2026-03-20T16:07:39Z"
}
```

**Technical Implementation Note:** The `created_at` field must not be persisted in the database. Instead, it must be derived from the UUIDv7 timestamp. Example: `dt.datetime.fromtimestamp(u.time / 1000)`.

**Note:** Password is NOT returned in the response.

## Error Responses

| Status Code | Condition |
|-------------|-----------|
| 400 | Missing required fields |
| 400 | Invalid email format |
| 400 | Password does not meet requirements |
| 400 | Password and password confirmation do not match |
| 400 | Username must be between 5 and 50 characters |
| 409 | Username already exists |
| 409 | Email already registered |

## Post-Signup Behavior
- User receives a verification email with a confirmation link
- User must click the confirmation link to verify their email and set `status` to `ACTIVE`
- User must use the **Login Use Case** to authenticate (only after email verification)
- User can then access protected resources and use core features (backlog management, game tracking, etc.)

## Email Verification
- Upon successful signup, `status` is set to `PENDING` in the database
- A verification email is sent with a unique token/link
- When the user clicks the link, the token is validated and `status` is set to `ACTIVE`
- The Login Use Case must check `status` and reject authentication for users with status other than `ACTIVE`

## Related Documentation
- README.md: Questr application purpose and features
- <https://fastapidozero.dunossauro.com/estavel/06/>: Password hashing with pwdlib[argon2]
- ARCHITECTURE.md: Email value object for validation
- ARCHITECTURE.md: Domain layer (User entity), Repository layer, Service layer
- ARCHITECTURE.md: Schemas for request/response validation
