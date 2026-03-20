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

### User Entity
```python
class User(Base):
    __tablename__ = "users"

    # Primary key - UUIDv7 for time-ordered uniqueness
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)

    # Username (trim whitespace, lowercase, remove special chars except underscores and hyphens)
    # Non-ASCII characters (e.g., ö, ñ, ü) are converted to ASCII equivalents
    # Example: "  Jöhn_Doe123 " → "john_doe123"
    username: Mapped[str] = mapped_column(String(50), unique=True)

    # Email - validated via Pydantic EmailStr (handles format, DNS, etc.)
    email: Mapped[str] = mapped_column(String(255), unique=True)

    # Hashed password (never plaintext). Argon2 hashes are ~512+ chars
    password_hash: Mapped[str] = mapped_column(String(1024))

    # Role enum. Default role for new signups is "user"
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)

    # Status. Default is PENDING until email is verified.
    # This controls authentication eligibility: only ACTIVE users can log in.
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus),
        default=UserStatus.PENDING
    )

    # Relationship to email verification record
    email_verification: Mapped["EmailVerification | None"] = relationship(
        "EmailVerification",
        back_populates="user",
        uselist=False
    )
```

### EmailVerification Table
```python
class EmailVerification(Base):
    __tablename__ = "email_verifications"

    # Primary key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)

    # Foreign key to users table
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)

    # Relationship to user
    user: Mapped["User"] = relationship("User", back_populates="email_verification")

    # Token hash (SHA-256 hex = 64 characters)
    token_hash: Mapped[str] = mapped_column(String(64))

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
- `username` (required, string, 5-50 characters after normalization)
- `email` (required, valid email format via Pydantic EmailStr)
- `password` (required, minimum 8 characters)
- `password_confirmation` (required, must match `password`)

**Validation Rules:**
- Username must be unique
- Username must be 5 to 50 characters in length (length check is performed after normalization)
- Username normalization: trim whitespace, lowercase, remove special characters except underscores and hyphens, convert non-ASCII characters to ASCII equivalents
- Email must be unique
- Email must be valid format (validated via Pydantic EmailStr)
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
The domain layer creates a new User entity (see User Entity data structure above).

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
| 400 | Email does not match the provided username |
| 400 | Invalid verification link |
| 400 | Verification link has expired |
| 400 | Link has already been used |
| 403 | Account is suspended or banned |
| 404 | User not found or already verified |
| 409 | Username already exists |
| 409 | Email already registered |
| 429 | Too many requests, please try again later |
| 500 | Failed to send verification email |

## Post-Signup Behavior
- User receives a verification email with a confirmation link
- User must click the confirmation link to verify their email and set `status` to `ACTIVE`
- User must use the **Login Use Case** to authenticate (only after email verification)
- User can then access protected resources and use core features (backlog management, game tracking, etc.)

## Email Verification Flow
1. User clicks link in email → sends POST to `/api/v1/auth/verify-email` with token
2. System hashes the incoming token using SHA-256, then looks up the hash in the database
3. **Validation Checks:**
   - If token hash not found → Return 400 "Invalid verification link"
   - If token is expired (`datetime.now(timezone.utc) > expires_at`) → Return 400 "Verification link has expired"
   - If token already used (`used_at` is not null) → Return 400 "Link has already been used"
4. System marks token as used: `used_at = datetime.now(timezone.utc)`
5. **Account Status Check:**
   - If user `status` is `SUSPENDED` or `BANNED` → Return 403 "Account is suspended or banned"
6. System updates user `status` to `ACTIVE`
7. System returns success response:
   ```json
   {
     "message": "Email verified successfully",
     "redirect_url": "/login?verified=true"
   }
   ```
8. User can now authenticate via Login Use Case

## Resend Verification Email
If the user does not receive the verification email or the link has expired, they can request a new one.

**Endpoint:** `POST /api/v1/auth/resend-verification`

**Request Body:**
```json
{
  "username": "newuser",
  "email": "user@example.com"
}
```

**Validation:**
- User is looked up by username first, then email is verified against that user
- If username does not exist → Return 404 "User not found or already verified"
- If username exists but email does not match → Return 400 "Email does not match the provided username"
- User's `status` must be `PENDING` (not already `ACTIVE`)
- If user is already `ACTIVE` → Return 404 "User not found or already verified"
- If user `status` is `SUSPENDED` or `BANNED` → Return 403 "Account is suspended or banned"

**Rate Limiting:** Maximum 3 resend requests per hour per IP address. If exceeded → Return 429 "Too many requests, please try again later"

**Behavior:**
1. Delete any existing verification tokens for this user (both expired and unexpired)
2. Generate a new verification token
3. Send new verification email
4. Return success response:
   ```json
   { "message": "Verification email sent successfully" }
   ```

**Security Note:** The same error message is returned for "user not found" and "already verified" to prevent user enumeration attacks.

## Related Documentation
- README.md: Questr application purpose and features
- <https://fastapidozero.dunossauro.com/estavel/06/>: Password hashing with pwdlib[argon2]
- ARCHITECTURE.md: Email value object for validation
- ARCHITECTURE.md: Domain layer (User entity), Repository layer, Service layer
- ARCHITECTURE.md: Schemas for request/response validation
