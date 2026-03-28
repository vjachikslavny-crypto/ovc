# Auth Migration — Current State

Документ описывает **фактическое** поведение auth в текущем коде OVC (не исторический план).

## Что реально работает сейчас

### Режимы аутентификации (`AUTH_MODE`)
- `local` — локальный логин/пароль (JWT + refresh cookie)
- `supabase` — только Supabase access token
- `both` — поддерживаются local и Supabase
- `none` — dev-режим (без нормальной аутентификации)

### Регистрация и вход

#### `POST /auth/register`
Текущий контракт:
- `email` — **обязателен**
- `password` — **обязателен**
- `username` — **опционален** (если не передан, генерируется автоматически из email)

Поведение:
- создаётся локальный пользователь
- отправляется письмо подтверждения email
- возвращается `201 { ok: true }`

#### `POST /auth/login`
Текущий контракт:
- `identifier` — username или email
- `password`

Поведение:
- создаётся refresh cookie
- access token получается через `/auth/refresh`

### Подтверждение email
- `GET /auth/verify?token=...` — **существует** и помечает email как подтверждённый.
- `POST /auth/resend-verification` — повторная отправка ссылки подтверждения.

### Пользовательские endpoint'ы
- `GET /api/users/me`
- `PATCH /api/users/me`
- `GET /auth/username-available?u=...`
- `POST /auth/change-password`

### Supabase bridge
- `POST /auth/supabase/session` — создаёт локальную refresh/csrf cookie-сессию из валидного Supabase access token.

## Что удалено/не используется

- `POST /auth/forgot`
- `POST /auth/reset`
- страницы forgot/reset

## Политика паролей (текущая)

Проверка централизована в `src/app/services/password_policy.py`:
- `PASSWORD_MIN_LENGTH` (по умолчанию 8)
- `PASSWORD_MIN_CHARACTER_CLASSES` (по умолчанию 3 из 4: upper/lower/digit/symbol)
- опциональные строгие флаги:
  - `PASSWORD_REQUIRE_UPPER`
  - `PASSWORD_REQUIRE_LOWER`
  - `PASSWORD_REQUIRE_DIGIT`
  - `PASSWORD_REQUIRE_SYMBOL`
- базовый blacklist слишком простых паролей

Одинаковые правила применяются для:
- регистрации
- смены пароля

## Важные замечания

1. Этот документ описывает **текущее состояние кода**, а не целевую будущую архитектуру.
2. Если меняются endpoint'ы или контракты auth, обновляйте этот файл одновременно с кодом.
