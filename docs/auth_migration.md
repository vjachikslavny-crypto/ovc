# Username-Based Auth Migration

## ✅ Completed Changes

### 1. Database Schema
- **Added to `users` table:**
  - `username` VARCHAR UNIQUE NOT NULL (indexed)
  - `failed_login_count` INTEGER DEFAULT 0
  - `locked_until` DATETIME NULL
- **Modified:**
  - `email` now NULLABLE (optional field)
- **Removed:**
  - `email_verified_at` (no longer needed)

### 2. Backend API Changes

#### New Endpoints
- `GET /auth/username-available?u=<username>` - Check username availability
- `POST /auth/change-password` - Change password for authenticated user

#### Modified Endpoints
- `POST /auth/register` - Now requires `username`, `password`; `email` is optional
- `POST /auth/login` - Now accepts `identifier` (username OR email) + `password`

#### Removed Endpoints
- `GET /auth/verify` - Email verification
- `GET /forgot` - Forgot password page
- `POST /auth/forgot` - Forgot password request
- `POST /auth/reset` - Reset password
- `GET /reset` - Reset password page

### 3. Security Features

#### Username Validation
- Pattern: `^[a-zA-Z0-9._-]{3,24}$`
- Forbidden: `admin`, `root`, `system`, `api`, `auth`, `login`, `register`, `logout`, `me`
- Case-insensitive uniqueness check

#### Account Lockout
- **Trigger:** 10 failed login attempts
- **Duration:** 15 minutes
- **Storage:** DB-based (`failed_login_count`, `locked_until`)
- **Reset:** On successful login

#### Password Policy
- Minimum 8 characters
- Requires 3 of 4 classes: uppercase, lowercase, digits, symbols
- Common password blacklist

### 4. Frontend Changes

#### Updated Templates
- `auth/register.html` - Username input with real-time availability check
- `auth/login.html` - Single identifier field (username or email)
- `auth/change-password.html` - New page for password change

#### Removed Templates
- `auth/forgot.html`
- `auth/reset.html`
- `auth/verify_sent.html`

#### Navigation
- User display now shows `username` instead of `email`
- Added "Пароль" link to change password

### 5. Migration Strategy

For existing users with email-only accounts:
```sql
UPDATE users 
SET username = REPLACE(LOWER(SUBSTR(email, 1, INSTR(email, '@') - 1)), '.', '_')
WHERE username IS NULL
```

Example: `user@example.com` → username: `user`

**Note:** If collisions occur (e.g., `user@a.com` and `user@b.com`), manual intervention required.

## 🔒 Security Improvements

1. **Brute Force Protection:**
   - Rate limiting: 10 requests/min per IP
   - Account lockout after 10 failed attempts
   - DB-persisted counters (survives restarts)

2. **Session Management:**
   - Access token: 15 minutes (JWT)
   - Refresh token: 30 days (HttpOnly cookie)
   - Token rotation with reuse detection
   - CSRF protection

3. **Password Security:**
   - Argon2id hashing
   - Configurable policy
   - Change password revokes all sessions

## 📝 API Examples

### Register
```bash
POST /auth/register
Content-Type: application/json

{
  "username": "john_doe",
  "password": "SecurePass123!",
  "email": "john@example.com"  # optional
}
```

### Login
```bash
POST /auth/login
Content-Type: application/json

{
  "identifier": "john_doe",  # or "john@example.com"
  "password": "SecurePass123!"
}
```

### Check Username
```bash
GET /auth/username-available?u=john_doe

Response:
{
  "available": false
}
```

### Change Password
```bash
POST /auth/change-password
Content-Type: application/json
X-CSRF-Token: <token>
Authorization: Bearer <access_token>

{
  "old_password": "SecurePass123!",
  "new_password": "NewSecurePass456!"
}
```

## 🚀 Testing Checklist

- [x] Register with username only
- [x] Register with username + email
- [x] Login with username
- [x] Login with email (if provided)
- [x] Username availability check (real-time)
- [x] Account lockout after 10 failures
- [x] Lockout auto-expires after 15 minutes
- [x] Change password works
- [x] Change password revokes all sessions
- [x] Duplicate username rejected (409)
- [x] Duplicate email rejected (409)
- [x] Invalid username format rejected (400)
- [x] Weak password rejected (400)
- [x] CSRF protection works
- [x] Rate limiting works

## 🔄 Rollback Plan

If issues arise:

1. **Database:** Keep old `email` column (still present, just nullable)
2. **Code:** Git revert to previous commit
3. **Data:** Username can be regenerated from email if needed

## 📚 Future Enhancements

Modular design allows easy addition of:
- Email verification (optional)
- 2FA/TOTP
- OAuth providers (Google, GitHub, etc.)
- Password reset via email (if email provided)
- Username change (with cooldown period)

## ⚠️ Known Limitations

1. **SQLite:** Cannot modify column constraints directly (email still has UNIQUE constraint in schema, but app treats as nullable)
2. **Username Collisions:** Manual resolution needed if multiple users had same email prefix
3. **No Email Recovery:** Users without email cannot recover account if password forgotten
4. **Case Sensitivity:** SQLite is case-insensitive by default for ASCII, but explicit LOWER() used for safety

## 🛠️ Configuration

See `.env.example` for all available settings:
- `SECRET_KEY` - **MUST** be changed in production (min 32 chars)
- `PASSWORD_MIN_LENGTH` - Default: 8
- `ACCESS_TOKEN_EXPIRES_MIN` - Default: 15
- `REFRESH_TOKEN_EXPIRES_DAYS` - Default: 30
- `COOKIE_SECURE` - Set to `true` in production (HTTPS)
- `COOKIE_SAMESITE` - `strict` or `lax` (default)

## 📞 Support

For issues or questions, check:
1. Console logs (browser & server)
2. Audit logs in database (`audit_logs` table)
3. Failed login counters (`users.failed_login_count`)

