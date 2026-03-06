# User Logout Use Case

## Description
Allows an authenticated user to end their session by invalidating their tokens.

## Preconditions
- User must be currently authenticated (valid access token)
- User must have an active session in the system

## Postconditions
- Access token is invalidated
- Refresh token is invalidated
- User cannot use either token for subsequent API requests

## Steps

### 1. Verify Authentication
The system verifies the user's current access token via the authentication middleware.

**Error Handling:**
- If no valid access token provided → Return 401 Unauthorized
- If token is expired → Return 401 Unauthorized

### 2. Identify User Session
The system extracts the user_id from the access token to identify which session to terminate.

### 3. Invalidate Tokens

**Access Token Invalidation:**
- Option A: Add token to a blacklist in the database with expiration time
- Option B: Implement token version/sequence number per user (invalidate all tokens when logout)

**Refresh Token Invalidation:**
- Invalidate the refresh token associated with the session
- Remove or mark as used in the database

**Technical Note (per ARCHITECTURE.md):**
- Consider using background tasks for cleanup operations if token cleanup is expensive

### 4. Return Confirmation
The system returns a success response:

```json
{
  "message": "Successfully logged out",
  "user_id": 123
}
```

## Error Responses

| Status Code | Condition |
|-------------|-----------|
| 401 | No valid access token provided |
| 401 | Token is expired or already invalidated |

## Post-Logout Behavior
- User must re-authenticate via the **Login Use Case** to access protected resources
- All associated tokens are permanently invalid

## Related Documentation
- ARCHITECTURE.md: Service layer (UserService), Dependency injection for get_current_user
- ARCHITECTURE.md: Background tasks for cleanup operations
- <https://coderslegacy.com/pyjwt-tutorial-token-authentication-in-python/> and <<https://fastapidozero.dunossauro.com/estavel/06/>>: Token implementation details
