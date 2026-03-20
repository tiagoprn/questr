# User Signup Use Case

## Description
Allows a new user to create an account in the Questr application.

## Data Structures

### UserRole Enum
```python
class UserRole(str, Enum):
    USER = "user"       # Standard user
    SUPERUSER = "superuser"  # Admin privileges
```

### UserStatus Enum
```python
class UserStatus(str, Enum):
    PENDING = "pending"      # Email not verified, cannot authenticate
    ACTIVE = "active"       # Email verified, can authenticate
    SUSPENDED = "suspended" # Temporarily disabled by admin
    BANNED = "banned"       # Permanently disabled
```

### EmailVerification Table
```python
class EmailVerification(Base):
    __tablename__ = "email_verifications"

    # Primary key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)

    # Foreign key to users table
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)

    # Token (hashed before storage for security)
    token_hash: Mapped[str] = mapped_column(String(128))

    # Expiration timestamp
    expires_at: Mapped[datetime]

    # Set when token is consumed (null until used)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

## Preconditions
- None (this is the first step for new users)

## Postconditions
- New user account is created in the database
- Password is securely hashed
- User record is created with `status` set to `PENDING`
- Verification token is generated and stored
- Verification email is sent (or queued for retry on failure)
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

# Store username (trim whitespace, lowercase, remove special chars except underscores and hyphens)
# Example: "  Jöhn_Doe123 " → "john_doe123"
username: Mapped[str] = mapped_column(String(50), unique=True)

# Store email (trim whitespace, lowercase, strip leading/trailing dots for Gmail compatibility)
# Example: "John.Doe@gmail.com" → "john.doe@gmail.com"
email: Mapped[str] = mapped_column(String(255), unique=True)

# Store hashed password (never plaintext). Argon2 hashes are ~512+ chars
password_hash: Mapped[str] = mapped_column(String(1024))

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

### 5. Create Verification Token
The system generates a unique verification token and stores it in the database:

```python
# Generate cryptographically secure random token (32 bytes, URL-safe base64)
token: str = secrets.token_urlsafe(32)

# Store token hash (never store raw token)
token_hash: str = hashlib.sha256(token.encode()).hexdigest()

# Set expiration (24 hours from creation)
expires_at: datetime = datetime.now(timezone.utc) + timedelta(hours=24)

# Create EmailVerification record linked to user
email_verification: EmailVerification = EmailVerification(
    user_id=user.id,
    token_hash=token_hash,
    expires_at=expires_at
)
```

### 6. Send Verification Email
The system sends a verification email to the user's email address containing a confirmation link.

**Email Requirements:**
- Email must contain a unique confirmation link
- Link format: `POST /api/v1/auth/verify-email`
- Token passed as JSON body: `{ "token": "<raw_token>" }`
- Token expires after 24 hours
- Link is valid for single use only

**Error Handling:**
- If email fails to send → Log error, return 500 with message "Failed to send verification email"
- Do NOT roll back user creation on email failure
- Consider async email queue for production resilience

### 7. Return Response
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
| 500 | Failed to send verification email |

## Post-Signup Behavior
- User receives a verification email with a confirmation link
- User must click the confirmation link to verify their email and set `status` to `ACTIVE`
- User must use the **Login Use Case** to authenticate (only after email verification)
- User can then access protected resources and use core features (backlog management, game tracking, etc.)

## Email Verification Flow
1. User clicks link in email → sends POST to `/api/v1/auth/verify-email` with token
2. System looks up token by hash
3. **Error Handling for Invalid/Expired/Used Token:**
   - If token not found → Return 400 "Invalid verification link"
   - If token is expired → Return 400 "Verification link has expired"
   - If token already used (`used_at` is not null) → Return 400 "Link has already been used"
4. System marks token as used: `used_at = now()`
5. System updates user `status` to `ACTIVE`
6. System returns success response
7. User can now authenticate via Login Use Case

## Related Documentation
- README.md: Questr application purpose and features
- <https://fastapidozero.dunossauro.com/estavel/06/>: Password hashing with pwdlib[argon2]
- ARCHITECTURE.md: Email value object for validation
- ARCHITECTURE.md: Domain layer (User entity), Repository layer, Service layer
- ARCHITECTURE.md: Schemas for request/response validation
