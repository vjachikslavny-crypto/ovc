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
PASSWORD_MIN_LENGTH=8
PASSWORD_MIN_CHARACTER_CLASSES=3
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
ALLOW_DESKTOP_DEV_FALLBACK=false

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
# Sync
# ============================================================================
SYNC_MODE=auto
SYNC_ENABLED=false
SYNC_REMOTE_BASE_URL=
SYNC_BEARER_TOKEN=
SYNC_POLL_SECONDS=15
SYNC_OUTBOX_MAX=10000
SYNC_BATCH_SIZE=100
SYNC_REQUEST_TIMEOUT_SECONDS=12
SYNC_PULL_ENABLED=true

# ============================================================================
# Runtime diagnostics / CSP
# ============================================================================
APP_ENV=development
RUNTIME_STATUS_ENABLED=true
CSP_REPORT_ONLY=false
CSP_SCRIPT_SRC_EXTRA=
CSP_STYLE_SRC_EXTRA=
CSP_CONNECT_SRC_EXTRA=
CSP_IMG_SRC_EXTRA=
CSP_FRAME_SRC_EXTRA=

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

## Password Policy

- `PASSWORD_MIN_LENGTH` (default: `8`)
- `PASSWORD_MIN_CHARACTER_CLASSES` (default: `3`) — minimum classes from:
  - uppercase
  - lowercase
  - digits
  - symbols
- Optional hard requirements:
  - `PASSWORD_REQUIRE_UPPER`
  - `PASSWORD_REQUIRE_LOWER`
  - `PASSWORD_REQUIRE_DIGIT`
  - `PASSWORD_REQUIRE_SYMBOL`

All password checks are enforced in register and change-password flows.

## Sync Mode Details

| Mode | Description |
|------|-------------|
| `off` | Remote sync disabled |
| `shared-db` | Desktop/web share one local DB, no remote sync worker |
| `remote-shell` | Remote URL configured, sync is manual via `/api/sync/trigger` |
| `remote-sync` | Background worker enabled (requires `SYNC_BEARER_TOKEN`) |
| `auto` | Derive mode from current env (`DESKTOP_MODE`, `SYNC_ENABLED`, `SYNC_REMOTE_BASE_URL`) |

## Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Go to Project Settings > API
3. Copy your Project URL to `SUPABASE_URL`
4. Copy your `anon` public key to `SUPABASE_ANON_KEY`
5. Set `AUTH_MODE=supabase` or `AUTH_MODE=both`
