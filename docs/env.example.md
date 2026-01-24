# Environment Configuration

Copy these settings to your `.env` file:

```bash
# OVC Environment Configuration

# ============================================================================
# Database
# ============================================================================
DATABASE_URL=sqlite:///./src/ovc.db
# For PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost:5432/ovc

# ============================================================================
# Security
# ============================================================================
SECRET_KEY=CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME  # Must be at least 32 chars

# JWT Token Settings
ACCESS_TOKEN_EXPIRES_MIN=15
REFRESH_TOKEN_EXPIRES_DAYS=30

# Cookie Settings
COOKIE_DOMAIN=
COOKIE_SECURE=false
COOKIE_SAMESITE=lax

# Rate Limiting
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_MAX=60

# Password Policy
PASSWORD_MIN_LENGTH=6
PASSWORD_REQUIRE_UPPER=false
PASSWORD_REQUIRE_LOWER=false
PASSWORD_REQUIRE_DIGIT=false
PASSWORD_REQUIRE_SYMBOL=false

# ============================================================================
# Authentication Mode
# ============================================================================
# Options: "none" | "local" | "supabase" | "both"
# - none: No authentication required (dev mode)
# - local: Local username/password auth only (default)
# - supabase: Supabase auth only
# - both: Both local and Supabase auth available
AUTH_MODE=local

# ============================================================================
# Supabase Configuration (required if AUTH_MODE is "supabase" or "both")
# ============================================================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here

# Optional Supabase settings (defaults are auto-generated from SUPABASE_URL)
# SUPABASE_ISSUER=https://your-project.supabase.co/auth/v1
# SUPABASE_JWKS_URL=https://your-project.supabase.co/auth/v1/.well-known/jwks.json
# SUPABASE_JWT_AUD=authenticated

# ============================================================================
# Email (for future use)
# ============================================================================
EMAIL_FROM=no-reply@ovc.local
EMAIL_BACKEND=mock
```

## Auth Mode Details

| Mode | Description |
|------|-------------|
| `none` | No authentication - anonymous access (development only) |
| `local` | Local username/password authentication (default) |
| `supabase` | Supabase authentication only |
| `both` | Both local and Supabase authentication available |

## Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Go to Project Settings > API
3. Copy your Project URL to `SUPABASE_URL`
4. Copy your `anon` public key to `SUPABASE_ANON_KEY`
5. Set `AUTH_MODE=supabase` or `AUTH_MODE=both`

