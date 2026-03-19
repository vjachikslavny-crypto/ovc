# OVC Human Notes

OVC — заметки на **FastAPI + SQLite** с блочным редактором, графом связей и desktop-приложением (macOS, Tauri).

Проект сейчас работает в двух режимах:
- web-версия (браузер)
- desktop-версия (нативное окно на macOS, тот же UI)

Ключевой принцип: desktop добавлен **аддитивно**, без ломки web-поведения.

## Что есть в проекте

- Блочный редактор заметок (`/`, `/notes/{id}`)
- Граф заметок и связей (`/graph`)
- Теги, связи, «паспорт заметки»
- Загрузка файлов (изображения, PDF, DOCX/RTF, PPTX, Excel/CSV, audio/video, code/markdown)
- Аудиозапись и аудиоплеер
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
uvicorn app.main:app --app-dir src --reload --host 127.0.0.1 --port 8000
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

Рекомендуемо для обычной работы:

```env
AUTH_MODE=both
```

## Offline/Sync (desktop)

Desktop sync использует outbox-модель:
- локальные изменения пишутся сразу
- операции складываются в очередь
- при доступном remote уходят push/pull

Основные переменные:

```env
SYNC_ENABLED=false
SYNC_REMOTE_BASE_URL=
SYNC_BEARER_TOKEN=
SYNC_POLL_SECONDS=15
SYNC_OUTBOX_MAX=10000
SYNC_BATCH_SIZE=100
SYNC_PULL_ENABLED=true
```

Пример включения синка на удалённый backend:

```bash
SYNC_ENABLED=true SYNC_REMOTE_BASE_URL=https://your-server AUTH_MODE=both npm run desktop:dev
```

## .env (минимально)

Пример базовых значений:

```env
DATABASE_URL=sqlite:///./src/ovc.db
SECRET_KEY=CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME
AUTH_MODE=both
COOKIE_SECURE=false
COOKIE_SAMESITE=strict
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
- Refresh-token в HttpOnly cookie
- Access token короткоживущий
- CSRF для cookie-флоу
- Ограничение попыток логина + lockout

## Полезные документы

- `docs/quick_start.md` — быстрый старт
- `docs/repo_map.md` — карта репозитория
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
