# Auth Migration — Current State

Документ описывает **фактическое** поведение auth в текущем коде OVC (не исторический план).

## Что реально работает сейчас

### Режимы аутентификации (`AUTH_MODE`)
- `local` — локальный логин/пароль (JWT + refresh cookie)
- `supabase` — Supabase access token; для страниц/медиа также подтверждённая bridge-сессия
- `both` — поддерживаются local и Supabase
- `none` — dev-режим без аутентификации, доступ только к данным dev-user

Local-endpoint'ы ниже доступны только при `local`/`both`, Supabase bridge — при `supabase`/`both`.
Публичный запуск с `none` блокируется; параметры и ограничения описаны в
[stabilization_stages_0_2.md](stabilization_stages_0_2.md).

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
- Сессия хранит провайдера: Supabase bridge нельзя обменять на local JWT через `/auth/refresh`.
- Привязка к существующему local-пользователю по одному email запрещена. Совпавший email
  без подтверждённой привязки или конфликтующий Supabase ID возвращает 409; правильная
  существующая привязка продолжает работать. Старые bridge-сессии требуют повторного входа.

### Refresh, logout и cookies

- Rotation выполняется транзакционно; повтор использованного refresh отзывает сессии пользователя
  с сохранением отзыва до ответа 401. Уже выданные access JWT действуют до истечения срока.
- `POST /auth/logout` отзывает текущий refresh и очищает cookies в возвращаемом ответе.
- Ошибки пароля/lockout сохраняются до ответа об ошибке, время сравнивается в UTC.
- Cookie-запросы, изменяющие состояние, требуют CSRF. Неверный Authorization не переключает
  запрос на другую cookie-сессию.
- `COOKIE_SECURE` соблюдается без автоматического отключения по Host. Для локального HTTP
  требуется `COOKIE_SECURE=false`; `SameSite=None` допустим только вместе с Secure.

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

## Схема auth после Stage 5

Auth tables, `email_verified_at` и `auth_provider` теперь создаются только Alembic.
Запросы регистрации/подтверждения email больше не выполняют `ALTER TABLE` и не скрывают
ошибку отсутствующей колонки. Сервер требует head `20260926_integrity` перед запуском.
Режимы auth, политика паролей и порядок проверки сессий не изменены.
`audit_logs.user_id` намеренно допускает NULL и SET NULL при hard delete пользователя;
его refresh-сессии каскадно удаляются. Исторические сломанные ссылки исправляются только
по отдельному проверенному плану: [Stage 5](stabilization_stage_5.md).
