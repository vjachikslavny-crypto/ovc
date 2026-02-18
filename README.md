# OVC Human Notes

Лёгкий офлайн-проект на **FastAPI + SQLite** с “человечными” заметками. Вместо Markdown используется блочная модель (заголовки, абзацы, списки, цитаты, задачи, источники и т.д.), мобильный UX с плавающей кнопкой `＋`, нижним bottom-sheet и инлайн-пузырём форматирования. Всё готово для будущего подключения своей GPT-модели, но сейчас работает вручную.

> 💡 **Sigma 1** — актуальная стабильная версия (ветка `version-s-ne-rabotayushchim-redaktorom-zametok`). Все фиксы попадают сюда, а новые эксперименты развиваются в ветках Sigma 2+.

## Основные возможности

- 🗂 **Список заметок** (`/notes`) — быстрый поиск, пагинация и создание заметок в один клик.
- 📝 **Редактор** (`/` или `/notes/{id}`) — блоки рендерятся из JSON, темы `Clean`/`Brief`, верхний мини-toolbar, inline bubble, smart insert (URL → источник, `- ` → список, `Сводка:` → блок сводки), голос/вложения и “паспорт заметки” (теги, связи, свойства).
- 🕸 **Граф** (`/graph`) — интерактивная визуализация явных связей и общих тегов (пунктир), поиск, подсветка по наведению, настройка цвета и названия групп.
- 🏷️ **Теги** — добавление в паспорте заметки и список всех тегов через `/api/tags`.
- 🔁 **DraftAction API** (`/api/commit`) — атомарно применяет действия (`insert_block`, `update_block`, `move_block`, `add_tag`, `remove_tag`, `add_link`, `set_style`).
- 🔎 **Локальный поиск** — TF-IDF индекс по тексту блоков, обновляется при каждом изменении.
- 🗃 **Журнал** (`/api/dataset/export`) — JSONL-лог для обучения модели.
- 🔐 **Авторизация** — регистрация/вход, refresh-токены в HttpOnly cookie, email‑подтверждение.
- 🤖 **LLM-интерфейсы** — `app/providers/llm_provider.py` + `structurizer.py` заготовлены под будущий Ollama/vLLM, сейчас возвращают пустой draft.

## Быстрый запуск

```bash
# Перейдите в корневую директорию проекта
cd ~/OVC

# Создайте и активируйте виртуальное окружение (если еще не создано)
python3 -m venv .venv
source .venv/bin/activate

# Установите зависимости
pip install -r src/requirements.txt

# Запустите миграцию базы данных (⚠️ очищает текущие таблицы)
PYTHONPATH=src python -m app.db.migrate

# Запустите сервер
uvicorn app.main:app --app-dir src --reload
```

Или используйте скрипт запуска:
```bash
cd ~/OVC
./scripts/start_server.sh
```

Откройте `http://localhost:8000`. Чтобы пересобрать схему, удалите `src/ovc.db` и перезапустите миграцию.

**Важно:** Всегда запускайте сервер из корневой директории проекта `OVC`, а не из `src`!

## Desktop macOS (Tauri add-on)

Desktop-режим добавлен как **аддитивный слой**: веб-UI остаётся тем же, приложение открывает тот же интерфейс в нативном окне.

### Запуск desktop в dev

```bash
cd ~/OVC
npm run desktop:dev
```

По умолчанию desktop поднимает локальный backend (`127.0.0.1:18741`) и использует локальную SQLite в app data директории.

Чтобы принудительно открыть удалённый сервер, задайте:

```bash
OVC_DESKTOP_BASE_URL=https://your-host.example npm run desktop:dev
```

### Сборка desktop

```bash
cd ~/OVC
npm run desktop:build
```

`desktop/src-tauri/tauri.conf.json` уже содержит базовые параметры окна и DMG target. Для App Store позже потребуется отдельный этап: signing/notarization/entitlements.

## Переменные окружения

```
SIMPLE_DB_URL=sqlite:///./src/ovc.db
VECTOR_DIM=384
OFFLINE_MODE=true
```

## Running DB

Для разработки можно использовать PostgreSQL или SQLite:

- **PostgreSQL**: создайте базу, установите `DATABASE_URL` и выполните миграции Alembic.
- **SQLite**: по умолчанию используется `sqlite:///./src/ovc.db` и `python -m app.db.migrate`.

## ENV

Основные переменные (см. `.env.example`):

- `DATABASE_URL` — строка подключения (PostgreSQL рекомендуется).
- `SECRET_KEY` — секрет для JWT/ссылок (32+ символов).
- `ACCESS_TOKEN_EXPIRES_MIN`, `REFRESH_TOKEN_EXPIRES_DAYS`
- `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN`
- `RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_MAX`
- `PASSWORD_MIN_LENGTH` и флаги классов символов
- `EMAIL_FROM`, `EMAIL_BACKEND`
- `DESKTOP_MODE` — включает desktop-ветку поведения (ставится desktop-wrapper’ом)
- `SYNC_ENABLED`, `SYNC_REMOTE_BASE_URL`, `SYNC_BEARER_TOKEN`
- `SYNC_POLL_SECONDS`, `SYNC_BATCH_SIZE`, `SYNC_OUTBOX_MAX`
- `SYNC_PULL_ENABLED` — подтягивать изменения с remote на локальную базу

## Migrations

PostgreSQL (Alembic):

```bash
export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/ovc
PYTHONPATH=src alembic upgrade head
```

SQLite (локально):

```bash
PYTHONPATH=src python -m app.db.migrate
```

## База и авторизация

- Таблицы авторизации: `users`, `refresh_tokens`, `audit_logs` (через Alembic).
- Заметки и файлы теперь привязаны к пользователю через `user_id`.
- Старые записи с пустым `user_id` автоматически закрепляются за первым зарегистрированным пользователем.
- Вход выполняется через access‑JWT (15 минут), refresh‑токен живёт в HttpOnly cookie и ротируется.
- Email подтверждение требуется при логине: ссылка печатается в логах при `EMAIL_BACKEND=mock`.

## Security notes

- Пароли хэшируются через Argon2id (`argon2-cffi`).
- Access токен живёт 15 минут, refresh — 30 дней, refresh токены ротируются.
- Refresh токен хранится в HttpOnly cookie, access токен передаётся как Bearer.
- Для запросов с cookie используется CSRF токен (double-submit).
- Ограничения частоты и блокировки логина — in-memory (для продакшна нужен Redis/DB).
- Sync outbox ограничен `SYNC_OUTBOX_MAX`, чтобы очередь не росла бесконечно.

## Документация

- `docs/quick_start.md` — быстрый запуск.
- `docs/repo_map.md` — карта репозитория.
- `docs/pdf/debug.md` — отладка PDF.
- `docs/pdf/performance.md` — производительность PDF.

## Структура

```
OVC/
├── README.md
├── .env.example
├── alembic.ini
├── alembic/
├── src/
│   ├── app/
│   │   ├── api/          # REST-эндпоинты (notes, commit, chat, export)
│   │   ├── agent/        # JSON-схема блоков и DraftAction
│   │   ├── db/           # SQLAlchemy модели и миграция
│   │   ├── log/          # JSONL журнал
│   │   ├── providers/    # LLM-заглушки и заготовка Ollama
│   │   ├── rag/          # TF-IDF индекс
│   │   └── main.py       # FastAPI приложение
│   ├── static/           # CSS/JS (рендер блоков, тулбары, palette, graph)
│   │   └── js/graph.js            # визуализация графа (D3)
│   ├── templates/        # base.html, notes.html, editor.html, graph.html
│   ├── requirements.txt  # зависимости
│   └── run.sh            # venv + миграция + запуск uvicorn
├── docs/
│   ├── quick_start.md
│   ├── repo_map.md
│   └── pdf/
│       ├── debug.md
│       └── performance.md
├── scripts/
│   └── start_server.sh
└── tests/
```

## Просмотр файлов внутри заметки

- **Изображения** — drag&drop/клипса, предпросмотр и полноразмерный просмотр.
- **PDF** — cover ↔ inline viewer прямо в заметке (ленивая подгрузка страниц, zoom, «Свернуть/Просмотр»).
- **DOCX/RTF** — cover ↔ inline режим, безопасный HTML внутри заметки (заголовки, списки, таблицы, изображения), без экспорта в Word.
- **PPTX** — cover ↔ inline просмотр слайдов с перелистыванием, миниатюрами и полноэкранным режимом.
- **Видео / YouTube** — HTML5-плеер для загруженных файлов (MP4/WebM/MOV и т.д.) с постером и метаданными, а также безопасные YouTube-встраивания (nocookie, без автозапуска).
- **Код** — подсветка синтаксиса (Prism.js), предпросмотр 300 строк и разворачивание до 10 000 строк с баннером для больших файлов, тулбар Copy/Expand.
- **Markdown (.md)** — безопасный рендер внутри заметки (таблицы, чек-листы, картинки, ссылки) с предварительным просмотром 200 КБ и разворачиванием до 10 000 строк, кнопки Copy/Expand/Download, подсветка блоков кода через Prism.
- **Excel / CSV (.xlsx/.xls/.csv)** — карточка с предпросмотром и inline-режим с выбором листа, порционной подгрузкой строк, поиском по текущему окну и скачиванием выбранного листа в CSV.
- **Аудио** — запись с микрофона или загрузка файла, мини-плеер с волной, таймкодами и расширенным режимом.

## Дальнейшие шаги

- Подключить Ollama/vLLM через `LLMProvider` и `structurizer`, формируя DraftAction автоматически.
- Реализовать историю коммитов + undo/redo.
- Добавить импорт JSON и расширенный экспорт (при необходимости).
- Настроить e2e-тестирование (Playwright/pytest + httpx).

Проект остаётся полностью офлайн и служит каркасом для собственной “человечной” модели заметок.

## Быстрая проверка offline -> sync

1. Запустите desktop и отключите интернет.
2. Создайте/измените заметку и (опционально) прикрепите файл.
3. Включите интернет обратно.
4. Проверьте `GET /api/sync/status`: `pending` должно уменьшаться, `done` расти.
5. Для ручного запуска цикла синка: `POST /api/sync/trigger`.
