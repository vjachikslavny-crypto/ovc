# OVC Human Notes

OVC — заметки на **FastAPI + SQLite** с блочным редактором, графом связей и desktop-приложением (macOS, Tauri).

Проект сейчас работает в двух режимах:
- web-версия (браузер)
- desktop-версия (нативное окно на macOS, тот же UI)

Ключевой принцип: desktop добавлен **аддитивно**, без ломки web-поведения.

Последнее обновление UI (2026-05-10): re-merge `ok10010` в `vanya+max/develop` с theme-aware правками dashboard/graph. Детали: `docs/current_release_notes.md`.

Стабилизация этапов 0–2: [резервное копирование](docs/data_backup_restore.md),
[контракт блоков, сохранение и изоляция аккаунтов](docs/stabilization_stages_0_2.md),
[baseline данных](docs/stabilization_baseline.md). Перед миграциями существующей базы создайте
и проверьте копию. `PATCH /api/notes/{id}` принимает необязательный `If-Match: "r<revision>"`
(старый `"<updatedAt>"` также поддерживается):
устаревшая версия получает 409; редактор сохраняет локальный черновик и предлагает восстановление.
`POST /api/notes/{id}/recovery-copy` принимает тело `NoteCreateRequest` локального
черновика и возвращает `201`, `NoteDetail` и ETag новой копии. Доступен только владельцу
исходной заметки, включая tombstone; cookie-запросы требуют CSRF. Копия получает
свои FileAsset IDs и переписанные URL, поэтому удаление оригинала не ломает вложения.
Семантика и проверки: [этап 4.1](docs/stabilization_stage_4_1.md).
В `AUTH_MODE=none` теперь видны только данные dev-user, а публичный запуск этого режима
блокируется. Существующие личные заметки открывайте после входа в соответствующий аккаунт.

Runtime/public HTTPS: [этап 6](docs/stabilization_stage_6.md) — ограничения загрузки,
изолированные конвертации, потоковое медиа, доверенные proxy и production env.
Обычный локальный запуск сохраняется; реальный `.env` автоматически не меняется.

## Что есть в проекте

- Главная рабочая страница (`/`) + блочный редактор (`/editor`, `/notes/{id}`)
- Граф заметок и связей (`/graph`)
- Теги, связи, «паспорт заметки»
- Загрузка файлов (изображения, PDF, DOCX/RTF, PPTX, Excel/CSV, audio/video, code/markdown)
- Аудиозапись и аудиоплеер
- Удаление заметки из базы с подтверждением
- Локальная авторизация + Supabase (режим задаётся через `AUTH_MODE`)
- Desktop local-first синхронизация (outbox + pull/push)

## Текущая структура

```text
OVC/
├── README.md
├── .env.example
├── alembic.ini
├── alembic/
├── desktop/                 # Tauri wrapper (macOS app)
├── docs/
├── scripts/
├── src/
│   ├── app/                 # FastAPI backend
│   ├── static/              # JS/CSS
│   ├── templates/           # Jinja templates
│   └── requirements.txt
└── tests/
```

## Быстрый запуск web-версии

```bash
cd ~/OVC
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
PYTHONPATH=src python -m app.db.migrate
uvicorn app.main:app --no-proxy-headers --app-dir src --reload --host 127.0.0.1 --port 8000
```

Или одним скриптом:

```bash
cd ~/OVC
./scripts/start_server.sh
```

Открыть: `http://127.0.0.1:8000`

## Public hosting from laptop (Cloudflare Tunnel)

Этот режим открывает сайт в интернет по HTTPS, при этом backend продолжает работать на ноутбуке.

Подготовка:

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create ovc-laptop
cloudflared tunnel route dns ovc-laptop <YOUR_HOSTNAME>
```

Далее:
1. Скопируйте `deploy/cloudflare_tunnel/config.yml.template` в локальный `config.yml`.
2. Заполните `tunnel`, `credentials-file`, `hostname`.
3. В `.env` задайте:

```env
PUBLIC_BASE_URL=https://<YOUR_HOSTNAME>
CORS_ORIGINS=["https://<YOUR_HOSTNAME>","http://127.0.0.1:8000"]
COOKIE_DOMAIN=<YOUR_HOSTNAME>
COOKIE_SECURE=true
CLOUDFLARED_CONFIG_PATH=/absolute/path/to/config.yml
```

Запуск:

```bash
./deploy/cloudflare_tunnel/start_public_server.sh
./deploy/cloudflare_tunnel/start_tunnel.sh
```

Проверка:

```bash
./deploy/cloudflare_tunnel/verify_public.sh
```

Дополнительная инструкция: `deploy/cloudflare_tunnel/README_TUNNEL.md`.

Быстрый временный вариант без домена:

```bash
./deploy/cloudflare_tunnel/start_public_server.sh
QUICK_TUNNEL=true ./deploy/cloudflare_tunnel/start_tunnel.sh
```

Cloudflared выдаст URL вида `https://<random>.trycloudflare.com` (меняется при каждом запуске).

## Запуск desktop (macOS)

Требования:
- Rust/Cargo
- Xcode Command Line Tools
- Python venv с зависимостями проекта

Dev-режим:

```bash
cd ~/OVC
source .venv/bin/activate
AUTH_MODE=both npm run desktop:dev
```

Build:

```bash
cd ~/OVC
npm run desktop:build
```

## Как сейчас устроена база и аккаунты (web + desktop)

По умолчанию desktop и web используют **одну и ту же локальную БД**:

- `DATABASE_URL=sqlite:///./src/ovc.db`
- desktop backend поднимается на `127.0.0.1:18741`
- web backend обычно на `127.0.0.1:8000`

Это даёт общий пул пользователей/заметок локально на одном компьютере.

Если нужно принудительно задать БД для desktop:

```bash
OVC_DESKTOP_DATABASE_URL=sqlite:////absolute/path/to/db.sqlite npm run desktop:dev
```

## AUTH_MODE

`AUTH_MODE` поддерживает:
- `local` — только локальная авторизация
- `supabase` — только Supabase JWT
- `both` — принимаются оба варианта
- `none` — dev-режим без обязательного логина (использовать только для отладки)

Для desktop fallback без токена контролируется явно:

```env
ALLOW_DESKTOP_DEV_FALLBACK=true|false
```

Если fallback включён, backend помечает запросы контекстом `desktop-dev-fallback`.

Рекомендуемо для обычной работы:

```env
AUTH_MODE=both
```

## Offline/Sync (desktop)

Sync v1 использует транзакционную очередь и журнал изменений. `Note.revision` —
локальная версия для web/editor/AI; удалённая версия хранится отдельно в
`SyncEntityMap.remote_revision` и задаёт sync base. Pull изменённого содержимого
увеличивает локальную версию, ack её не подменяет. Операция и durable receipt на сервере фиксируются вместе;
повтор UUID возвращает прежний результат. Конфликты сохраняют обе версии,
удаления передаются tombstone, ID файлов сопоставляются явно.
Удалённая цель старой связи не блокирует текст: намерение сохраняется как
`relation_target_deleted` в `sync_conflicts` и receipt, счётчик `relationConflicts`
виден в status и desktop-индикаторе. При permanent failure, включая preflight,
trigger возвращает `ok=false`; `failed`, `pending`, `retry`, `lastError` согласованы
со status того же пользователя/remote. `ok=true` не означает пустую очередь.

Технический контракт и проверенные сценарии: [sync v1](docs/sync_protocol_v1.md),
[выбор протокола](docs/sync_protocol_selection.md), [legacy quarantine](docs/sync_legacy_quarantine.md).
**Старые 187 операций автоматически не отправляются.** До включения worker выполните
аудит `python -B scripts/audit_legacy_sync.py` и проверьте резервную копию.
При полной очереди новая транзакция получает 503; редактор сохраняет черновик для повтора.

Основные переменные:

```env
SYNC_MODE=auto
SYNC_ENABLED=false
SYNC_REMOTE_BASE_URL=
SYNC_BEARER_TOKEN=
SYNC_POLL_SECONDS=15
SYNC_OUTBOX_MAX=10000
SYNC_BATCH_SIZE=100
SYNC_PULL_ENABLED=true
```

`SYNC_MODE`:
- `off` — удалённый sync выключен
- `shared-db` — desktop/web работают с одной локальной БД, без remote sync
- `remote-shell` — desktop использует удалённый UI/backend, локального обмена репликами нет
- `remote-sync` — очередь и ручной `/api/sync/trigger`; фоновый worker дополнительно требует `SYNC_BEARER_TOKEN`
- `auto` — режим выводится из `DESKTOP_MODE`, `SYNC_ENABLED`, `SYNC_REMOTE_BASE_URL`

Пример включения синка на удалённый backend:

```bash
SYNC_ENABLED=true SYNC_REMOTE_BASE_URL=https://your-server AUTH_MODE=both npm run desktop:dev
```

Обе стороны должны поддерживать v1 и подтверждать одну и ту же auth-идентичность.
`AUTH_MODE=none`/dev fallback не подходят для обмена. Worker закрепляет пользователя
за проверенным токеном, при истечении токена останавливается; ручной trigger использует
текущий access token. Секреты не сохраняются в очереди/status. Менять remote URL можно:
очередь и cursor старого сервера сохранятся отдельно. Подмена server UUID на прежнем URL
блокирует обмен и требует отдельного явного переподключения.

## .env (минимально)

Пример базовых значений:

```env
DATABASE_URL=sqlite:///./src/ovc.db
SECRET_KEY=CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME
AUTH_MODE=both
COOKIE_SECURE=false
COOKIE_SAMESITE=strict
PASSWORD_MIN_LENGTH=8
PASSWORD_MIN_CHARACTER_CLASSES=3
```

Полный список — в `.env.example` и `docs/env.example.md`.

## Файлы и предпросмотр

Загруженные файлы хранятся в `data/uploads/*`.
API:
- оригинал: `/files/{id}/original`
- превью: `/files/{id}/preview`
- для DOCX/RTF inline HTML: `/files/{id}/doc.html`

Если видите заглушку вместо файла в desktop:
1. убедитесь, что вход выполнен в тот же аккаунт
2. проверьте, что `AUTH_MODE=both` или корректный режим
3. перезапустите desktop после смены `.env`

## Безопасность

- Пароли: Argon2id
- Политика паролей: минимум `PASSWORD_MIN_LENGTH` и минимум `PASSWORD_MIN_CHARACTER_CLASSES` классов символов
- Refresh-token в HttpOnly cookie
- Access token короткоживущий
- CSRF для cookie-флоу
- Ограничение попыток логина + lockout
- CSP ограничен реальными origin (без широкого `https:` wildcard)

## Диагностика runtime

В dev/desktop доступен endpoint:

```text
GET /api/runtime/status
```

Показывает безопасный срез конфигурации:
- `authMode`, `syncMode`, `desktopMode`
- включён ли sync worker
- активен ли dev fallback
- request auth context

## Полезные документы

- `docs/quick_start.md` — быстрый старт
- `docs/repo_map.md` — карта репозитория
- `docs/current_release_notes.md` — отдельная сводка всех последних нововведений
- `docs/design-fixes.md` — точечные правки по дизайну и UX
- `docs/auth_migration.md` — заметки по миграции auth
- `docs/pdf/debug.md` — отладка PDF
- `docs/pdf/performance.md` — производительность PDF

## Быстрый чек после обновлений

1. Web:
```bash
./scripts/start_server.sh
```
Проверить: логин, создание заметки, загрузка файла.

2. Desktop:
```bash
AUTH_MODE=both npm run desktop:dev
```
Проверить: логин, создание заметки, загрузка/открытие файла, синк-статус.

## Stage 5: схема, целостность и запуск

Единственный источник схемы — Alembic, текущий head `20260926_integrity`.
Сервер проверяет схему при старте; ошибки миграции больше не скрываются.
`/healthz` показывает жизнь процесса, `/readyz` — доступность БД, head, таблиц/столбцов,
FK SQLite и хранилища. `DB_AUTO_MIGRATE=false` по умолчанию; production требует
явной миграции отдельным шагом до запуска workers. В development/test автообновление
можно включить явно, но оно не ремонтирует повреждённые данные.

**Stage 5 COMPLETE: 2026-09-26 рабочая SQLite явно отремонтирована и проверена в Stage 5.1.**
Она находится на head `20260926_integrity`, FK/cross-owner нарушений нет, все 187 legacy
операций остаются в карантине. Для другой старой/неисправленной копии сначала требуется
отдельный согласованный ремонт с backup; обычный запуск такой схемы будет заблокирован.
Настройки auth/sync, .env и Tauri не менялись. Для пустой БД подходит команда миграции выше.

- [Отчёт Stage 5 и точная процедура ремонта](docs/stabilization_stage_5.md)
- [Stage 5.1: применение к рабочей базе, backup IDs и финальные проверки](docs/stabilization_stage_5_1.md)
- [Каноническая схема и семантика удаления](docs/database_schema.md)
- [Резервная копия и восстановление](docs/data_backup_restore.md)

Ремонт реальных данных выполнен по явному разрешению пользователя после свежего backup,
restore и совпавшего dry-run. Uploads и .env не изменены, production remote sync выключен.
Stage 6 не начат; изменения кода и документации остаются локальными.
