# OVC Human Notes — Полная техническая документация проекта

> Дата генерации: 14 февраля 2026
> Версия: 0.1.0

---

## Оглавление

1. [Обзор проекта](#1-обзор-проекта)
2. [Структура файлов](#2-структура-файлов)
3. [Архитектура](#3-архитектура)
4. [Бэкенд](#4-бэкенд)
   - 4.1 [Точка входа — main.py](#41-точка-входа--mainpy)
   - 4.2 [Конфигурация — config.py](#42-конфигурация--configpy)
   - 4.3 [Безопасность — security.py](#43-безопасность--securitypy)
   - 4.4 [Провайдеры аутентификации — auth_provider.py](#44-провайдеры-аутентификации--auth_providerpy)
   - 4.5 [Модели базы данных — models.py](#45-модели-базы-данных--modelspy)
   - 4.6 [Сессия БД — session.py](#46-сессия-бд--sessionpy)
   - 4.7 [Миграции — migrate.py](#47-миграции--migratepy)
   - 4.8 [API заметок — notes.py](#48-api-заметок--notespy)
   - 4.9 [API аутентификации — auth.py](#49-api-аутентификации--authpy)
   - 4.10 [API пользователей — users.py](#410-api-пользователей--userspy)
   - 4.11 [API синхронизации — sync.py](#411-api-синхронизации--syncpy)
   - 4.12 [API загрузки файлов — upload.py](#412-api-загрузки-файлов--uploadpy)
   - 4.13 [API раздачи файлов — files.py](#413-api-раздачи-файлов--filespy)
   - 4.14 [API коммитов — commit.py](#414-api-коммитов--commitpy)
   - 4.15 [API чата — chat.py](#415-api-чата--chatpy)
   - 4.16 [API графа — graph.py](#416-api-графа--graphpy)
   - 4.17 [API экспорта — export.py](#417-api-экспорта--exportpy)
   - 4.18 [API резолва URL — resolve.py](#418-api-резолва-url--resolvepy)
   - 4.19 [Pydantic-модели заметок — note_models.py](#419-pydantic-модели-заметок--note_modelspy)
   - 4.20 [Модели блоков — block_models.py](#420-модели-блоков--block_modelspy)
   - 4.21 [Типы действий агента — draft_types.py](#421-типы-действий-агента--draft_typespy)
   - 4.22 [Оркестратор агента — orchestrator.py](#422-оркестратор-агента--orchestratorpy)
   - 4.23 [Движок синхронизации — sync_engine.py](#423-движок-синхронизации--sync_enginepy)
   - 4.24 [Сервис файлов — files.py (services)](#424-сервис-файлов--filespy-services)
   - 4.25 [Политика паролей — password_policy.py](#425-политика-паролей--password_policypy)
   - 4.26 [Rate-лимитер — rate_limit.py](#426-rate-лимитер--rate_limitpy)
   - 4.27 [Аудит-логирование — audit.py](#427-аудит-логирование--auditpy)
   - 4.28 [TF-IDF поиск — tfidf_index.py](#428-tf-idf-поиск--tfidf_indexpy)
   - 4.29 [Чанкинг текста — chunking.py](#429-чанкинг-текста--chunkingpy)
   - 4.30 [Модель User — user.py](#430-модель-user--userpy)
   - 4.31 [Модель RefreshToken — session.py](#431-модель-refreshtoken--sessionpy-модели)
   - 4.32 [Модель AuditLog — audit.py (модели)](#432-модель-auditlog--auditpy-модели)
   - 4.33 [Схемы аутентификации — schemas/auth.py](#433-схемы-аутентификации--schemasauthpy)
   - 4.34 [Схемы пользователей — schemas/user.py](#434-схемы-пользователей--schemasuserpy)
5. [Фронтенд](#5-фронтенд)
   - 5.1 [editor.js — Главный контроллер редактора](#51-editorjs--главный-контроллер-редактора)
   - 5.2 [notes_page.js — Страница списка заметок](#52-notes_pagejs--страница-списка-заметок)
   - 5.3 [blocks_render.js — Рендеринг блоков](#53-blocks_renderjs--рендеринг-блоков)
   - 5.4 [audio_recorder.js — Запись аудио](#54-audio_recorderjs--запись-аудио)
   - 5.5 [audio_player.js — Проигрыватель аудио](#55-audio_playerjs--проигрыватель-аудио)
   - 5.6 [mini-graph.js — Мини-граф в редакторе](#56-mini-graphjs--мини-граф-в-редакторе)
   - 5.7 [graph.js — Полноэкранный граф](#57-graphjs--полноэкранный-граф)
   - 5.8 [uploader.js — Загрузчик файлов](#58-uploaderjs--загрузчик-файлов)
   - 5.9 [palette.js — Палитра блоков](#59-palettejs--палитра-блоков)
   - 5.10 [notes_renderer.js — Рендеринг карточек заметок](#510-notes_rendererjs--рендеринг-карточек-заметок)
   - 5.11 [toolbar.js — Панель форматирования](#511-toolbarjs--панель-форматирования)
   - 5.12 [inline_bubble.js — Inline-пузырёк форматирования](#512-inline_bubblejs--inline-пузырёк-форматирования)
   - 5.13 [smart_insert.js — Умная вставка блоков](#513-smart_insertjs--умная-вставка-блоков)
   - 5.14 [inspector.js — Инспектор заметки](#514-inspectorjs--инспектор-заметки)
   - 5.15 [connections_panel.js — Панель связей](#515-connections_paneljs--панель-связей)
   - 5.16 [word_viewer.js — Просмотр DOCX/RTF](#516-word_viewerjs--просмотр-docxrtf)
   - 5.17 [pdf_viewer.js — Просмотр PDF](#517-pdf_viewerjs--просмотр-pdf)
   - 5.18 [slides_viewer.js — Просмотр презентаций](#518-slides_viewerjs--просмотр-презентаций)
   - 5.19 [table_viewer.js — Просмотр таблиц Excel/CSV](#519-table_viewerjs--просмотр-таблиц-excelcsv)
   - 5.20 [markdown_viewer.js — Просмотр Markdown](#520-markdown_viewerjs--просмотр-markdown)
   - 5.21 [auth.js — Слой аутентификации](#521-authjs--слой-аутентификации)
   - 5.22 [supabase_auth.js — Интеграция Supabase](#522-supabase_authjs--интеграция-supabase)
   - 5.23 [data_adapter.js — Десктопный адаптер синхронизации](#523-data_adapterjs--десктопный-адаптер-синхронизации)
   - 5.24 [app_bootstrap.js — Инициализация глобальных переменных](#524-app_bootstrapjs--инициализация-глобальных-переменных)
   - 5.25 [theme.js — Переключение тем](#525-themejs--переключение-тем)
   - 5.26 [utils.js — Утилиты](#526-utilsjs--утилиты)
   - 5.27 [hints.js — Подсказки](#527-hintsjs--подсказки)
   - 5.28 [password_toggle.js — Переключение видимости пароля](#528-password_togglejs--переключение-видимости-пароля)
   - 5.29 [Страницы аутентификации](#529-страницы-аутентификации)
6. [HTML-шаблоны](#6-html-шаблоны)
   - 6.1 [base.html — Базовый шаблон](#61-basehtml--базовый-шаблон)
   - 6.2 [editor.html — Страница редактора](#62-editorhtml--страница-редактора)
   - 6.3 [notes.html — Список заметок](#63-noteshtml--список-заметок)
   - 6.4 [graph.html — Страница графа](#64-graphhtml--страница-графа)
   - 6.5 [Шаблоны аутентификации](#65-шаблоны-аутентификации)
   - 6.6 [welcome.html — Приветственная страница](#66-welcomehtml--приветственная-страница)
7. [CSS — Стили](#7-css--стили)
8. [Десктопное приложение (Tauri)](#8-десктопное-приложение-tauri)
   - 8.1 [main.rs — Rust точка входа](#81-mainrs--rust-точка-входа)
   - 8.2 [tauri.conf.json — Конфигурация Tauri](#82-tauriconfjson--конфигурация-tauri)
   - 8.3 [Cargo.toml — Зависимости Rust](#83-cargotoml--зависимости-rust)
   - 8.4 [Info.plist — Разрешения macOS](#84-infoplist--разрешения-macos)
   - 8.5 [build.rs — Скрипт сборки](#85-buildrs--скрипт-сборки)
9. [Скрипты и утилиты](#9-скрипты-и-утилиты)
10. [Переменные окружения — Полный список](#10-переменные-окружения--полный-список)
11. [Зависимости Python](#11-зависимости-python)
12. [Полный список API-эндпоинтов](#12-полный-список-api-эндпоинтов)
13. [Схема базы данных](#13-схема-базы-данных)
14. [Потоки данных](#14-потоки-данных)

---

## 1. Обзор проекта

**OVC Human Notes** — это приложение для управления заметками с поддержкой:
- Богатого редактора блоков (текст, заголовки, списки, цитаты, таблицы, аудио, видео, изображения, документы, слайды, код, markdown, YouTube, Instagram, TikTok)
- Графа знаний (визуализация связей между заметками через D3.js)
- Полнотекстового поиска (TF-IDF с scikit-learn)
- Загрузки и обработки файлов (изображения, PDF, DOCX, RTF, PPTX, Excel, CSV, аудио, видео, код, markdown)
- Аутентификации (локальная JWT, Supabase, гибридная, без аутентификации)
- Синхронизации между устройствами (outbox-очередь, push/pull к удалённому серверу)
- Десктопного приложения (Tauri + WKWebView на macOS)

**Стек технологий:**
- **Бэкенд:** Python 3, FastAPI, SQLAlchemy, Pydantic v2, SQLite (основная), PostgreSQL (опционально)
- **Фронтенд:** Vanilla JavaScript (ES модули), HTML5, CSS3, D3.js (графы), Prism.js (подсветка кода), markdown-it (рендеринг markdown), DOMPurify (санитизация HTML)
- **Десктоп:** Rust, Tauri 1.6, WKWebView (macOS)
- **Внешние сервисы:** Supabase (опционально), Cloudflare Tunnel (опционально)

---

## 2. Структура файлов

```
OVC/
├── desktop/                           # Десктопное приложение Tauri
│   └── src-tauri/
│       ├── src/
│       │   └── main.rs                # Rust точка входа
│       ├── icons/
│       │   └── icon.png               # Иконка приложения
│       ├── Cargo.toml                 # Зависимости Rust
│       ├── tauri.conf.json            # Конфигурация Tauri
│       ├── Info.plist                 # Разрешения macOS
│       └── build.rs                   # Скрипт сборки
├── docs/
│   └── auth_migration.md             # Документация аутентификации
├── scripts/
│   ├── start_server.sh               # Скрипт запуска сервера
│   └── migrate_desktop_to_shared.py  # Скрипт миграции данных
├── src/
│   ├── app/
│   │   ├── main.py                   # Точка входа FastAPI
│   │   ├── core/
│   │   │   ├── config.py             # Конфигурация (Settings)
│   │   │   ├── security.py           # JWT, хеширование, CSRF, аутентификация
│   │   │   └── auth_provider.py      # Провайдеры аутентификации
│   │   ├── db/
│   │   │   ├── models.py             # SQLAlchemy модели (Note, NoteChunk, и т.д.)
│   │   │   ├── session.py            # Создание engine и сессий
│   │   │   └── migrate.py            # Автоматические миграции
│   │   ├── api/
│   │   │   ├── notes.py              # CRUD заметок + поиск
│   │   │   ├── upload.py             # Загрузка файлов
│   │   │   ├── files.py              # Раздача файлов (стриминг, превью)
│   │   │   ├── commit.py             # Пакетные действия агента
│   │   │   ├── chat.py               # Чат с агентом
│   │   │   ├── graph.py              # Данные графа
│   │   │   ├── export.py             # Экспорт (заглушка)
│   │   │   ├── resolve.py            # Резолв YouTube/TikTok URL
│   │   │   ├── sync.py               # Эндпоинты синхронизации
│   │   │   ├── note_models.py        # Pydantic-модели заметок
│   │   │   └── routes/
│   │   │       ├── auth.py           # Эндпоинты аутентификации
│   │   │       └── users.py          # Эндпоинты пользователей
│   │   ├── agent/
│   │   │   ├── block_models.py       # Pydantic-модели 22 типов блоков
│   │   │   ├── draft_types.py        # Типы действий агента
│   │   │   └── orchestrator.py       # Оркестратор (заглушка)
│   │   ├── models/
│   │   │   ├── user.py               # SQLAlchemy модель User
│   │   │   ├── session.py            # SQLAlchemy модель RefreshToken
│   │   │   └── audit.py              # SQLAlchemy модель AuditLog
│   │   ├── schemas/
│   │   │   ├── auth.py               # Pydantic-схемы аутентификации
│   │   │   └── user.py               # Pydantic-схемы пользователя
│   │   ├── services/
│   │   │   ├── sync_engine.py        # Движок синхронизации (push/pull/outbox)
│   │   │   ├── files.py              # Обработка файлов (превью, метаданные)
│   │   │   ├── password_policy.py    # Валидация паролей
│   │   │   ├── rate_limit.py         # In-memory rate-лимитер
│   │   │   └── audit.py              # Запись аудит-логов
│   │   └── rag/
│   │       ├── tfidf_index.py        # In-memory TF-IDF индекс
│   │       └── chunking.py           # Разбиение текста на чанки
│   ├── static/
│   │   ├── css/
│   │   │   ├── styles.css            # Все стили (~4600 строк)
│   │   │   ├── prism-tomorrow.css    # Тема Prism.js
│   │   │   └── prism-ovc.css         # Кастомная тема Prism
│   │   └── js/
│   │       ├── editor.js             # Главный контроллер редактора
│   │       ├── notes_page.js         # Страница списка заметок
│   │       ├── blocks_render.js      # Рендеринг всех типов блоков
│   │       ├── audio_recorder.js     # Запись аудио (MediaRecorder/PCM)
│   │       ├── audio_player.js       # Кастомный аудио-плеер
│   │       ├── mini-graph.js         # Мини-граф в сайдбаре редактора
│   │       ├── graph.js              # Полноэкранный граф знаний
│   │       ├── uploader.js           # Загрузка файлов (drag-drop, paste)
│   │       ├── palette.js            # Палитра вставки блоков
│   │       ├── notes_renderer.js     # Рендеринг карточек заметок
│   │       ├── toolbar.js            # Форматирование (bold, italic, и т.д.)
│   │       ├── inline_bubble.js      # Плавающий пузырёк форматирования
│   │       ├── smart_insert.js       # Автотрансформация блоков
│   │       ├── inspector.js          # Инспектор заметки (теги, связи)
│   │       ├── connections_panel.js   # Панель связей
│   │       ├── word_viewer.js        # Просмотр DOCX/RTF
│   │       ├── pdf_viewer.js         # Просмотр PDF
│   │       ├── slides_viewer.js      # Просмотр PPTX
│   │       ├── table_viewer.js       # Просмотр Excel/CSV
│   │       ├── markdown_viewer.js    # Просмотр Markdown
│   │       ├── auth.js               # Аутентификация (fetch wrapper)
│   │       ├── supabase_auth.js      # Supabase-интеграция
│   │       ├── data_adapter.js       # Десктопный sync-адаптер
│   │       ├── app_bootstrap.js      # Инициализация глобалов
│   │       ├── theme.js              # Переключатель тем
│   │       ├── utils.js              # Утилиты (uuid)
│   │       ├── hints.js              # Подсказки-баннеры
│   │       ├── password_toggle.js    # Видимость пароля
│   │       ├── auth_login_page.js    # Логика формы логина
│   │       ├── auth_register_page.js # Логика формы регистрации
│   │       └── auth_change_password_page.js # Логика смены пароля
│   ├── templates/
│   │   ├── base.html                 # Базовый Jinja2-шаблон
│   │   ├── editor.html               # Страница редактора
│   │   ├── notes.html                # Список заметок
│   │   ├── graph.html                # Страница графа
│   │   ├── welcome.html              # Приветственная страница
│   │   └── auth/
│   │       ├── login.html            # Логин
│   │       ├── register.html         # Регистрация
│   │       └── change-password.html  # Смена пароля
│   ├── requirements.txt              # Python-зависимости с версиями
│   └── ovc.db                        # SQLite база данных (runtime)
├── .env.example                      # Пример переменных окружения
├── package.json                      # npm-скрипты для десктопа
└── README.md                         # Общая документация
```

---

## 3. Архитектура

### 3.1. Общая схема

```
┌─────────────────────────────────────────────────────────┐
│                    Клиент (Браузер / Tauri WKWebView)   │
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐  │
│  │editor.js│  │notes_page│  │ graph.js  │  │ auth.js │  │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └────┬────┘  │
│       │            │             │              │        │
│       └────────────┴─────────────┴──────────────┘        │
│                          │                               │
│              fetch() с Bearer token + CSRF               │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼───────────────────────────────┐
│                  FastAPI (Python бэкенд)                  │
│                                                           │
│  ┌────────────────────────────────────────────────┐       │
│  │              Middleware слой                    │       │
│  │  • CORS                                        │       │
│  │  • CSP Headers                                 │       │
│  │  • CSRF Cookie                                 │       │
│  │  • Desktop File Proxy (404 → remote)           │       │
│  └────────────────────────────────────────────────┘       │
│                                                           │
│  ┌────────────────┐  ┌────────────┐  ┌────────────────┐   │
│  │  API Routers   │  │  Services  │  │     Core       │   │
│  │  • notes       │  │  • files   │  │  • config      │   │
│  │  • upload      │  │  • sync    │  │  • security    │   │
│  │  • files       │  │  • audit   │  │  • auth_prov.  │   │
│  │  • auth        │  │  • rate    │  │                │   │
│  │  • users       │  │  • passwd  │  │                │   │
│  │  • graph       │  │            │  │                │   │
│  │  • commit      │  │            │  │                │   │
│  │  • chat        │  │            │  │                │   │
│  │  • sync        │  │            │  │                │   │
│  │  • resolve     │  │            │  │                │   │
│  │  • export      │  │            │  │                │   │
│  └────────┬───────┘  └─────┬──────┘  └────────────────┘   │
│           │                │                               │
│  ┌────────▼────────────────▼──────────────────────┐       │
│  │              SQLAlchemy ORM                     │       │
│  │  • Session (contextmanager)                    │       │
│  │  • Auto-migrations on startup                  │       │
│  └────────────────────┬───────────────────────────┘       │
│                       │                                    │
│  ┌────────────────────▼───────────────────────────┐       │
│  │         SQLite (ovc.db) / PostgreSQL            │       │
│  └────────────────────────────────────────────────┘       │
│                                                           │
│  ┌────────────────────────────────────────────────┐       │
│  │         In-Memory Services                      │       │
│  │  • TF-IDF Index (scikit-learn, thread-safe)     │       │
│  │  • Rate Limiter (sliding window deque)          │       │
│  │  • Login Lockout (in-memory tracking)           │       │
│  │  • JWKS Cache (Supabase keys, TTL 600s)         │       │
│  └────────────────────────────────────────────────┘       │
│                                                           │
│  ┌────────────────────────────────────────────────┐       │
│  │         Background Sync Worker (daemon thread)  │       │
│  │  • Polls every sync_poll_seconds                │       │
│  │  • Push outbox → remote                         │       │
│  │  • Pull remote → local                          │       │
│  │  • LWW conflict resolution                      │       │
│  └────────────────────────────────────────────────┘       │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│               Tauri Desktop Wrapper (опционально)          │
│                                                            │
│  ┌──────────────────┐    ┌────────────────────────────┐    │
│  │  main.rs (Rust)  │───>│  spawn_local_backend()     │    │
│  │  • Spawn Python  │    │  python3 -m uvicorn ...    │    │
│  │  • Wait for port │    │  port 18741                │    │
│  │  • Create window │    └────────────────────────────┘    │
│  │  • Kill on exit  │                                      │
│  └──────────────────┘                                      │
│                                                            │
│  WKWebView → http://127.0.0.1:18741                       │
└────────────────────────────────────────────────────────────┘
```

### 3.2. Потоки аутентификации

```
AUTH_MODE = "local":
  Логин → POST /auth/login → JWT access token (15 мин) + refresh token (30 дн) в httpOnly cookies
  Каждый API запрос → Authorization: Bearer <access_token>
  При 401 → POST /auth/refresh → новый access token (ротация refresh token)
  
AUTH_MODE = "supabase":
  Логин → Supabase SDK → POST /auth/supabase/session → мост к локальным cookies
  
AUTH_MODE = "both":
  Пробует local JWT → если не совпал → пробует Supabase → если нет → desktop fallback
  
AUTH_MODE = "none":
  Всегда dev-user (id="00000000-...", email="dev@localhost")
```

### 3.3. Поток синхронизации

```
SYNC_MODE = "off":          Без синхронизации
SYNC_MODE = "shared-db":    Общая SQLite база (через файловую систему)
SYNC_MODE = "remote-sync":  Push/Pull через HTTP к удалённому серверу
SYNC_MODE = "remote-shell": CLI синхронизация (через скрипты)
SYNC_MODE = "auto":         Автоопределение по конфигурации

Поток remote-sync:
  1. Действие пользователя (создание/изменение/удаление заметки) 
     → enqueue_sync_operation() → SyncOutbox (pending)
  2. Background worker (каждые sync_poll_seconds):
     a. Push: берёт pending из SyncOutbox → HTTP к удалённому серверу → done/failed
     b. Pull: GET /api/notes с удалённого → сравнивает updated_at → upsert локально
  3. Конфликт: если local pending + remote newer → создаёт копию (SyncConflict)
```

---

## 4. Бэкенд

---

### 4.1. Точка входа — main.py

**Файл:** `src/app/main.py`

**Назначение:** Создаёт экземпляр FastAPI, регистрирует все роутеры, настраивает middleware, серверит шаблоны и статику.

#### Константы

| Константа | Значение | Описание |
|-----------|----------|----------|
| `MAX_REQUEST_SIZE` | `500 * 1024 * 1024` (500 МБ) | Максимальный размер запроса |

#### Startup Event (`startup_event`)

При запуске приложения выполняется:
1. Логирование доступности PDF-библиотек (`HAS_PYMUPDF`, `HAS_PDF2IMAGE`)
2. Запуск миграций — `app.db.migrate.upgrade()`
3. Логирование `settings.runtime_summary()` и предупреждений
4. Запуск фонового воркера синхронизации — `start_sync_worker_once()`

#### CORS Middleware

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # localhost варианты + CORS_ORIGINS env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Origins по умолчанию:
- `http://127.0.0.1:8000`, `http://localhost:8000`
- `http://127.0.0.1:18741`, `http://localhost:18741`
- `tauri://localhost`
- Дополнительные из `CORS_ORIGINS` env (CSV)

#### Регистрация роутеров

| Роутер | Префикс | Исходный модуль |
|--------|---------|-----------------|
| `chat_router` | `/api` | `app.api.chat` |
| `commit_router` | `/api` | `app.api.commit` |
| `notes_router` | `/api` | `app.api.notes` |
| `export_router` | `/api` | `app.api.export` |
| `graph_router` | `/api` | `app.api.graph` |
| `upload_router` | `/api` | `app.api.upload` |
| `resolve_router` | `/api` | `app.api.resolve` |
| `sync_router` | `/api` | `app.api.sync` |
| `files_router` | (без префикса) | `app.api.files` |
| `auth_router` | (без префикса) | `app.api.routes.auth` |
| `users_router` | `/api` | `app.api.routes.users` |

#### Статика и шаблоны

- Статические файлы: `src/static/` → монтируются на `/static`
- Шаблоны: `src/templates/` → Jinja2
- Глобальные переменные шаблонов: `auth_mode`, `desktop_mode`

#### HTTP Middleware — `security_headers`

Добавляет заголовки безопасности к каждому ответу:

| Заголовок | Значение |
|-----------|----------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), geolocation=(), payment=()` |
| `Content-Security-Policy` | Динамический (см. ниже) |
| `X-OVC-Auth-Context` | (опционально, если `runtime_status_enabled`) |

CSP директивы:
- `default-src 'self'`
- `script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://www.instagram.com` + `CSP_SCRIPT_SRC_EXTRA`
- `style-src 'self' 'unsafe-inline'` + `CSP_STYLE_SRC_EXTRA`
- `img-src 'self' data: blob:` + `CSP_IMG_SRC_EXTRA`
- `font-src 'self' data:`
- `media-src 'self' data: blob: https:` + динамические origins
- `connect-src 'self'` + Supabase URL + sync URL + CDN + `CSP_CONNECT_SRC_EXTRA`
- `frame-src 'self' https://www.instagram.com https://www.tiktok.com` + `CSP_FRAME_SRC_EXTRA`
- `object-src 'none'`
- `frame-ancestors 'none'`

Режим `CSP_REPORT_ONLY` — заголовок `Content-Security-Policy-Report-Only` вместо блокирующего.

#### Дополнительная логика middleware

- `_proxy_remote_file_if_needed(request, response)` — для десктоп-режима: если ответ на `/files/*` — 404, проксирует запрос к `SYNC_REMOTE_BASE_URL`. Передаёт заголовки авторизации, Range, Cache-Control. Генерирует короткоживущий access token из refresh cookie.

#### Страничные маршруты

| Метод | Путь | Аутентификация | Шаблон |
|-------|------|----------------|--------|
| GET | `/` | Опциональная | `editor.html` или `welcome.html` |
| GET | `/notes` | Опциональная | `notes.html` |
| GET | `/notes/{note_id}` | Опциональная | `editor.html` |
| GET | `/graph` | Опциональная | `graph.html` |
| GET | `/change-password` | Опциональная | `auth/change-password.html` |
| GET | `/healthz` | Нет | `{"ok": true}` |
| GET | `/api/runtime/status` | Нет (если включен) | JSON с конфигурацией |

#### Ключевые внутренние функции

| Функция | Описание |
|---------|----------|
| `_require_user(request)` | Извлекает User из refresh cookie или возвращает None |
| `_allow_anonymous()` | True если desktop dev fallback, или auth_mode в (none, supabase, both) |
| `_ensure_csrf_cookie(request, response)` | Устанавливает CSRF cookie если отсутствует |
| `_proxy_remote_file_if_needed(request, response)` | Проксирует файлы с удалённого сервера при 404 |

---

### 4.2. Конфигурация — config.py

**Файл:** `src/app/core/config.py`

**Назначение:** Загрузка `.env` файлов, определение всех настроек приложения с валидацией и значениями по умолчанию. Экспортирует единственный экземпляр `settings`.

#### Типы

```python
AuthMode = Literal["none", "local", "supabase", "both"]
SyncMode = Literal["off", "shared-db", "remote-sync", "remote-shell"]
```

#### Порядок загрузки .env файлов

1. `OVC/.env`
2. `OVC/src/.env` (legacy)
3. `cwd/.env`
4. `~/OVC/.env`

#### Полный список настроек

| Настройка | Env-переменная | Значение по умолчанию | Описание |
|-----------|----------------|----------------------|----------|
| `database_url` | `DATABASE_URL` / `SIMPLE_DB_URL` | `sqlite:///.../src/ovc.db` | URL базы данных. Нормализует относительные sqlite пути |
| `secret_key` | `SECRET_KEY` | `CHANGE_ME_...` | Ключ подписи JWT. Минимум 32 символа |
| `access_token_expires_min` | `ACCESS_TOKEN_EXPIRES_MIN` | `15` | TTL access token в минутах |
| `refresh_token_expires_days` | `REFRESH_TOKEN_EXPIRES_DAYS` | `30` | TTL refresh token в днях |
| `cookie_domain` | `COOKIE_DOMAIN` | `None` | Домен для cookies |
| `cookie_secure` | `COOKIE_SECURE` | `False` | Только HTTPS cookies |
| `cookie_samesite` | `COOKIE_SAMESITE` | `"lax"` | SameSite политика |
| `public_base_url` | `PUBLIC_BASE_URL` | `""` | Публичный URL (для CSP) |
| `cors_origins` | `CORS_ORIGINS` | hardcoded defaults | JSON массив или CSV |
| `rate_limit_window_seconds` | `RATE_LIMIT_WINDOW_SECONDS` | `60` | Окно rate limit |
| `rate_limit_max` | `RATE_LIMIT_MAX` | `60` | Макс. запросов за окно |
| `rate_limit_login_per_min` | `RATE_LIMIT_LOGIN_PER_MIN` | `10` | Лимит попыток логина |
| `rate_limit_register_per_min` | `RATE_LIMIT_REGISTER_PER_MIN` | = login | Лимит регистраций |
| `password_min_length` | `PASSWORD_MIN_LENGTH` | `8` | Мин. длина пароля (не менее 6) |
| `password_min_character_classes` | `PASSWORD_MIN_CHARACTER_CLASSES` | `3` | Мин. классов символов (1–4) |
| `password_require_upper` | `PASSWORD_REQUIRE_UPPER` | `False` | Требовать заглавные |
| `password_require_lower` | `PASSWORD_REQUIRE_LOWER` | `False` | Требовать строчные |
| `password_require_digit` | `PASSWORD_REQUIRE_DIGIT` | `False` | Требовать цифры |
| `password_require_symbol` | `PASSWORD_REQUIRE_SYMBOL` | `False` | Требовать спецсимволы |
| `email_from` | `EMAIL_FROM` | `no-reply@ovc.local` | Адрес отправителя |
| `email_backend` | `EMAIL_BACKEND` | `mock` | Бэкенд email |
| `app_env` | `APP_ENV` | `development` | Окружение |
| `desktop_mode` | `DESKTOP_MODE` | `False` | Режим десктоп-приложения |
| `allow_desktop_dev_fallback` | `ALLOW_DESKTOP_DEV_FALLBACK` | = desktop_mode | Разрешить dev-user без аутентификации |
| `sync_enabled` | `SYNC_ENABLED` | `False` | Включить синхронизацию |
| `sync_remote_base_url` | `SYNC_REMOTE_BASE_URL` | `""` | URL удалённого сервера |
| `sync_bearer_token` | `SYNC_BEARER_TOKEN` | `""` | Токен для sync |
| `sync_poll_seconds` | `SYNC_POLL_SECONDS` | `15` | Интервал опроса (сек) |
| `sync_outbox_max` | `SYNC_OUTBOX_MAX` | `10000` | Макс. записей в outbox |
| `sync_batch_size` | `SYNC_BATCH_SIZE` | `100` | Размер батча |
| `sync_request_timeout_seconds` | `SYNC_REQUEST_TIMEOUT_SECONDS` | `12` | Таймаут HTTP запроса |
| `sync_pull_enabled` | `SYNC_PULL_ENABLED` | `True` | Разрешить pull |
| `sync_mode` | `SYNC_MODE` | `auto` | Режим синхронизации |
| `auth_mode` | `AUTH_MODE` | `local` | Режим аутентификации |
| `supabase_url` | `SUPABASE_URL` | `""` | URL Supabase |
| `supabase_anon_key` | `SUPABASE_ANON_KEY` | `""` | Anon ключ Supabase |
| `supabase_issuer` | `SUPABASE_ISSUER` | `{supabase_url}/auth/v1` | Issuer JWT Supabase |
| `supabase_jwks_url` | `SUPABASE_JWKS_URL` | `{supabase_url}/auth/v1/.well-known/jwks.json` | JWKS URL |
| `supabase_jwt_aud` | `SUPABASE_JWT_AUD` | `authenticated` | JWT audience |
| `runtime_status_enabled` | `RUNTIME_STATUS_ENABLED` | динамически | Эндпоинт диагностики |
| `csp_report_only` | `CSP_REPORT_ONLY` | `False` | CSP в режиме отчёта |
| `csp_script_src_extra` | `CSP_SCRIPT_SRC_EXTRA` | `[]` | Доп. CSP script sources |
| `csp_style_src_extra` | `CSP_STYLE_SRC_EXTRA` | `[]` | Доп. CSP style sources |
| `csp_connect_src_extra` | `CSP_CONNECT_SRC_EXTRA` | `[]` | Доп. CSP connect sources |
| `csp_img_src_extra` | `CSP_IMG_SRC_EXTRA` | `[]` | Доп. CSP img sources |
| `csp_frame_src_extra` | `CSP_FRAME_SRC_EXTRA` | `[]` | Доп. CSP frame sources |

#### Вычисляемые настройки

- `sync_remote_configured = bool(sync_remote_base_url)` — есть ли удалённый сервер
- `sync_worker_enabled = sync_mode == "remote-sync" and bool(sync_bearer_token)` — запускать ли воркер

#### Автоопределение sync_mode (значение `auto`)

| Условие | Результат |
|---------|----------|
| Есть remote URL + SYNC_ENABLED | `remote-sync` |
| Есть remote URL + DESKTOP_MODE | `remote-shell` |
| Нет remote URL + DESKTOP_MODE | `shared-db` |
| Иначе | `off` |

#### Методы

| Метод | Описание |
|-------|----------|
| `runtime_summary()` | Возвращает dict текущей конфигурации для диагностики |
| `_parse_cors_origins()` | Список origins с defaults + CORS_ORIGINS env |
| `_parse_csv_env(name)` | Парсинг CSV из переменной окружения |

---

### 4.3. Безопасность — security.py

**Файл:** `src/app/core/security.py`

**Назначение:** Хеширование паролей (Argon2id), создание/верификация JWT, CSRF, управление refresh-токенами, аутентификация, блокировка аккаунтов.

#### Константы

| Константа | Значение | Описание |
|-----------|----------|----------|
| `JWT_ALG` | `"HS256"` | Алгоритм JWT |
| `CSRF_COOKIE` | `"csrf_token"` | Имя CSRF cookie |
| `REFRESH_COOKIE` | `"refresh_token"` | Имя refresh cookie |
| `ACCESS_COOKIE` | `"ovc_access_token"` | Имя access cookie |
| `USERNAME_REGEX` | `r'^[a-zA-Z0-9._-]{3,24}$'` | Валидация username |
| `FORBIDDEN_USERNAMES` | `{'admin', 'root', 'system', 'api', 'auth', 'login', 'register', 'logout', 'me'}` | Запрещённые имена |

#### Функции

| Функция | Сигнатура | Описание |
|---------|-----------|----------|
| `hash_password` | `(password: str) -> str` | Хеширование Argon2id |
| `verify_password` | `(password: str, password_hash: str) -> bool` | Проверка Argon2id хеша |
| `create_access_token` | `(subject: str, *, extra_claims=None) -> str` | JWT с полями sub, iat, exp, jti. Алгоритм HS256. Принимает extra_claims dict |
| `decode_access_token` | `(token: str) -> dict` | Декодирование и верификация JWT |
| `hash_refresh_token` | `(raw_token: str) -> str` | SHA256 + pepper (secret_key), base64 |
| `generate_refresh_token` | `() -> str` | `secrets.token_urlsafe(48)` |
| `issue_csrf_token` | `() -> str` | `secrets.token_urlsafe(32)` |
| `get_bearer_token` | `(request) -> Optional[str]` | Из `Authorization` заголовка, `ovc_access_token` cookie, или `access_token` query param |
| `require_csrf` | `(request) -> None` | Валидация `X-CSRF-Token` заголовка vs `csrf_token` cookie |
| `get_current_user` | `(request) -> User` | Главная функция аутентификации. Делегирует в provider layer |
| `get_user_from_refresh_cookie` | `(request) -> User` | Валидация refresh_token cookie (не отозван, не ротирован, не истёк) |
| `get_current_user_or_refresh` | `(request) -> User` | Пробует bearer token, fallback на refresh cookie |
| `validate_username` | `(username: str) -> bool` | Regex + проверка запрещённых имён |
| `check_user_locked` | `(user) -> tuple[bool, Optional[datetime]]` | Проверка `locked_until` |
| `register_login_failure` | `(session, user, max_failures=10)` | Инкремент счётчика, блокировка на 15 мин после max |
| `reset_login_failures` | `(session, user)` | Сброс счётчика и блокировки |

---

### 4.4. Провайдеры аутентификации — auth_provider.py

**Файл:** `src/app/core/auth_provider.py`

**Назначение:** Поддержка local JWT, Supabase JWT (JWKS или userinfo fallback), dev-fallback. Возвращает унифицированные `AuthUser` объекты.

#### Классы

**`AuthUser`** (dataclass):
- `id: str` — ID пользователя
- `email: Optional[str]` — email
- `provider: str` — `"local" | "supabase" | "none" | "dev-fallback"`
- `raw_claims: Optional[Dict[str, Any]]` — сырые claims JWT

**`JWKSCache`** — In-memory кеш JWKS-ключей Supabase:
- TTL: 600 секунд
- Методы: `is_expired()`, `get_key(kid)`, `update(jwks_data)`

#### Функции

| Функция | Описание |
|---------|----------|
| `_fetch_jwks()` | HTTP запрос к `supabase_jwks_url`, обновление кеша |
| `_is_supabase_issuer(issuer)` | Проверка совпадения issuer с конфигурацией Supabase |
| `_verify_supabase_token_via_userinfo(token)` | Валидация через Supabase `/auth/v1/user` API |
| `_get_signing_key(token)` | Получение JWKS signing key по `kid` из кеша или запроса |
| `get_bearer_token(request)` | Извлечение токена из header/cookie/query |
| `local_auth_get_user(request)` | Декодирование локального JWT, пропуск Supabase-подобных токенов (ES256/RS256) |
| `supabase_auth_get_user(request)` | Верификация Supabase JWT (JWKS для ES256/RS256, userinfo для HS256 + fallback) |
| `get_auth_user(request)` | Унифицированный диспатчер по `auth_mode` |
| `get_current_user_from_provider(request)` | Резолвит `AuthUser` → DB `User`; автосоздание для Supabase, dev-user для none |

#### Поведение по auth_mode

| Режим | Поведение |
|-------|----------|
| `none` | Возвращает dev-user (анонимный) |
| `local` | Локальный JWT. Desktop dev-fallback если нет токена + `allow_desktop_dev_fallback` |
| `supabase` | Только Supabase JWT |
| `both` | Пробует local → Supabase → desktop fallback |

---

### 4.5. Модели базы данных — models.py

**Файл:** `src/app/db/models.py`

**Назначение:** SQLAlchemy-модели для заметок, чанков, связей, тегов, источников, сообщений, действий, групп, файлов, таблиц синхронизации.

#### Модель: `Note` (таблица `notes`)

| Столбец | Тип | Nullable | Default | Index | FK |
|---------|-----|----------|---------|-------|----|
| `id` | String | PK | uuid4 | PK | — |
| `user_id` | String | True | — | index | `users.id` CASCADE |
| `title` | String | False | — | — | — |
| `style_theme` | String | False | `"clean"` | — | — |
| `layout_hints` | Text | False | `"{}"` | — | — |
| `blocks_json` | Text | False | `"[]"` | — | — |
| `passport_json` | Text | False | `"{}"` | — | — |
| `created_at` | DateTime | False | utcnow | — | — |
| `updated_at` | DateTime | False | utcnow (onupdate) | — | — |
| `revision` | Integer | False | `0` | — | — |
| `tombstone` | Boolean | False | `False` | — | — |
| `client_origin` | String | True | — | — | — |
| `last_client_ts` | DateTime | True | — | — | — |

Relationships:
- `chunks` → NoteChunk (cascade="all, delete-orphan")
- `tags` → NoteTag (cascade="all, delete-orphan")
- `sources` → NoteSource (cascade="all, delete-orphan")
- `links_from` → NoteLink (FK=from_id, cascade="all, delete-orphan")
- `links_to` → NoteLink (FK=to_id, cascade="all, delete-orphan")
- `files` → FileAsset (cascade="all, delete-orphan")
- `user` → User

#### Модель: `NoteChunk` (таблица `note_chunks`)

| Столбец | Тип | Nullable | Default | Index | FK |
|---------|-----|----------|---------|-------|----|
| `id` | String | PK | uuid4 | — | — |
| `note_id` | String | False | — | index | `notes.id` CASCADE |
| `idx` | Float | False | — | — | — |
| `text` | Text | False | — | — | — |
| `embedding` | Text | False | — | — | — |

#### Модель: `NoteLink` (таблица `note_links`)

| Столбец | Тип | Nullable | Default | Index | FK |
|---------|-----|----------|---------|-------|----|
| `id` | String | PK | uuid4 | — | — |
| `from_id` | String | False | — | index | `notes.id` CASCADE |
| `to_id` | String | False | — | index | `notes.id` CASCADE |
| `reason` | String | True | — | — | — |
| `confidence` | Float | True | — | — | — |
| `created_at` | DateTime | False | utcnow | — | — |

Уникальное ограничение: `(from_id, to_id, reason)`

#### Модель: `NoteTag` (таблица `note_tags`)

| Столбец | Тип | Nullable | Default | Index | FK |
|---------|-----|----------|---------|-------|----|
| `id` | String | PK | uuid4 | — | — |
| `note_id` | String | False | — | index | `notes.id` CASCADE |
| `tag` | String | False | — | index | — |
| `weight` | Float | — | `1.0` | — | — |

Уникальное ограничение: `(note_id, tag)`

#### Модель: `Source` (таблица `sources`)

| Столбец | Тип | Nullable | Default |
|---------|-----|----------|---------|
| `id` | String | PK | uuid4 |
| `url` | Text | False, unique | — |
| `domain` | String | False | — |
| `title` | Text | False | — |
| `summary` | Text | False | `""` |
| `published_at` | String | True | — |

#### Модель: `NoteSource` (таблица `note_sources`)

| Столбец | Тип | Index | FK |
|---------|-----|-------|----|
| `id` | String PK | — | — |
| `note_id` | String | index | `notes.id` CASCADE |
| `source_id` | String | — | `sources.id` CASCADE |
| `relevance` | Float, default 1.0 | — | — |

#### Модель: `MessageLog` (таблица `messages`)

| Столбец | Тип |
|---------|-----|
| `id` | String PK |
| `role` | String, not null |
| `text` | Text, not null |
| `created_at` | DateTime |

#### Модель: `ActionLog` (таблица `action_log`)

| Столбец | Тип |
|---------|-----|
| `id` | String PK |
| `hash` | String, unique, not null |
| `payload` | Text, not null |
| `created_at` | DateTime |

#### Модель: `GroupPreference` (таблица `group_preferences`)

| Столбец | Тип | Default |
|---------|-----|---------|
| `key` | String PK | — |
| `label` | String | `"Группа"` |
| `color` | String | `"#8b5cf6"` |
| `created_at` | DateTime | utcnow |
| `updated_at` | DateTime | utcnow |

#### Модель: `FileAsset` (таблица `files`)

| Столбец | Тип | Nullable | Index | FK |
|---------|-----|----------|-------|----|
| `id` | String | PK | — | — |
| `note_id` | String | True | — | `notes.id` SET NULL |
| `user_id` | String | True | index | `users.id` CASCADE |
| `kind` | String | False | — | — |
| `mime` | String | False | — | — |
| `filename` | String | False | — | — |
| `size` | Integer | False | — | — |
| `path_original` | String | False | — | — |
| `path_preview` | String | True | — | — |
| `path_doc_html` | String | True | — | — |
| `path_waveform` | String | True | — | — |
| `path_slides_json` | String | True | — | — |
| `path_slides_dir` | String | True | — | — |
| `path_excel_summary` | String | True | — | — |
| `path_excel_charts_json` | String | True | — | — |
| `path_excel_charts_dir` | String | True | — | — |
| `path_excel_chart_sheets_json` | String | True | — | — |
| `excel_charts_pages_keep` | Text | True | — | — |
| `excel_default_sheet` | String | True | — | — |
| `path_video_original` | String | True | — | — |
| `path_video_poster` | String | True | — | — |
| `path_code_original` | String | True | — | — |
| `path_markdown_raw` | String | True | — | — |
| `hash_sha256` | String | True | — | — |
| `upload_op_id` | String | True | index | — |
| `width` | Integer | True | — | — |
| `height` | Integer | True | — | — |
| `pages` | Integer | True | — | — |
| `duration` | Float | True | — | — |
| `words` | Integer | True | — | — |
| `slides_count` | Integer | True | — | — |
| `video_duration` | Float | True | — | — |
| `video_width` | Integer | True | — | — |
| `video_height` | Integer | True | — | — |
| `video_mime` | String | True | — | — |
| `code_language` | String | True | — | — |
| `code_line_count` | Integer | True | — | — |
| `markdown_line_count` | Integer | True | — | — |
| `created_at` | DateTime | False | — | — |

#### Модель: `SyncOutbox` (таблица `sync_outbox`)

| Столбец | Тип | Index | FK |
|---------|-----|-------|----|
| `id` | String PK | — | — |
| `op_type` | String, not null | index | — |
| `user_id` | String | index | `users.id` SET NULL |
| `note_id` | String | index | `notes.id` SET NULL |
| `payload_json` | Text, default `"{}"` | — | — |
| `status` | String, default `"pending"` | index | — |
| `tries` | Integer, default 0 | — | — |
| `last_error` | Text | — | — |
| `created_at` | DateTime | index | — |
| `updated_at` | DateTime | — | — |

#### Модель: `SyncNoteMap` (таблица `sync_note_map`)

| Столбец | Тип | Index | FK |
|---------|-----|-------|----|
| `local_note_id` | String PK | — | `notes.id` CASCADE |
| `remote_note_id` | String, unique | index | — |
| `created_at` | DateTime | — | — |
| `updated_at` | DateTime | — | — |

#### Модель: `SyncConflict` (таблица `sync_conflicts`)

| Столбец | Тип | Index | FK |
|---------|-----|-------|----|
| `id` | String PK | — | — |
| `local_note_id` | String | index | `notes.id` SET NULL |
| `remote_note_id` | String | index | — |
| `kind` | String, default `"note_conflict"` | — | — |
| `payload_json` | Text, default `"{}"` | — | — |
| `created_at` | DateTime | index | — |

---

### 4.6. Сессия БД — session.py

**Файл:** `src/app/db/session.py`

**Назначение:** Создание SQLAlchemy engine и фабрики сессий.

- Нормализует `postgres://` → `postgresql://`
- SQLite: `check_same_thread=False`
- `pool_pre_ping=True`
- `expire_on_commit=False`

**`get_session()`** — контекстный менеджер:
- Yield: `SessionLocal` сессия
- Автокоммит при успехе, rollback при исключении, всегда close

---

### 4.7. Миграции — migrate.py

**Файл:** `src/app/db/migrate.py`

**Назначение:** Запуск ALTER TABLE миграций при старте для добавления отсутствующих столбцов. Использует SQLite PRAGMA для обнаружения.

**Функция `upgrade()`** добавляет столбцы если отсутствуют:

**Таблица `files`:** `path_waveform`, `path_doc_html`, `path_slides_json`, `path_slides_dir`, `path_excel_summary`, `excel_default_sheet`, `duration`, `words`, `slides_count`, `path_excel_charts_json`, `path_excel_charts_dir`, `path_excel_chart_sheets_json`, `excel_charts_pages_keep`, `path_video_original`, `path_video_poster`, `video_duration`, `video_width`, `video_height`, `video_mime`, `path_code_original`, `code_language`, `code_line_count`, `path_markdown_raw`, `markdown_line_count`, `user_id`, `upload_op_id` (с индексом)

**Таблица `sync_outbox`:** `user_id` (с индексом, backfill из notes)

**Таблица `users`:** `username` (с unique индексом, генерация из email для существующих), `failed_login_count`, `locked_until`, `supabase_id` (с unique индексом)

**Таблица `notes`:** `user_id`, `revision`, `tombstone`, `client_origin`, `last_client_ts`

Завершается вызовом `Base.metadata.create_all()` для создания отсутствующих таблиц.

---

### 4.8. API заметок — notes.py

**Файл:** `src/app/api/notes.py`

**Назначение:** CRUD операции с заметками, полнотекстовый поиск, TF-IDF переиндексация, постановка в очередь синхронизации.

#### Эндпоинты

| Метод | Путь | Аутентификация | Ответ | Описание |
|-------|------|----------------|-------|----------|
| GET | `/api/tags` | Bearer | `{"tags": [...]}` | Все уникальные теги текущего пользователя |
| GET | `/api/notes` | Bearer | `NoteListResponse` | Пагинированный список (limit/offset), фильтр по user_id |
| GET | `/api/notes/search/full` | Bearer | `{"items": [...], "total", "query"}` | TF-IDF + поиск по заголовку + поиск по именам файлов |
| GET | `/api/notes/{note_id}` | Bearer | `NoteDetail` | Полная заметка с блоками, связями, тегами, источниками |
| POST | `/api/notes` | Bearer | `NoteDetail` (201) | Создание заметки, переиндексация, постановка в sync |
| PATCH | `/api/notes/{note_id}` | Bearer | `NoteDetail` | Частичное обновление (title, style, layout, blocks, passport) |
| DELETE | `/api/notes/{note_id}` | Bearer | `{"status": "ok"}` | Удаление заметки, удаление из TF-IDF индекса |

#### Внутренние функции

| Функция | Описание |
|---------|----------|
| `_serialize_summary(note)` | Преобразование Note → NoteSummary |
| `_serialize_detail(note, session, user_id)` | Преобразование Note → NoteDetail (связи фильтруются по владельцу) |
| `_ensure_note_owner(note, user, session)` | Проверка/назначение владельца. 404 если чужая заметка |
| `_reindex_note(session, note)` | Перечанкинг блоков, upsert в TF-IDF индекс |
| `_blocks_to_text(blocks)` | Извлечение чистого текста из всех типов блоков |
| `_load_blocks(raw_json)` | JSON парсинг + валидация схемы через `parse_blocks` |

#### Операции синхронизации

- `OP_CREATE_NOTE` — при создании
- `OP_UPDATE_NOTE` — при обновлении (с patch + snapshot)
- `OP_DELETE_NOTE` — при удалении

---

### 4.9. API аутентификации — auth.py

**Файл:** `src/app/api/routes/auth.py`

**Назначение:** Регистрация, логин (по username или email), обновление токена, выход, верификация email, мост Supabase, смена пароля.

#### Эндпоинты

| Метод | Путь | Аутентификация | Rate-лимит | CSRF | Ответ |
|-------|------|----------------|------------|------|-------|
| GET | `/login` | Нет | Нет | Нет | HTML |
| GET | `/register` | Нет | Нет | Нет | HTML |
| GET | `/auth/verify` | Нет | Нет | Нет | Redirect |
| POST | `/auth/register` | Нет | Да (register) | Нет | `AuthOkResponse` (201) |
| POST | `/auth/resend-verification` | Нет | Да (1/мин/ip+email) | Нет | `AuthOkResponse` |
| POST | `/auth/login` | Нет | Да (login) | Нет | `AuthOkResponse` |
| POST | `/auth/supabase/session` | Supabase token | Нет | Нет | `AuthOkResponse` |
| POST | `/auth/refresh` | Refresh cookie | Нет | Да | `RefreshResponse` |
| POST | `/auth/logout` | Refresh cookie | Нет | Да | 204 |
| GET | `/auth/username-available` | Нет | Нет | Нет | `{"available": bool}` |
| POST | `/auth/change-password` | Bearer | Нет | Да | `AuthOkResponse` |

#### Поток регистрации

1. Проверка rate limit по IP
2. Проверка уникальности email (case-insensitive)
3. Валидация пароля через `validate_password`
4. Генерация username (из explicit или email prefix)
5. Создание User с хешированным паролем
6. Миграция первого пользователя: привязка orphan заметок/файлов
7. Отправка verification email

#### Поток логина

1. Rate limit по IP
2. Поиск user по username ИЛИ email (case-insensitive)
3. Проверка блокировки аккаунта
4. Верификация пароля
5. При ошибке: инкремент `failed_login_count`, блокировка после 10 попыток (15 мин)
6. При успехе: сброс ошибок, создание RefreshToken, установка cookies

#### Поток обновления токена

1. Проверка CSRF
2. Валидация refresh_token cookie
3. Обнаружение повторного использования (rotated_at установлен) → отзыв всей цепочки
4. Ротация: старый помечается rotated, создаётся новый
5. Возврат нового access token с email/username claims

#### Мост Supabase

- Требует `auth_mode` в (supabase, both)
- Валидирует Supabase токен, резолвит/создаёт локального пользователя
- Создаёт локальный RefreshToken + cookies

#### Вспомогательные функции

| Функция | Описание |
|---------|----------|
| `_cookie_secure_for_request(request)` | Разрешает не-secure cookies для localhost |
| `_fingerprint_hash(request)` | SHA256 от IP + user-agent |
| `_build_unique_username(session, email, explicit_username)` | Уникальность с суффикс-инкрементом |

---

### 4.10. API пользователей — users.py

**Файл:** `src/app/api/routes/users.py`

**Назначение:** Получение и обновление профиля текущего пользователя.

| Метод | Путь | Аутентификация | Ответ |
|-------|------|----------------|-------|
| GET | `/api/users/me` | Bearer | `UserProfile` |
| PATCH | `/api/users/me` | Bearer | `UserProfile` |

**`UserUpdate` поля:** `display_name` (optional), `avatar_url` (optional)

---

### 4.11. API синхронизации — sync.py

**Файл:** `src/app/api/sync.py`

**Назначение:** Статус синхронизации и ручной триггер.

| Метод | Путь | Аутентификация | Ответ |
|-------|------|----------------|-------|
| GET | `/api/sync/status` | Bearer | dict (pending/failed/done/conflicts + режим) |
| POST | `/api/sync/trigger` | Bearer | `{"ok": bool, "pushed", "failed", "pulled", "conflicts"}` |

---

### 4.12. API загрузки файлов — upload.py

**Файл:** `src/app/api/upload.py`

**Назначение:** Загрузка файлов (обычные, аудио, транскрипция). Возвращает блоки + метаданные файлов.

#### Константы

| Константа | Значение |
|-----------|----------|
| `MAX_UPLOAD_SIZE` | 500 МБ |

#### Эндпоинты

| Метод | Путь | Аутентификация | Ответ |
|-------|------|----------------|-------|
| POST | `/api/upload` | Bearer | `UploadResponse` |
| POST | `/api/upload/audio` | Bearer | `UploadResponse` |
| POST | `/api/transcribe` | Bearer | PlainText (заглушка) |

#### Поток загрузки

1. Проверка `X-Upload-Op-Id` / `X-Desktop-Op-Id` для идемпотентности
2. Для каждого файла: проверка существующего (по op_id) или вызов `file_service.save_upload()`
3. Построение response-блоков и file payloads
4. Постановка `OP_UPLOAD_FILE` в sync outbox по каждому файлу
5. Аудит `FILE_UPLOAD`

---

### 4.13. API раздачи файлов — files.py

**Файл:** `src/app/api/files.py`

**Назначение:** Раздача оригиналов, превью, документов, слайдов, видео, аудио-стримов, кода, markdown, Excel, PDF-страниц, waveform, графиков.

#### Эндпоинты

| Метод | Путь | Ответ |
|-------|------|-------|
| GET | `/files/{id}/original` | FileResponse |
| GET | `/files/{id}/preview` | FileResponse (webp) |
| GET | `/files/{id}/doc.html` | HTMLResponse |
| GET | `/files/{id}/slides.json` | JSON metadata |
| GET | `/files/{id}/slide/{index}` | image/webp |
| GET | `/files/{id}/video/source` | FileResponse (video) |
| GET | `/files/{id}/video/poster.webp` | image/webp |
| GET | `/files/{id}/code/meta` | JSON |
| GET | `/files/{id}/code/preview` | text/plain |
| GET | `/files/{id}/code/raw` | text/plain |
| GET | `/files/{id}/md/preview` | text/plain |
| GET | `/files/{id}/md/raw` | text/plain |
| GET | `/files/{id}/excel/summary.json` | JSON |
| GET | `/files/{id}/excel/sheet/{name}.json` | JSON (windowed rows) |
| GET | `/files/{id}/excel/sheet/{name}.csv` | text/csv streaming |
| GET | `/files/{id}/excel/charts.json` | JSON |
| GET | `/files/{id}/excel/charts/sheets.json` | JSON |
| GET | `/files/{id}/excel/charts-anchors.json` | JSON |
| POST | `/files/{id}/excel/charts/pages` | JSON |
| GET | `/files/{id}/excel/chart/{index}` | image/webp |
| GET | `/files/{id}/waveform` | JSON |
| GET | `/files/{id}/stream` | StreamingResponse (range-поддержка) |
| GET | `/files/{id}/page/{page_num}` | image/webp (PDF page) |

Все файловые эндпоинты требуют Bearer или Refresh cookie аутентификации.

Стриминг поддерживает HTTP Range (206 Partial Content), чанки по 64KB.

PDF-рендеринг через PyMuPDF или pdf2image, кеширование в `PAGES_DIR/{file_id}/{page}_{scale}.webp`.

---

### 4.14. API коммитов — commit.py

**Файл:** `src/app/api/commit.py`

**Назначение:** Пакетное применение draft-действий агента.

| Метод | Путь | Аутентификация | Ответ |
|-------|------|----------------|-------|
| POST | `/api/commit` | Bearer | `CommitResponse {applied, notes_changed}` |

Поддерживаемые действия:
- `InsertBlockAction` — вставка блока после указанного
- `UpdateBlockAction` — обновление блока по id
- `MoveBlockAction` — перемещение блока
- `AddTagAction` — добавление тега
- `RemoveTagAction` — удаление тега
- `AddLinkAction` — создание связи
- `SetStyleAction` — установка стиля + layout_hints

---

### 4.15. API чата — chat.py

**Файл:** `src/app/api/chat.py`

| Метод | Путь | Аутентификация | Ответ |
|-------|------|----------------|-------|
| POST | `/api/chat` | Bearer | `ChatResponse {reply, draft}` |

Запрос: `ChatRequest` — `text` (мин. 1 символ), `noteId` (опционально)

---

### 4.16. API графа — graph.py

**Файл:** `src/app/api/graph.py`

**Назначение:** Данные графа знаний (ноды с группами, рёбра из связей + общих тегов).

#### Константы

| Константа | Значение |
|-----------|----------|
| `DEFAULT_COLOR` | `"#8b5cf6"` |
| `DEFAULT_LABEL` | `"Без группы"` |
| `TAG_EDGE_MAX_NOTES` | `200` |

#### Эндпоинты

| Метод | Путь | Ответ |
|-------|------|-------|
| GET | `/api/graph` | `{nodes, edges}` |
| GET | `/api/graph/groups` | `{groups}` |
| POST | `/api/graph/groups/{cluster}` | Обновление цвета группы |
| POST | `/api/graph/groups/{cluster}/label` | Обновление метки группы |

#### Построение графа

- **Ручные группы:** из passport `group` поля заметки
- **Компонентные группы:** связные компоненты через NoteLinks
- **Тег-рёбра:** заметки с общими тегами (до TAG_EDGE_MAX_NOTES попарных рёбер)
- `sizeScore` ноды = текст/число блоков + `sizeWeight` из layout hints

---

### 4.17. API экспорта — export.py

**Файл:** `src/app/api/export.py`

| Метод | Путь | Ответ |
|-------|------|-------|
| GET | `/api/export/docx/{note_id}` | `{"status": "todo"}` (заглушка) |

---

### 4.18. API резолва URL — resolve.py

**Файл:** `src/app/api/resolve.py`

| Метод | Путь | Аутентификация | Ответ |
|-------|------|----------------|-------|
| POST | `/api/resolve/youtube` | Bearer | `{block}` (YouTubeBlock dict) |
| POST | `/api/resolve/tiktok` | Bearer | `{url, videoId}` |

**YouTube:** youtube.com, youtu.be, youtube-nocookie.com. Извлекает videoId (11 символов) + start time.

**TikTok:** tiktok.com, vt.tiktok.com, vm.tiktok.com. Короткие URL резолвятся через HTTP redirect.

---

### 4.19. Pydantic-модели заметок — note_models.py

**Файл:** `src/app/api/note_models.py`

| Модель | Поля |
|--------|------|
| `LinkPayload` | id, fromId, toId, title, reason, confidence |
| `SourcePayload` | id, url, title, domain, published_at, summary |
| `NoteSummary` | id, title, styleTheme, createdAt, updatedAt |
| `NoteDetail` | extends NoteSummary + blocks, layoutHints, passport, tags, linksFrom, linksTo, sources |
| `NoteListResponse` | items, total, limit, offset |
| `NoteCreateRequest` | title (required), styleTheme, layoutHints, blocks, passport |
| `NoteUpdateRequest` | all optional: title, styleTheme, layoutHints, blocks, passport |

---

### 4.20. Модели блоков — block_models.py

**Файл:** `src/app/agent/block_models.py`

**Назначение:** Типизированные Pydantic-модели для всех 22 типов блоков редактора.

#### Data-модели

| Модель | Поля |
|--------|------|
| `Annotations` | bold, italic, underline, strike, code, href |
| `RichText` | text + annotations |
| `HeadingData` | level (1–3), text |
| `ParagraphData` | parts: List[RichText] |
| `ListData` | items: List[RichText] |
| `QuoteData` | text, cite |
| `ImageData` | src, full, alt, w, h |
| `AudioData` | src, mime, duration, waveform, transcript, view (mini/expanded) |
| `VideoData` | src, poster, durationSec, width, height, mime, caption, view |
| `DocMeta` | pages, slides, size, words |
| `DocData` | kind (pdf/docx/rtf/pptx/txt), src, title, preview, meta, view |
| `SheetData` | kind (xlsx/csv), src, sheets, rows |
| `SlidesData` | kind (pptx), src, slides, preview, count, view |
| `CodeData` | src, previewUrl, filename, language, sizeBytes, lineCount, view |
| `MarkdownData` | src, previewUrl, filename, sizeBytes, lineCount, view |
| `ArchiveData` | src, tree: List[ArchiveEntry] |
| `LinkData` | url, title, desc, image |
| `TableData` | kind (optional), src (optional), summary (optional), view, activeSheet, charts, rows |
| `YouTubeData` | videoId, title, startSec, view |
| `InstagramData` | url |
| `TikTokData` | url, videoId |
| `SourceData` | url, title, domain, published_at, summary |
| `SummaryData` | dateISO, text |
| `TodoItem` | id, text, done |
| `TodoData` | items: List[TodoItem] |
| `DividerData` | (пустой) |

#### Типы блоков (22 шт.)

`HeadingBlock`, `ParagraphBlock`, `BulletListBlock`, `NumberListBlock`, `QuoteBlock`, `ImageBlock`, `AudioBlock`, `VideoBlock`, `DocBlock`, `SlidesBlock`, `SheetBlock`, `CodeBlock`, `ArchiveBlock`, `LinkBlock`, `TableBlock`, `MarkdownBlock`, `YouTubeBlock`, `InstagramBlock`, `TikTokBlock`, `SourceBlock`, `SummaryBlock`, `TodoBlock`, `DividerBlock`

`BlockModel = Union[...]` всех 22 типов.

#### Функции

| Функция | Описание |
|---------|----------|
| `dump_block(block)` | dict с `exclude_none=True, by_alias=True` |
| `dump_blocks(blocks)` | Список dict |
| `parse_blocks(raw_blocks)` | Валидация списка dict → типизированные блоки (Pydantic v1/v2) |

---

### 4.21. Типы действий агента — draft_types.py

**Файл:** `src/app/agent/draft_types.py`

| Тип действия | Поля |
|--------------|------|
| `InsertBlockAction` | type="insert_block", noteId, afterId, block |
| `UpdateBlockAction` | type="update_block", noteId, id, patch |
| `MoveBlockAction` | type="move_block", noteId, id, afterId |
| `AddTagAction` | type="add_tag", noteId, tag, confidence |
| `RemoveTagAction` | type="remove_tag", noteId, tag |
| `AddLinkAction` | type="add_link", noteId, fromId, toId, reason, confidence |
| `SetStyleAction` | type="set_style", noteId, styleTheme, layoutHints |

**AgentReply:** `reply: str`, `draft: list[DraftAction]`

---

### 4.22. Оркестратор агента — orchestrator.py

**Файл:** `src/app/agent/orchestrator.py`

**Заглушка:** Возвращает статический ответ и пустой draft. Совместим с будущей GPT-интеграцией.

```python
def handle_user_message(text: str, note_id: Optional[str]) -> AgentReply
```

---

### 4.23. Движок синхронизации — sync_engine.py

**Файл:** `src/app/services/sync_engine.py`

**Назначение:** Фоновый воркер, outbox-очередь, push/pull к удалённому серверу, разрешение конфликтов (LWW с копиями конфликтов).

#### Константы

| Константа | Значение |
|-----------|----------|
| `OP_CREATE_NOTE` | Создание заметки |
| `OP_UPDATE_NOTE` | Обновление заметки |
| `OP_DELETE_NOTE` | Удаление заметки |
| `OP_COMMIT` | Пакетная операция |
| `OP_UPLOAD_FILE` | Загрузка файла |
| `STATUS_PENDING` | Ожидает |
| `STATUS_DONE` | Выполнено |
| `STATUS_FAILED` | Ошибка |
| `_MAX_RETRIES_BEFORE_BACKOFF` | 5 |

#### Функции

| Функция | Описание |
|---------|----------|
| `start_sync_worker_once()` | Запуск daemon-потока (если remote-sync + bearer token), поллинг каждые `sync_poll_seconds` |
| `enqueue_sync_operation(session, op_type, payload, note_id, user_id)` | Добавление в SyncOutbox если desktop/sync enabled и очередь не полна |
| `trigger_sync_now(access_token, user_id)` | Push + Pull цикл под lock |
| `get_sync_status(user_id)` | Счётчики pending/failed/done/conflicts |
| `_build_client(access_token)` | Создание httpx.Client с bearer token |
| `_push_outbox(session, client, user_id)` | Обработка pending/failed элементов |
| `_flush_create_note(...)` | POST `/api/notes` на remote, сохранение маппинга |
| `_flush_update_note(...)` | PATCH `/api/notes/{id}`, create fallback при 404 |
| `_flush_delete_note(...)` | DELETE `/api/notes/{id}`, 404 допустим |
| `_flush_commit(...)` | POST `/api/commit` с маппированными ID |
| `_flush_upload_file(...)` | POST `/api/upload` с бинарными данными |
| `_pull_remote_changes(...)` | Пагинация `/api/notes`, upsert более новых |
| `_create_conflict_copy(...)` | Создание копии + SyncConflict |
| `_upsert_local_note_from_remote(...)` | Создание/обновление локальной заметки из remote |

#### Разрешение конфликтов

Стратегия **LWW** (Last Write Wins):
- Если у local есть pending операции и remote новее → создаётся копия конфликта, pending операции сбрасываются

---

### 4.24. Сервис файлов — files.py (services)

**Файл:** `src/app/services/files.py`

**Назначение:** Обработка загруженных файлов: превью, метаданные для изображений, PDF, DOCX, RTF, PPTX, Excel, аудио, видео, кода, markdown.

#### Env-переменные

- `OVC_UPLOAD_ROOT` — кастомная директория для загрузок

#### Структура директорий

`UPLOAD_ROOT/{original, preview, pages, doc_html, waveform, slides, slides_meta, excel_summary, excel_charts, excel_charts_meta, videos, code, markdown}`

#### Лимиты размеров

| Тип | Лимит |
|-----|-------|
| Image | 15 МБ |
| PDF | 50 МБ |
| Doc (DOCX/RTF) | 30 МБ |
| Audio | 50 МБ |
| PPTX | 50 МБ |
| Excel | 40 МБ |
| Video | 200 МБ |
| Code | 5 МБ |

#### Ключевые константы

| Константа | Значение |
|-----------|----------|
| `AUDIO_WAVE_POINTS` | 256 |
| `SLIDES_TARGET_WIDTH` | 1600 |
| `EXCEL_PREVIEW_ROWS` | 5 |
| `EXCEL_WINDOW_LIMIT` | 1000 |
| `MAX_CODE_LINES` | 10 000 |
| `CODE_PREVIEW_LINES` | 300 |
| `MARKDOWN_PREVIEW_MAX_BYTES` | 200 000 |
| `CODE_GZIP_THRESHOLD` | 10 МБ |

#### Классификация файлов (`_classify_file`)

Поддерживаемые типы: `image`, `pdf`, `docx`, `rtf`, `pptx`, `xlsx`, `xls`, `csv`, `audio`, `video`, `code`, `markdown`

#### Ключевые функции

| Функция | Описание |
|---------|----------|
| `save_upload(session, upload, note_id, user_id, upload_op_id)` | Главный вход: классификация, сохранение, генерация превью/метаданных, создание FileAsset |
| `_generate_image_preview(data)` | Thumbnail до 1600x1600 webp |
| `_render_pdf_page(data, page_num, scale)` | PyMuPDF или pdf2image → webp |
| `_generate_pdf_preview(data, file_id, pages)` | Рендер первой страницы |
| `_convert_docx_to_html(data)` | Через mammoth |
| `_convert_rtf_to_html(data)` | Через striprtf |
| `_extract_audio_metadata(data, mime)` | Duration через mutagen, PCM waveform |
| `extract_video_meta(path)` | Duration/width/height через ffprobe |
| `render_video_poster(video_path, out_path)` | Кадр через ffmpeg |
| `_convert_pptx_to_slides(original_path, file_id)` | LibreOffice → PDF → slide images |
| `_prepare_excel_summary(kind, original_path, file_id)` | Листы, заголовки, счётчики строк |
| `_read_excel_window(asset, sheet_name, offset, limit)` | Пагинированное окно данных |
| `_build_block(asset)` | Создание типизированного block dict из FileAsset |

#### Опциональные зависимости

bleach (санитизация HTML), mammoth (DOCX), striprtf (RTF), mutagen (аудио метаданные), pypdf (PDF подсчёт страниц), fitz/PyMuPDF (PDF рендеринг), pdf2image (PDF fallback)

---

### 4.25. Политика паролей — password_policy.py

**Файл:** `src/app/services/password_policy.py`

#### Чёрный список паролей

`12345678, 123456789, 1234567890, qwerty123, password, password123, admin123, letmein, welcome123, iloveyou`

#### Функции

| Функция | Описание |
|---------|----------|
| `validate_password(password: str) -> List[str]` | Возвращает список ошибок: длина, классы символов, специфические требования, чёрный список |
| `password_policy_hint() -> str` | Человекочитаемая подсказка |

---

### 4.26. Rate-лимитер — rate_limit.py

**Файл:** `src/app/services/rate_limit.py`

#### Классы

**`RateLimiter`** — in-memory sliding window:
- `allow(key: str, limit: int, window_seconds: int) -> bool`

**`LoginLockout`** — блокировка после N ошибок:
- `register_failure(email, max_failures, window_seconds, lock_seconds)`
- `is_locked(email) -> tuple[bool, float]`

---

### 4.27. Аудит-логирование — audit.py

**Файл:** `src/app/services/audit.py`

**Функция:** `log_event(session, event, *, user_id, request, metadata)` → создаёт `AuditLog` запись с IP, user-agent, метаданными

**Типы событий:** `NOTE_READ`, `NOTE_CREATE`, `NOTE_UPDATE`, `NOTE_DELETE`, `FILE_UPLOAD`, `REGISTER_SUCCESS`, `REGISTER_EMAIL_EXISTS`, `LOGIN_SUCCESS`, `LOGIN_FAIL`, `LOGIN_LOCKED`, `LOGOUT`, `TOKEN_ROTATE`, `TOKEN_REUSE`, `EMAIL_VERIFIED`, `EMAIL_VERIFY_SENT`, `EMAIL_VERIFY_RESENT`, `PASSWORD_CHANGE_SUCCESS`, `PASSWORD_CHANGE_FAIL`, `SUPABASE_SESSION_BRIDGE`, `LEGACY_DATA_MIGRATED`

---

### 4.28. TF-IDF поиск — tfidf_index.py

**Файл:** `src/app/rag/tfidf_index.py`

**Назначение:** In-memory TF-IDF индекс через scikit-learn. Потокобезопасный (threading.Lock).

| Метод | Описание |
|-------|----------|
| `upsert(note_id, chunks: List[Tuple[str, str]])` | Замена чанков заметки, перестройка матрицы |
| `remove(note_id)` | Удаление из индекса, перестройка |
| `search(query, limit=8)` | Косинусное сходство, возвращает note_id, chunk_id, text, score |
| `_rebuild()` | Переобучение TfidfVectorizer |

Синглтон: `index = TFIDFIndex()`

---

### 4.29. Чанкинг текста — chunking.py

**Файл:** `src/app/rag/chunking.py`

| Функция | Описание |
|---------|----------|
| `chunk_markdown(text, size=800, overlap=120)` | Скользящее окно с перекрытием |
| `window(iterable, size)` | Группировка по размеру |

---

### 4.30. Модель User — user.py

**Файл:** `src/app/models/user.py`

Таблица `users`:

| Столбец | Тип | Nullable | Default | Index | Unique |
|---------|-----|----------|---------|-------|--------|
| `id` | String | PK | uuid4 | PK | — |
| `username` | String | False | — | index | unique |
| `email` | String | True | — | index | unique |
| `password_hash` | String | False | — | — | — |
| `supabase_id` | String | True | — | index | unique |
| `display_name` | String | True | — | — | — |
| `avatar_url` | String | True | — | — | — |
| `failed_login_count` | Integer | False | `0` | — | — |
| `locked_until` | DateTime | True | — | — | — |
| `created_at` | DateTime | False | utcnow | — | — |
| `updated_at` | DateTime | False | utcnow (onupdate) | — | — |
| `is_active` | Boolean | False | `True` | — | — |
| `role` | String | False | `"user"` | — | — |

Relationships: `refresh_tokens` (cascade all, delete-orphan), `notes`, `files`

---

### 4.31. Модель RefreshToken — session.py (модели)

**Файл:** `src/app/models/session.py`

Таблица `refresh_tokens`:

| Столбец | Тип | Nullable | Index | FK |
|---------|-----|----------|-------|----|
| `id` | String | PK | — | — |
| `user_id` | String | False | index | `users.id` CASCADE |
| `token_hash` | String | False | index | — |
| `created_at` | DateTime | False | — | — |
| `expires_at` | DateTime | False | index | — |
| `rotated_at` | DateTime | True | — | — |
| `revoked_at` | DateTime | True | — | — |
| `fingerprint_hash` | String | True | — | — |
| `ip` | String | True | — | — |
| `user_agent` | String | True | — | — |

---

### 4.32. Модель AuditLog — audit.py (модели)

**Файл:** `src/app/models/audit.py`

Таблица `audit_logs`:

| Столбец | Тип | Nullable | Index | FK |
|---------|-----|----------|-------|----|
| `id` | String | PK | — | — |
| `user_id` | String | True | index | `users.id` SET NULL |
| `event` | String | False | index | — |
| `ip` | String | True | — | — |
| `user_agent` | String | True | — | — |
| `event_meta` | JSON (JSONB на PostgreSQL) | True | — | — |
| `created_at` | DateTime | False | index | — |

---

### 4.33. Схемы аутентификации — schemas/auth.py

**Файл:** `src/app/schemas/auth.py`

| Модель | Поля |
|--------|------|
| `RegisterRequest` | username (optional, 3–24), password, email (EmailStr) |
| `LoginRequest` | identifier (username или email), password |
| `RefreshResponse` | accessToken, tokenType |
| `ForgotRequest` | email |
| `ResetRequest` | token, password |
| `AuthOkResponse` | ok, detail (optional) |
| `ChangePasswordRequest` | old_password, new_password |

---

### 4.34. Схемы пользователей — schemas/user.py

**Файл:** `src/app/schemas/user.py`

| Модель | Поля |
|--------|------|
| `UserProfile` | id, username, email, isActive, role, displayName, avatarUrl |
| `UserUpdate` | displayName, avatarUrl (оба optional) |

---

## 5. Фронтенд

---

### 5.1. editor.js — Главный контроллер редактора

**Файл:** `src/static/js/editor.js`

**Назначение:** Оркестрация всего редактирования заметки: загрузка, рендеринг, сохранение, манипуляции с блоками, drag-and-drop, управление фокусом/выделением, инициализация всех суб-модулей.

#### Импорты

`renderNote` из `blocks_render.js`, `initToolbar`, `clearSelectionSnapshot`, `rememberSelection` из `toolbar.js`, `initInlineBubble` из `inline_bubble.js`, `initPalette` из `palette.js`, `initSmartInsert` из `smart_insert.js`, `initInspector` из `inspector.js`, `uuid` из `utils.js`, `initUploader` из `uploader.js`, `initPdfViewers` из `pdf_viewer.js`, `initAudioPlayers` из `audio_player.js`, `initAudioRecorder` из `audio_recorder.js`, `initWordViewers` из `word_viewer.js`, `initSlidesViewers` из `slides_viewer.js`, `initTableViewers` из `table_viewer.js`, `initMarkdownViewers` из `markdown_viewer.js`, `initConnectionsPanel` из `connections_panel.js`, `initMiniGraph` из `mini-graph.js`

#### Состояние

| Переменная | Описание |
|-----------|----------|
| `noteState` | `{ id, title, styleTheme, blocks, layoutHints, passport, tags, linksFrom, linksTo, sources }` |
| `SAVE_DEBOUNCE` | `600` мс |
| `PLACEHOLDER_STRINGS` | `Set(['Новый заголовок', 'Новый абзац'])` |
| `focusedBlockId` | ID текущего блока в фокусе |
| `pendingCaretBlockId` | Блок для фокуса после следующего рендера |
| `dragState` | `{ activeId, overId, position }` |
| `saveQueue` | Массив отложенных сохранений |
| `isEditingTitle` | Флаг редактирования заголовка |
| `_saveToast` | Элемент toast-уведомления об ошибке сохранения |
| `connectionsPanel` | Экземпляр панели связей |
| `MINI_GRAPH_VISIBILITY_KEY` | `'ovc:editor:mini_graph_hidden'` |

#### Ключевые функции

| Функция | Описание |
|---------|----------|
| `ensureNote()` | Создаёт заметку через POST если `noteState.id` пуст, устанавливает URL через `replaceState` |
| `fetchNoteDetail(noteId)` | GET `/api/notes/{noteId}` |
| `applyNote(note)` | Заполняет `noteState`, вызывает `render()`, обновляет панель связей и инспектор |
| `loadNote()` | Полная инициализация: `ensureNote` → `fetchNoteDetail` → `applyNote` → `initMiniGraph({ force: true })` |
| `render()` | Полный DOM-рендер с сохранением/восстановлением курсора, выделения, фокуса ячеек таблиц |
| `hydrateBlocks()` | Навешивает обработчики на все отрендеренные блоки |
| `hydrateTableCells(tableEl)` | Обработчики для ячеек таблицы |
| `handleTableNavigation(event, cell, tableEl, blockId)` | Tab, Arrow, Enter навигация в таблицах |
| `updateBlockFromDom(editableEl, blockId)` | Считывание DOM обратно в `noteState.blocks` |
| `extractRichTextParts(el)` | Рекурсивный обход DOM, извлечение текста с аннотациями |
| `handleInsertBlock(block)` | Вставка нового блока |
| `handleUploadedBlocks(blocks)` | Добавление блоков загруженных файлов |
| `handleBlockAction(blockId, action)` | `delete`, `move-up`, `move-down`, `insert-before`, `insert-after` |
| `scheduleSave()` | Debounced (600мс) вызов `persistNote()` |
| `persistNote()` | PATCH `/api/notes/{noteId}` с title, blocks, styleTheme, layoutHints, passport |
| `attachBlockControls(blockEl)` | Обёртка в `.note-block-shell`, drag handle, кнопки действий |
| `setupDragAndDrop(shell, blockId)` | HTML5 drag через handle |
| `createManualLink({toId, reason})` | POST `/api/commit` с addLinks |
| `addManualTags(tags)` | POST `/api/commit` с addTags |
| `removeManualTag(tag)` | POST `/api/commit` с removeTags |
| `fetchLinkableNotes()` | GET `/api/notes?limit=100` |
| `showSaveError()` | Toast-уведомление при ошибке сохранения |
| `checkTitleOverflow()` | Проверяет переполнение заголовка, показывает/скрывает кнопку "···" |

#### DOM-элементы

`note-blocks`, `note-title`, `title-toggle`, `note-share`, `nav-back`, `nav-refresh`, `note-info`, `mobile-header-actions-toggle`, `editor-header-actions`, `block-palette`, `fab-plus`, `fab-connections`, `fab-voice`, `fab-attach`, `file-input`, `drop-overlay`, `upload-progress`, `format-toolbar`, `inline-bubble`, `note-inspector`, `llm-toggle`, `connections-panel`, `connections-toggle`, `mini-graph-toggle`, `graph-sidebar`

#### API-вызовы

| Эндпоинт | Метод | Назначение |
|----------|-------|------------|
| `/api/notes` | POST | Создание заметки |
| `/api/notes/{id}` | GET | Загрузка заметки |
| `/api/notes/{id}` | PATCH | Сохранение заметки |
| `/api/notes?limit=100` | GET | Список заметок для связей |
| `/api/commit` | POST | Связи и теги |
| `/api/export/docx/{id}` | GET | Экспорт (window.open) |

---

### 5.2. notes_page.js — Страница списка заметок

**Файл:** `src/static/js/notes_page.js`

**Назначение:** Загрузка, поиск, фильтрация, создание и удаление заметок, пагинация, глубокий полнотекстовый поиск.

#### Состояние

| Переменная | Описание |
|-----------|----------|
| `limit` | `20` |
| `offset` | Текущий offset пагинации |
| `notesCache[]` | Закешированные заметки |
| `deepSearchResults` | `{ items, query, total }` или null |
| `state.loading`, `state.reachedEnd` | Флаги загрузки |

#### Обработка удаления заметок

Внутри `renderList()` создаётся callback `onNoteDeleted(noteId)`:
1. Удаляет заметку из `notesCache` через `filter`
2. Если активен глубокий поиск — удаляет из `deepSearchResults.items`
3. Вызывает `renderList()` повторно для перерисовки списка

Этот callback передаётся в `renderNoteCard(note, { onDeleted: onNoteDeleted })` при рендере каждой карточки — как в обычном списке, так и в результатах глубокого поиска.

#### DOM-элементы

`notes-list`, `notes-search`, `create-note`, `load-more`, `deep-search-toggle`, `deep-search-panel`, `deep-search-input`, `deep-search-go`, `deep-search-close`, `deep-search-status`

#### API-вызовы

| Эндпоинт | Метод | Назначение |
|----------|-------|------------|
| `/api/notes?limit=N&offset=N` | GET | Пагинированные заметки |
| `/api/notes/search/full?q=...` | GET | Глубокий поиск |
| `/api/notes` | POST | Создание заметки |

---

### 5.3. blocks_render.js — Рендеринг блоков

**Файл:** `src/static/js/blocks_render.js`

**Назначение:** Чистый рендеринг — преобразование данных блоков в DOM-элементы.

#### Экспорты

| Функция | Описание |
|---------|----------|
| `renderNote(container, note, theme)` | Очищает контейнер, рендерит все блоки, группирует медиа в `.media-grid`, применяет тему |
| `renderBlock(block)` | Диспатч к типо-специфичному рендереру |

#### Рендереры по типам блоков

| Тип | Функция | DOM-структура |
|-----|---------|--------------|
| heading | `renderHeading(data)` | `<h2>`–`<h4>` contenteditable |
| paragraph | `renderParagraph(data)` | `<p>` contenteditable с rich text parts |
| bulletList | `renderList(data, 'ul')` | `<ul>` с `<li>` |
| numberList | `renderList(data, 'ol')` | `<ol>` с `<li>` |
| quote | `renderQuote(data)` | `<figure><blockquote>` + `<figcaption>` |
| table | `renderTable(data)` | HTML table с `<td contenteditable>` или Excel-таблица |
| image | `renderImage(data)` | `<figure><img>` |
| video | `renderVideoBlock(data)` | Compact cover или inline `<video>` |
| youtube | `renderYouTubeBlock(data)` | Cover (thumbnail + badge) или iframe |
| instagram | `renderInstagramBlock(data)` | Instagram embed с SDK |
| tiktok | `renderTikTokBlock(data)` | TikTok iframe |
| code | `renderCodeBlock(data)` | `<pre><code>` с Prism.js |
| markdown | `renderMarkdownBlock(data)` | markdown-it rendered HTML |
| audio | `renderAudio(data)` | Кастомный плеер |
| doc | `renderDoc(data)` | PDF/DOCX/RTF cover + inline |
| slides | `renderSlides(data)` | PPTX shell |
| summary | `renderSummary(data)` | Дата + текст |
| todo | `renderTodo(data)` | Checklist |
| divider | `renderDivider()` | `<hr>` |

#### Константы

| Константа | Значение |
|-----------|----------|
| `THEMES` | `{ clean: 'theme-clean', brief: 'theme-brief' }` |
| `MEDIA_BLOCK_TYPES` | `Set(['tiktok', 'instagram', 'youtube', 'video'])` |
| `CODE_MAX_LINES` | `5000` |
| `CODE_PREVIEW_LINES` | `10` |
| `SAFE_DOWNLOAD_PROTOCOLS` | `Set(['http:', 'https:'])` |

---

### 5.4. audio_recorder.js — Запись аудио

**Файл:** `src/static/js/audio_recorder.js`

**Назначение:** Запись голоса. Два пути: browser MediaRecorder (web) и PCM/WAV fallback через ScriptProcessorNode (desktop/WebView).

#### Экспорты

`initAudioRecorder({ button, uploader, onReady })` → возвращает `{ stop }` или `null`

#### Поддерживаемые MIME-типы (в порядке приоритета)

1. `audio/webm;codecs=opus`
2. `audio/webm`
3. `audio/mp4;codecs=mp4a.40.2`
4. `audio/mp4`
5. `audio/x-m4a`
6. `audio/m4a`
7. `audio/ogg;codecs=opus`
8. `audio/ogg`

#### Ключевые функции

| Функция | Описание |
|---------|----------|
| `startRecording()` | getUserMedia, старт записи (PCM на десктопе, MediaRecorder на вебе) |
| `stopRecording()` | Остановка, мин. длительность 250мс |
| `finalizeRecording(blob, mimeType)` | Валидация blob (мин. 128 байт), создание File, загрузка |
| `startPcmRecorder(stream)` | AudioContext, ScriptProcessorNode (4096 buffer), запись Float32 |
| `encodeWav(samples, sampleRate)` | PCM Float32 → WAV (44-byte header + 16-bit PCM) |
| `transcribe(file)` | POST `/api/transcribe` с FormData |
| `showAudioToast(message)` | Toast-уведомление для ошибок записи |
| `setAudioError(button, message)` | Унифицированная обработка ошибок |

#### Состояние

| Переменная | Описание |
|-----------|----------|
| `state` | `'idle'|'recording'|'uploading'|'processing'|'error'` |
| `mediaRecorder`, `mediaChunks`, `activeStream` | MediaRecorder state |
| `usePcmMode`, `pcmContext`, `pcmProcessor`, `pcmChunks` | PCM state |
| `isDesktop` | `Boolean(window.__DESKTOP_MODE || window.__TAURI__)` |

---

### 5.5. audio_player.js — Проигрыватель аудио

**Файл:** `src/static/js/audio_player.js`

**Назначение:** Кастомный аудио-плеер для `.audio-block` элементов с drag-seeking, таймлайном, переключением view.

#### Экспорты

`initAudioPlayers(container, onBlockUpdate)`

#### Ключевые функции

| Функция | Описание |
|---------|----------|
| `getAudioSrc(audioEl)` | `currentSrc || dataset.srcUrl || src` |
| `setupAudioBlock(block, onBlockUpdate)` | Инициализация плеера для блока |
| `seekToPosition(clientX, element)` | Seek по клику/drag |

#### Обработчики событий (на блок)

play/pause, audioEl events (playing, pause, waiting, stalled, ended, timeupdate, loadedmetadata, error, canplay, loadstart), toggleBtn (mini/expanded), rewind/forward 10s, download, timeline click, timeline drag (mousedown/mousemove/mouseup, touch events)

---

### 5.6. mini-graph.js — Мини-граф в редакторе

**Файл:** `src/static/js/mini-graph.js`

**Назначение:** Мини force-directed D3.js граф в сайдбаре: текущая заметка + соседи на 1 hop.

#### Экспорты

`initMiniGraph(options = { force })`

#### Состояние

| Переменная | Описание |
|-----------|----------|
| `miniGraphData` | Полные данные графа |
| `miniGraphSvg` | D3 SVG selection |
| `miniGraphSimulation` | D3 force simulation |
| `currentNoteId` | Активная заметка |
| `retryCount` | Макс. `MAX_RETRIES = 5` |
| `INIT_SAFETY_MS` | `8000` — safety timeout |
| `currentSizeWeight`, `currentGroupKey` | Текущие настройки ноды |

#### API-вызовы

| Эндпоинт | Метод | Назначение |
|----------|-------|------------|
| `/api/graph` | GET | Полные данные графа |
| `/api/notes/{id}` | GET | Загрузка sizeWeight |
| `/api/notes/{id}` | PATCH | Сохранение sizeWeight |
| `/api/graph/groups/{key}` | POST | Обновление цвета группы |

---

### 5.7. graph.js — Полноэкранный граф

**Файл:** `src/static/js/graph.js`

**Назначение:** Полноэкранный граф знаний с D3 force simulation, поиском, зумом, tooltip, управлением группами.

#### Состояние (через `window.__graph`)

`nodes`, `edges`, `node` (D3), `labels`, `link`, `svg`, `zoomBehaviour`, `simulation`, `fitToView`, `clusterColors` (Map), `clusterLabels` (Map)

#### API-вызовы

| Эндпоинт | Метод | Назначение |
|----------|-------|------------|
| `/api/graph` | GET | Все ноды и рёбра |
| `/api/graph/groups` | GET | Данные групп |
| `/api/graph/groups/{key}` | POST | Обновление цвета |
| `/api/graph/groups/{key}/label` | POST | Обновление метки |

---

### 5.8. uploader.js — Загрузчик файлов

**Файл:** `src/static/js/uploader.js`

**Назначение:** Загрузка файлов через кнопку, drag-and-drop, paste. XHR для отслеживания прогресса.

#### Экспорты

`initUploader({ attachBtn, fileInput, dropOverlay, statusEl, ensureNote, onBlocksReady, getDragState })` → `{ queueFiles(files) }` или `null`

#### Константы

| Константа | Значение |
|-----------|----------|
| `CODE_FILE_EXT` | Set из 42 расширений кода (.py, .js, .ts, .tsx, .jsx, .json, .md, .html, .css, .scss, .yml, .yaml, .sh, .bash, .zsh, .sql, .c, .h, .cpp, .hpp, .java, .kt, .go, .rs, .php, .rb, .lua, .r, .tex, .toml, .ini, .cfg, .pl, .cs, .markdown, .htm) |
| `SUCCESS_HIDE_DELAY` | 3200 мс |
| `ERROR_HIDE_DELAY` | 6200 мс |

#### API-вызовы

| Эндпоинт | Метод | Назначение |
|----------|-------|------------|
| `/api/upload?noteId=X` | POST (FormData, XHR) | Загрузка файла с прогрессом |

---

### 5.9. palette.js — Палитра блоков

**Файл:** `src/static/js/palette.js`

**Назначение:** Bottom sheet для вставки блоков с визуальным выбором размера таблицы.

#### Экспорты

`initPalette({ paletteEl, triggerEl, onInsert, onAction })`

#### Типы блоков в палитре

| Тип | Данные |
|-----|--------|
| heading | `{ level, text: '' }` |
| paragraph | `{ parts: [{ text: '' }] }` |
| bulletList | `{ items: [{ text: 'Первый пункт' }] }` |
| quote | `{ text: 'Цитата', cite: '' }` |
| table | Async picker 12x12 → `{ rows: Array[][] }` |
| todo | `{ items: [{ id, text: 'Задача', done: false }] }` |
| summary | `{ dateISO, text: 'Краткая сводка' }` |
| divider | `{}` |
| image, source | Делегирует в `onAction('attach-file')` |

---

### 5.10. notes_renderer.js — Рендеринг карточек заметок

**Файл:** `src/static/js/notes_renderer.js`

#### Экспорты

`renderNoteCard(note, options = {})` → `<article>` DOM-элемент

**Параметр `options`:**
- `onDeleted(noteId)` — callback, вызывается после успешного удаления заметки. Если не передан, карточка просто удаляется из DOM через `article.remove()`.

#### Структура карточки

Карточка включает:
- **Заголовок** (`h2.note-card__title`, contenteditable) — debounced save (1000мс) через `PATCH /api/notes/{id}`, немедленное сохранение при blur, Enter → blur, Escape → откат к оригиналу
- **Превью** (`p.note-card__preview`) — первые 80 символов текстового блока или emoji для медиа-типов (🖼 Изображение, 📄 PDF, 🎵 Аудио, 🎬 Видео, ▶ YouTube, 📸 Instagram Reel, 🎵 TikTok)
- **Футер** (`div.note-card__footer`) — дата (русский относительный формат) + **кнопка удаления**
- **Кнопка удаления** (`button.note-card__delete`) — иконка «×», aria-label "Удалить заметку"

#### Удаление заметки — поток

1. Клик по кнопке «×» (с `stopPropagation` чтобы не открыть заметку)
2. Вызов `confirmDeleteNote(title)` — показывает кастомный модальный диалог подтверждения
3. При подтверждении: `fetch('/api/notes/{id}', { method: 'DELETE' })`
4. При успехе: вызов `onDeleted(noteId)` callback или `article.remove()`
5. При ошибке: `window.alert('Не удалось удалить заметку. Попробуйте ещё раз.')`
6. Кнопка disabled на время запроса

#### Функция `confirmDeleteNote(title)` — Модальное подтверждение

Возвращает `Promise<boolean>`. Создаёт кастомный overlay + dialog (без `window.confirm`):

**DOM-структура:**
```
div.confirm-overlay
  └── div.confirm-dialog [role="dialog", aria-modal="true"]
      ├── h3.confirm-dialog__title — "Удалить заметку?"
      ├── p.confirm-dialog__text — "Заметка «{title}» будет удалена безвозвратно."
      └── div.confirm-dialog__actions
          ├── button.confirm-dialog__btn.confirm-dialog__btn--ghost — "Отменить"
          └── button.confirm-dialog__btn.confirm-dialog__btn--danger — "Удалить"
```

**Закрытие:** клик "Отменить" → false, клик "Удалить" → true, Escape → false, клик по overlay → false.

**Фокус:** автофокус на кнопку "Отменить" (безопасный выбор по умолчанию).

**Анимация:** overlay появляется через `opacity 0 → 1` с классом `.is-visible`.

**Очистка:** удаление `keydown` listener и overlay из DOM при закрытии.

#### Вспомогательные функции

| Функция | Описание |
|---------|----------|
| `formatDate(date)` | Русский относительный формат: "Только что", "X мин. назад", "X ч. назад", "X дн. назад", или локализованная дата |
| `getPreviewText(note)` | Извлечение превью: текстовый контент (80 символов) или emoji по типу блока |

#### API-вызовы

| Эндпоинт | Метод | Назначение |
|----------|-------|------------|
| `/api/notes/{id}` | PATCH | Обновление заголовка |
| `/api/notes/{id}` | DELETE | Удаление заметки |

#### Обработчики событий (на карточку)

- `article.click` — навигация на `/notes/{id}` (кроме клика на title или кнопку)
- `title.click` — `stopPropagation`
- `title.input` — debounced (1000мс) сохранение заголовка
- `title.blur` — немедленное сохранение
- `title.keydown` — Enter → blur, Escape → откат
- `deleteBtn.click` — подтверждение + удаление заметки

---

### 5.11. toolbar.js — Панель форматирования

**Файл:** `src/static/js/toolbar.js`

#### Экспорты

| Функция | Описание |
|---------|----------|
| `initToolbar(toolbarEl, rootEl)` | Настройка тулбара |
| `applyCommand(action)` | Применение `document.execCommand` |
| `clearSelectionSnapshot()` | Очистка сохранённого range |
| `rememberSelection()` | Захват текущего выделения |

#### Команды

| Кнопка | execCommand |
|--------|------------|
| bold | `'bold'` |
| italic | `'italic'` |
| link | `'createLink'` (prompt для URL) |
| list | `'insertUnorderedList'` |
| quote | `'formatBlock'` → `'blockquote'` |
| align | `'justifyFull'` |

---

### 5.12. inline_bubble.js — Inline-пузырёк форматирования

**Файл:** `src/static/js/inline_bubble.js`

**Экспорты:** `initInlineBubble(bubbleEl, canvas)`

Плавающий пузырёк, показывается при выделении текста в canvas. Позиционируется через `getBoundingClientRect()` с учётом viewport. Кнопки: bold, italic, link, quote, list, heading.

---

### 5.13. smart_insert.js — Умная вставка блоков

**Файл:** `src/static/js/smart_insert.js`

**Экспорты:** `initSmartInsert(canvas, { onTransform })`

#### Паттерны автотрансформации

| Паттерн | Результат |
|---------|----------|
| `- ` в начале | → `bulletList` |
| `сводка:` в начале | → `summary` с текущей датой |
| Instagram Reel URL | → `instagram` блок |
| TikTok URL | → `tiktok` блок (короткие URL через API) |
| YouTube URL | → через `/api/resolve/youtube` |

---

### 5.14. inspector.js — Инспектор заметки

**Файл:** `src/static/js/inspector.js`

**Экспорты:** `initInspector(panelEl, options)` → `{ update(note), onOpen(note) }`

Секции: теги (добавление/удаление, саджесты из GET `/api/tags`), связи (список + форма добавления), свойства (passport), слайдер веса ноды (sizeWeight).

---

### 5.15. connections_panel.js — Панель связей

**Файл:** `src/static/js/connections_panel.js`

**Экспорты:** `initConnectionsPanel({ rootEl, toggleBtn, getNoteId, onOpenNote, fetchOptions, addLink })` → `{ update(noteState) }`

Показывает входящие/исходящие связи, форму добавления новой связи.

---

### 5.16. word_viewer.js — Просмотр DOCX/RTF

**Файл:** `src/static/js/word_viewer.js`

**Экспорты:** `initWordViewers(container, onBlockUpdate)`

Загружает HTML через `GET /files/{fileId}/doc.html`, санитизирует через DOMPurify, кеширует в `wordContentCache` (Map).

---

### 5.17. pdf_viewer.js — Просмотр PDF

**Файл:** `src/static/js/pdf_viewer.js`

**Экспорты:** `initPdfViewers(container, onBlockUpdate)`

Lazy-загрузка страниц через IntersectionObserver, зум (MIN_ZOOM=1, MAX_ZOOM=4, ZOOM_STEP=1), навигация по страницам, кеширование состояния изображений.

API: `GET /files/{fileId}/page/{pageNum}?scale={zoom}`

---

### 5.18. slides_viewer.js — Просмотр презентаций

**Файл:** `src/static/js/slides_viewer.js`

**Экспорты:** `initSlidesViewers(container, onBlockUpdate)`

Одиночный слайд или сетка всех слайдов с lazy-загрузкой.

---

### 5.19. table_viewer.js — Просмотр таблиц Excel/CSV

**Файл:** `src/static/js/table_viewer.js`

**Экспорты:** `initTableViewers(container, onBlockUpdate)`

Навигация по листам, windowed data loading (`WINDOW_LIMIT = 500`), CSV-скачивание.

---

### 5.20. markdown_viewer.js — Просмотр Markdown

**Файл:** `src/static/js/markdown_viewer.js`

**Экспорты:** `initMarkdownViewers(container)`

markdown-it + плагины (task-lists, sub, sup, footnote), DOMPurify, Prism.js.

---

### 5.21. auth.js — Слой аутентификации

**Файл:** `src/static/js/auth.js`

**Назначение:** Обёртка `window.fetch` для инъекции Bearer token и CSRF header. Обработка 401 → refresh → retry.

#### Глобальные экспорты

| Функция | Описание |
|---------|----------|
| `window.refreshAccessToken` | Обновление access token |
| `window.ensureAccessToken` | Возвращает валидный access token |

#### Логика fetch-обёртки

1. Определяет same-origin запрос
2. Классифицирует путь: `isApi` (/api, /auth, /users, /files), `isRefresh`, `isAuthBootstrap`
3. Для API (не bootstrap): `ensureAccessToken()`, установка `Authorization: Bearer`
4. Для не-GET/HEAD/OPTIONS: добавление `X-CSRF-Token`
5. При 401 (не refresh, не retry): обновление токена + повторный запрос
6. При постоянном 401 для API: редирект на `/login`

---

### 5.22. supabase_auth.js — Интеграция Supabase

**Файл:** `src/static/js/supabase_auth.js`

**Глобальные экспорты:** `window.supabaseAuth = { init, signUp, signIn, signOut, getAccessToken, refreshSession }`

Мост Supabase → backend через `POST /auth/supabase/session`.

---

### 5.23. data_adapter.js — Десктопный адаптер синхронизации

**Файл:** `src/static/js/data_adapter.js`

**Глобальные экспорты:** `window.__OVC_DESKTOP_ADAPTER = { enabled, syncNow, getSyncStatus, refreshSyncIndicator }`, `window.__DESKTOP_MODE`

Определяет connectivity, поллит sync status, триггерит sync.

---

### 5.24. app_bootstrap.js — Инициализация глобальных переменных

**Файл:** `src/static/js/app_bootstrap.js`

Читает `data-*` атрибуты из `<body>` и устанавливает: `window.__AUTH_MODE`, `window.__DESKTOP_MODE`, `window.__SUPABASE_URL`, `window.__SUPABASE_ANON_KEY`

---

### 5.25. theme.js — Переключение тем

**Файл:** `src/static/js/theme.js`

Темы: `default`, `dark`, `milk`, `light`. Хранение в `localStorage['ovc-theme']`. Dispatch `theme-change` custom event.

---

### 5.26. utils.js — Утилиты

**Файл:** `src/static/js/utils.js`

**Экспорты:** `uuid()` — `crypto.randomUUID()` с time+random fallback.

---

### 5.27. hints.js — Подсказки

**Файл:** `src/static/js/hints.js`

**Экспорты:** `initHints(bannerEl, textEl, dismissBtn)` → `{ push(message) }`

Макс. 3 показа, трекинг в `localStorage['ovc-hints-shown']`.

---

### 5.28. password_toggle.js — Переключение видимости пароля

**Файл:** `src/static/js/password_toggle.js`

Переключает `input.type` между `password`/`text` по клику на `[data-password-toggle]`.

---

### 5.29. Страницы аутентификации

**auth_login_page.js** — Форма логина. Поддержка local, supabase, both. DOM: `#login-form`, `#login-error`. API: `POST /auth/login`.

**auth_register_page.js** — Форма регистрации. DOM: `#register-form`, `#register-error`, `#register-success`, `#registered-email`. API: `POST /auth/register`.

**auth_change_password_page.js** — Форма смены пароля. DOM: `#change-password-form`, `#change-password-error`. API: `POST /auth/change-password`.

---

## 6. HTML-шаблоны

---

### 6.1. base.html — Базовый шаблон

**Файл:** `src/templates/base.html`

Jinja2 базовый layout. Русский locale (`lang="ru"`).

**Head:** charset, viewport, title (block), CSS (styles.css, prism-tomorrow.css, prism-ovc.css)

**Body атрибуты:** `class="theme-clean"`, `data-theme`, `data-auth-mode`, `data-desktop-mode`, `data-supabase-url`, `data-supabase-anon-key`

**Header:** `.app-shell__topbar` — бренд "OVC Human Notes", навигация: База (/notes), Редактор (/notes/), Граф (/graph), условные ссылки (user/login/register/logout/password)

**Main:** `<main id="app-root" class="app-shell__body">` → content block

**Footer:** `.app-shell__footer` — "Offline · Готово к своей модели" + `#sync-status-indicator`

**Scripts (deferred):** prism.js, markdown-it.min.js + плагины, dompurify.min.js, app_bootstrap.js, data_adapter.js, (условно) supabase.js + supabase_auth.js, auth.js, theme.js, extra_scripts block

---

### 6.2. editor.html — Страница редактора

**Файл:** `src/templates/editor.html`

Двухколоночный layout: editor + graph sidebar.

Секции:
- `.editor-layout` → `.editor[data-note-id]`
- Header: back, refresh, title (contenteditable), title-toggle, mobile actions toggle, header actions (connections, info, theme, share)
- Toolbar: Bold, Italic, Link, List, Quote, Align
- Connections panel
- Canvas → `#note-blocks`
- Floating actions: +, connections, voice, attach
- Hidden file input
- Upload progress
- Drop overlay
- Block palette (bottom sheet)
- Note inspector (side panel)
- Inline bubble
- Mini-graph toggle (floating)
- Graph sidebar

Scripts: d3.v7.min.js, editor.js (module), mini-graph.js (module)

---

### 6.3. notes.html — Список заметок

**Файл:** `src/templates/notes.html`

- Header: "Мои заметки", search input, deep-search-toggle, theme switcher, create button
- Deep search panel (hidden): input, find button, close button, status
- Notes list
- Footer: load more

Script: notes_page.js (module)

---

### 6.4. graph.html — Страница графа

**Файл:** `src/templates/graph.html`

- Header: "Граф заметок", search, theme, reset, labels toggle
- Graph shell: canvas, SVG, tooltip
- Groups panel: legend, groups list

Scripts: d3.v7.min.js, graph.js

---

### 6.5. Шаблоны аутентификации

**login.html** — Форма логина (identifier + password), password toggle, ссылка на register. Условные сообщения для ?registered, ?verified, ?verify=expired|invalid.

**register.html** — Форма регистрации (email + password), policy hint, success panel с email. Ссылка на login.

**change-password.html** — Форма смены пароля (old + new), policy hint. Ссылка на главную.

---

### 6.6. welcome.html — Приветственная страница

Бренд "OVCnotes" + слоган. Две карточки: вход и регистрация.

---

## 7. CSS — Стили

**Файл:** `src/static/css/styles.css` (~4600 строк)

### Основные секции

1. **Design Tokens (`:root`):**
   - Цвета: `--bg`, `--surface`, `--card`, `--text`, `--muted`, `--accent`, `--danger`
   - Бордеры: `--border-1/2/3`
   - Тени: `--elev-1/2/3`
   - Neon-эффекты: `--neon-bg`, `--neon-glow`
   - Радиусы: `--radius-s/m/l`
   - Шрифт: Inter, SF Pro Display

2. **4 темы:** `default`/`brief`/`clean` (фиолетовый neon dark), `dark` (нейтральный серый), `milk` (тёплый кремовый), `light` (чистый белый)

3. **App Shell:** `.app-shell__topbar`, `__nav`, `__body`, `__footer`, `__brand`

4. **Кнопки:** `.pill-button` (primary, compact, ghost, secondary), `.icon-button` (mini, ghost, info, compact)

5. **Формы:** input, select, label, `.password-field`, `.password-toggle`

6. **Auth-страницы:** `.auth-page`, `.auth-card`, `.auth-form`, `.register-success`, `.welcome-page`

7. **Страница заметок:** `.notes-page`, `.note-card`, `.note-card__delete`, `.notes-empty`, `.deep-search-panel`

7a. **Модальное подтверждение удаления:** `.confirm-overlay` (fixed overlay с затемнением, opacity-анимация через `.is-visible`), `.confirm-dialog` (max-width 430px, border + shadow + padding, grid layout), `.confirm-dialog__title`, `.confirm-dialog__text`, `.confirm-dialog__actions` (flex, justify-content: flex-end), `.confirm-dialog__btn` (pill-shaped, border, hover transform), `.confirm-dialog__btn--danger` (красная обводка + цвет #ef4444), `.confirm-dialog__btn--ghost` (стандартный стиль без акцента)

7b. **Кнопка удаления карточки:** `.note-card__delete` (34x34px, border-radius 12px, символ «×», полупрозрачная, hover → красноватый оттенок rgba(239,68,68), disabled → opacity 0.55 + cursor wait)

8. **Editor Layout:** `.editor-layout` (flex), `.editor`, `.editor__header`, `.editor__title-wrapper`, `.editor__title`, `.editor__title-more`

9. **Toolbar & Inline Bubble:** `.toolbar`, `.toolbar__btn`, `.inline-bubble`

10. **Note Blocks:** `.note-block`, `.note-block-shell`, `.block-actions`, `.note-editable`, rich text (`.rt-bold`, `.rt-italic`, `.rt-underline`, `.rt-strike`, `.rt-code`)

11. **Media Blocks:** image, video, youtube, instagram, tiktok, `.media-grid`

12. **Code & Markdown:** `.note-block--code`, `.ovc-prism`, `.note-block--markdown`, `.ovc-md`

13. **Audio Player:** `.audio-block`, `.audio-controls`, `.audio-btn--play`, `.audio-timeline`, `.audio-progress`, `.audio-expanded`

14. **Document Viewers:** `.doc-block--pdf`, `.doc-block--word`, `.pdf-pages`, `.word-inline`

15. **Slides Viewer:** `.slides-block`, `.slides-cover`, `.slides-inline`

16. **Table Viewer:** `.table-block`, `.table-block--excel`, `.data-grid`

17. **Floating Actions:** `.floating-actions`, `.fab`, `.fab--primary`, `.fab--recording`

18. **Upload Progress:** `.upload-progress`, `__item`, `__bar`, `__fill`

19. **Drop Overlay:** `.drop-overlay`, `.is-visible`

20. **Block Palette:** `.bottom-sheet`, `.block-palette`

21. **Inspector:** `.note-inspector`, `.chip-list`, `.chip`, `.inspector-link-form`

22. **Connections Panel:** `.connections-panel`, `.connections-panel--open`, `.conn-group`, `.conn-item`, `.conn-add`

23. **Graph Page:** `.graph-page`, `.graph-canvas`, `.graph-tooltip`, `.graph-legend`, `.graph-groups-panel`

24. **Mini-Graph Sidebar:** `.graph-sidebar`, `.mini-graph-svg`, `.mini-graph-toggle-floating`

25. **Mobile Responsive (max-width: 899px):** Стек layout, скрытие graph sidebar, full-width блоки

26. **Утилиты:** `.hidden`, `.muted`, `.spacer`, `.sr-only`, `.text-center`, `.danger`

---

## 8. Десктопное приложение (Tauri)

---

### 8.1. main.rs — Rust точка входа

**Файл:** `desktop/src-tauri/src/main.rs`

**Назначение:** Запуск локального Python FastAPI бэкенда и создание WebView-окна.

#### Структуры

```rust
struct BackendState {
    child: Mutex<Option<Child>>
}
```

#### Функции

| Функция | Описание |
|---------|----------|
| `find_project_root()` | Поиск корня OVC по наличию `src/` и `scripts/` |
| `ensure_dir(path)` | Создание директории если отсутствует |
| `wait_for_port(host, port, timeout)` | Поллинг TCP порта (таймаут 25с) |
| `pick_env(name)` | Чтение переменной окружения |
| `resolve_database_url(project_root, app_data_dir)` | Приоритет: `OVC_DESKTOP_DATABASE_URL` → `DATABASE_URL` → `sqlite:///./src/ovc.db` |
| `spawn_local_backend(app_data_dir)` | Запуск `python3 -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 18741` |
| `main()` | Tauri setup: spawn backend → wait for port → create window 1440x920 (min 1100x700). On exit: kill child |

#### Env-переменные (устанавливаемые)

| Переменная | Значение |
|-----------|----------|
| `PYTHONPATH` | `src` |
| `DATABASE_URL` | resolved |
| `DESKTOP_MODE` | `1` |

#### Env-переменные (читаемые)

| Переменная | Описание |
|-----------|----------|
| `OVC_DESKTOP_BASE_URL` | Override внешнего URL |
| `OVC_DESKTOP_DATABASE_URL` | Явный путь к БД |
| `DATABASE_URL` | Стандартный URL БД |

---

### 8.2. tauri.conf.json — Конфигурация Tauri

**Файл:** `desktop/src-tauri/tauri.conf.json`

- **Package:** productName "OVC Desktop", version "0.1.0"
- **Build:** devPath "http://127.0.0.1:18741", distDir "../web"
- **Window:** title "OVC", 1440x920, resizable
- **Bundle:** active false, targets ["dmg"], identifier "com.ovc.desktop"

#### Allowlist (разрешения)

| Категория | Значение |
|-----------|----------|
| `all` | false |
| `shell.all` | false |
| `shell.open` | true |
| `window.all` | true |
| `path.all` | true |
| `dialog.all` | true |

#### CSP

```
default-src 'self';
base-uri 'self';
form-action 'self';
script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://www.instagram.com;
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
font-src 'self' data:;
media-src 'self' data: blob: http://127.0.0.1:18741 http://127.0.0.1:8000 https:;
connect-src 'self' http://127.0.0.1:18741 http://127.0.0.1:8000 https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cemlfmnjpydwgwcedlzy.supabase.co https://YOUR_REMOTE_DOMAIN;
frame-src 'self' https://www.instagram.com https://www.tiktok.com;
object-src 'none';
frame-ancestors 'none'
```

---

### 8.3. Cargo.toml — Зависимости Rust

**Файл:** `desktop/src-tauri/Cargo.toml`

| Зависимость | Версия | Назначение |
|-------------|--------|------------|
| `anyhow` | 1.0 | Обработка ошибок |
| `serde` | 1.0 + derive | Сериализация |
| `serde_json` | 1.0 | JSON |
| `tauri` | 1.6 (features: window-all, shell-open, path-all, dialog-all) | Tauri framework |
| `ureq` | 2.10 | HTTP клиент |
| `url` | 2.5 | Парсинг URL |
| `tauri-build` | 1.5 (build) | Сборка Tauri |

---

### 8.4. Info.plist — Разрешения macOS

**Файл:** `desktop/src-tauri/Info.plist`

```xml
<key>NSMicrophoneUsageDescription</key>
<string>OVC использует микрофон для записи голосовых заметок.</string>
```

---

### 8.5. build.rs — Скрипт сборки

**Файл:** `desktop/src-tauri/build.rs`

```rust
fn main() { tauri_build::build() }
```

---

## 9. Скрипты и утилиты

### start_server.sh

**Файл:** `scripts/start_server.sh`

1. Создаёт `.venv` если отсутствует
2. Активирует виртуальное окружение
3. Устанавливает зависимости из `src/requirements.txt`
4. Запускает миграции: `PYTHONPATH=src python -m app.db.migrate`
5. Запускает сервер: `uvicorn app.main:app --app-dir src --reload --host 127.0.0.1 --port 8000`

### migrate_desktop_to_shared.py

**Файл:** `scripts/migrate_desktop_to_shared.py`

**Назначение:** Миграция данных из старой десктопной SQLite БД в общую БД.

Обрабатывает: merge пользователей по email/username/ID, миграцию notes, note_chunks, files, note_links, note_tags. Создаёт бэкап.

**Ключевые функции:** `_normalize()`, `_table_columns()`, `_row_to_dict()`, `_insert_row()`, `_ensure_unique_username()`, `migrate(source_db, target_db, backup=True)`, `main()`

### package.json

```json
{
  "name": "ovc-desktop-tools",
  "private": true,
  "scripts": {
    "desktop:dev": "cargo run --manifest-path desktop/src-tauri/Cargo.toml",
    "desktop:build": "cargo build --release --manifest-path desktop/src-tauri/Cargo.toml"
  }
}
```

---

## 10. Переменные окружения — Полный список

| Переменная | Default | Описание |
|-----------|---------|----------|
| `DATABASE_URL` | `sqlite:///./src/ovc.db` | URL базы данных |
| `SIMPLE_DB_URL` | `sqlite:///./src/ovc.db` | Альтернативный URL БД |
| `SECRET_KEY` | `CHANGE_ME...` | Ключ подписи JWT (≥32 символа) |
| `ACCESS_TOKEN_EXPIRES_MIN` | `15` | TTL access token (минуты) |
| `REFRESH_TOKEN_EXPIRES_DAYS` | `30` | TTL refresh token (дни) |
| `COOKIE_DOMAIN` | (пусто) | Домен cookies |
| `COOKIE_SECURE` | `false` | HTTPS-only cookies |
| `COOKIE_SAMESITE` | `lax` | SameSite политика |
| `PUBLIC_BASE_URL` | (пусто) | Публичный URL |
| `CORS_ORIGINS` | (пусто) | Дополнительные allowed origins (CSV) |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Окно rate limit |
| `RATE_LIMIT_MAX` | `60` | Макс. запросов |
| `RATE_LIMIT_LOGIN_PER_MIN` | `10` | Лимит логинов |
| `RATE_LIMIT_REGISTER_PER_MIN` | `10` | Лимит регистраций |
| `PASSWORD_MIN_LENGTH` | `8` | Мин. длина пароля |
| `PASSWORD_MIN_CHARACTER_CLASSES` | `3` | Мин. классов символов |
| `PASSWORD_REQUIRE_UPPER` | `false` | Требовать заглавные |
| `PASSWORD_REQUIRE_LOWER` | `false` | Требовать строчные |
| `PASSWORD_REQUIRE_DIGIT` | `false` | Требовать цифры |
| `PASSWORD_REQUIRE_SYMBOL` | `false` | Требовать спецсимволы |
| `EMAIL_FROM` | `no-reply@ovc.local` | Email отправитель |
| `EMAIL_BACKEND` | `mock` | Email бэкенд |
| `AUTH_MODE` | `local` | Режим аутентификации |
| `DESKTOP_MODE` | `false` | Десктоп-режим |
| `ALLOW_DESKTOP_DEV_FALLBACK` | `false` | Dev-user без auth |
| `SUPABASE_URL` | (пусто) | URL Supabase |
| `SUPABASE_ANON_KEY` | (пусто) | Supabase anon key |
| `SUPABASE_ISSUER` | (auto) | JWT issuer Supabase |
| `SUPABASE_JWKS_URL` | (auto) | JWKS URL Supabase |
| `SUPABASE_JWT_AUD` | `authenticated` | JWT audience |
| `SYNC_MODE` | `auto` | Режим синхронизации |
| `SYNC_ENABLED` | `false` | Включить sync |
| `SYNC_REMOTE_BASE_URL` | (пусто) | Remote URL |
| `SYNC_BEARER_TOKEN` | (пусто) | Токен sync |
| `SYNC_POLL_SECONDS` | `15` | Интервал поллинга |
| `SYNC_OUTBOX_MAX` | `10000` | Макс. outbox |
| `SYNC_BATCH_SIZE` | `100` | Размер батча |
| `SYNC_REQUEST_TIMEOUT_SECONDS` | `12` | Таймаут запроса |
| `SYNC_PULL_ENABLED` | `true` | Разрешить pull |
| `APP_ENV` | `development` | Окружение |
| `RUNTIME_STATUS_ENABLED` | `true` | Эндпоинт статуса |
| `CSP_REPORT_ONLY` | `false` | CSP report-only |
| `CSP_SCRIPT_SRC_EXTRA` | (пусто) | Доп. script CSP |
| `CSP_STYLE_SRC_EXTRA` | (пусто) | Доп. style CSP |
| `CSP_CONNECT_SRC_EXTRA` | (пусто) | Доп. connect CSP |
| `CSP_IMG_SRC_EXTRA` | (пусто) | Доп. img CSP |
| `CSP_FRAME_SRC_EXTRA` | (пусто) | Доп. frame CSP |
| `OVC_UPLOAD_ROOT` | (пусто) | Кастомная директория загрузок |
| `OVC_DESKTOP_BASE_URL` | (пусто) | Override URL десктопа |
| `OVC_DESKTOP_DATABASE_URL` | (пусто) | Override БД десктопа |
| `OVC_DESKTOP_USE_SHARED_DB` | (пусто) | Флаг общей БД |
| `VECTOR_DIM` | `384` | Размерность эмбеддингов |
| `OFFLINE_MODE` | `true` | Offline-first режим |

---

## 11. Зависимости Python

**Файл:** `src/requirements.txt`

| Пакет | Версия | Назначение |
|-------|--------|------------|
| fastapi | 0.121.0 | Web framework |
| uvicorn | 0.38.0 | ASGI server |
| jinja2 | 3.1.6 | Шаблоны |
| python-dotenv | 1.2.1 | .env загрузка |
| sqlalchemy | 2.0.44 | ORM |
| scikit-learn | 1.6.1 | TF-IDF |
| python-multipart | 0.0.20 | Form data parsing |
| pydantic | 2.12.3 | Валидация |
| markdown | 3.9 | Markdown processing |
| pillow | 11.3.0 | Обработка изображений |
| pypdf | 6.2.0 | PDF parsing |
| pymupdf | 1.26.5 | PDF rendering |
| mammoth | 1.11.0 | DOCX → HTML |
| striprtf | 0.0.29 | RTF → HTML |
| bleach | 6.2.0 | HTML sanitization |
| mutagen | 1.47.0 | Audio metadata |
| pandas | 2.3.3 | Excel/CSV обработка |
| openpyxl | 3.1.5 | .xlsx чтение |
| xlrd | 1.2.0 | .xls чтение |
| httpx | 0.28.1 | HTTP client (sync engine) |
| argon2-cffi | 25.1.0 | Argon2id hashing |
| python-jose | 3.5.0 | JWT |
| itsdangerous | 2.2.0 | Token signing |
| email-validator | 2.3.0 | Email валидация |
| psycopg2-binary | 2.9.11 | PostgreSQL driver |

---

## 12. Полный список API-эндпоинтов

### Страницы (GET, HTML)

| Путь | Аутентификация | Шаблон |
|------|----------------|--------|
| `/` | Опциональная | editor.html / welcome.html |
| `/notes` | Опциональная | notes.html |
| `/notes/{note_id}` | Опциональная | editor.html |
| `/graph` | Опциональная | graph.html |
| `/login` | Нет | auth/login.html |
| `/register` | Нет | auth/register.html |
| `/change-password` | Опциональная | auth/change-password.html |

### API — Заметки

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/api/tags` | Bearer | Все теги пользователя |
| GET | `/api/notes` | Bearer | Список заметок (limit, offset) |
| GET | `/api/notes/search/full` | Bearer | Глубокий поиск (q, limit) |
| GET | `/api/notes/{id}` | Bearer | Деталь заметки |
| POST | `/api/notes` | Bearer | Создание |
| PATCH | `/api/notes/{id}` | Bearer | Обновление |
| DELETE | `/api/notes/{id}` | Bearer | Удаление |

### API — Аутентификация

| Метод | Путь | Auth | Rate | CSRF |
|-------|------|------|------|------|
| POST | `/auth/register` | Нет | Да | Нет |
| POST | `/auth/login` | Нет | Да | Нет |
| POST | `/auth/refresh` | Refresh cookie | Нет | Да |
| POST | `/auth/logout` | Refresh cookie | Нет | Да |
| GET | `/auth/verify` | Нет | Нет | Нет |
| POST | `/auth/resend-verification` | Нет | Да | Нет |
| POST | `/auth/supabase/session` | Supabase | Нет | Нет |
| GET | `/auth/username-available` | Нет | Нет | Нет |
| POST | `/auth/change-password` | Bearer | Нет | Да |

### API — Пользователи

| Метод | Путь | Auth |
|-------|------|------|
| GET | `/api/users/me` | Bearer |
| PATCH | `/api/users/me` | Bearer |

### API — Файлы (загрузка)

| Метод | Путь | Auth |
|-------|------|------|
| POST | `/api/upload` | Bearer |
| POST | `/api/upload/audio` | Bearer |
| POST | `/api/transcribe` | Bearer |

### API — Файлы (раздача)

| Метод | Путь | Auth |
|-------|------|------|
| GET | `/files/{id}/original` | Bearer/Refresh |
| GET | `/files/{id}/preview` | Bearer/Refresh |
| GET | `/files/{id}/doc.html` | Bearer/Refresh |
| GET | `/files/{id}/slides.json` | Bearer/Refresh |
| GET | `/files/{id}/slide/{idx}` | Bearer/Refresh |
| GET | `/files/{id}/video/source` | Bearer/Refresh |
| GET | `/files/{id}/video/poster.webp` | Bearer/Refresh |
| GET | `/files/{id}/code/meta` | Bearer/Refresh |
| GET | `/files/{id}/code/preview` | Bearer/Refresh |
| GET | `/files/{id}/code/raw` | Bearer/Refresh |
| GET | `/files/{id}/md/preview` | Bearer/Refresh |
| GET | `/files/{id}/md/raw` | Bearer/Refresh |
| GET | `/files/{id}/excel/summary.json` | Bearer/Refresh |
| GET | `/files/{id}/excel/sheet/{name}.json` | Bearer/Refresh |
| GET | `/files/{id}/excel/sheet/{name}.csv` | Bearer/Refresh |
| GET | `/files/{id}/excel/charts.json` | Bearer/Refresh |
| GET | `/files/{id}/excel/charts/sheets.json` | Bearer/Refresh |
| GET | `/files/{id}/excel/charts-anchors.json` | Bearer/Refresh |
| POST | `/files/{id}/excel/charts/pages` | Bearer |
| GET | `/files/{id}/excel/chart/{idx}` | Bearer/Refresh |
| GET | `/files/{id}/waveform` | Bearer/Refresh |
| GET | `/files/{id}/stream` | Bearer/Refresh |
| GET | `/files/{id}/page/{num}` | Bearer/Refresh |

### API — Граф

| Метод | Путь | Auth |
|-------|------|------|
| GET | `/api/graph` | Bearer |
| GET | `/api/graph/groups` | Bearer |
| POST | `/api/graph/groups/{key}` | Bearer |
| POST | `/api/graph/groups/{key}/label` | Bearer |

### API — Прочее

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/commit` | Bearer | Пакетные действия |
| POST | `/api/chat` | Bearer | Чат с агентом |
| GET | `/api/export/docx/{id}` | Bearer | Экспорт (заглушка) |
| POST | `/api/resolve/youtube` | Bearer | Резолв YouTube |
| POST | `/api/resolve/tiktok` | Bearer | Резолв TikTok |
| GET | `/api/sync/status` | Bearer | Статус синхронизации |
| POST | `/api/sync/trigger` | Bearer | Триггер синхронизации |
| GET | `/healthz` | Нет | Health check |
| GET | `/api/runtime/status` | Нет | Диагностика (если включена) |

---

## 13. Схема базы данных

```
┌─────────────────────┐
│       users          │
│─────────────────────│
│ id (PK)             │
│ username (unique)    │
│ email (unique)       │
│ password_hash        │
│ supabase_id (unique) │
│ display_name         │
│ avatar_url           │
│ failed_login_count   │
│ locked_until         │
│ created_at           │
│ updated_at           │
│ is_active            │
│ role                 │
└──────────┬──────────┘
           │
    ┌──────┼──────────┬────────────┬────────────┐
    │      │          │            │            │
    ▼      ▼          ▼            ▼            ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
│ notes  │ │ files  │ │ refresh  │ │ audit    │ │ sync_outbox  │
│        │ │        │ │ _tokens  │ │ _logs    │ │              │
└───┬────┘ └────────┘ └──────────┘ └──────────┘ └──────────────┘
    │
    ├─── note_chunks
    ├─── note_links (from_id, to_id → notes)
    ├─── note_tags
    ├─── note_sources ──→ sources
    ├─── files (note_id)
    ├─── sync_note_map
    └─── sync_conflicts

Другие таблицы:
    messages, action_log, group_preferences
```

---

## 14. Потоки данных

### 14.1. Создание заметки

```
Пользователь нажимает "+" (editor.js)
  → ensureNote()
    → POST /api/notes (notes.py)
      → _reindex_note() → tfidf_index.upsert()
      → enqueue_sync_operation(OP_CREATE_NOTE)
      → audit.log_event(NOTE_CREATE)
    → history.replaceState()
  → render()
  → initMiniGraph({ force: true })
```

### 14.2. Сохранение заметки

```
Пользователь редактирует блок (input event)
  → updateBlockFromDom() → noteState.blocks обновлён
  → scheduleSave() (debounce 600ms)
    → persistNote()
      → PATCH /api/notes/{id} (notes.py)
        → _load_blocks() (валидация)
        → _reindex_note() → tfidf_index.upsert()
        → enqueue_sync_operation(OP_UPDATE_NOTE)
        → audit.log_event(NOTE_UPDATE)
      ← 200 OK
    (при ошибке) → showSaveError() (toast)
```

### 14.3. Загрузка файла

```
Пользователь перетаскивает файл (uploader.js)
  → ensureNote()
  → XHR POST /api/upload (upload.py)
    → file_service.save_upload() (services/files.py)
      → _classify_file()
      → Сохранение оригинала
      → Генерация превью/метаданных
      → Создание FileAsset в БД
      → _build_block() → JSON блок
    → enqueue_sync_operation(OP_UPLOAD_FILE)
    → audit.log_event(FILE_UPLOAD)
  ← 200 {blocks, files}
  → handleUploadedBlocks(blocks) → render()
```

### 14.4. Глубокий поиск

```
Пользователь вводит запрос в deep-search-input (notes_page.js)
  → performDeepSearch()
    → GET /api/notes/search/full?q=... (notes.py)
      → tfidf_index.search(query) → TF-IDF результаты
      → SQL LIKE по title → заголовки
      → SQL LIKE по FileAsset.filename → файлы
      → Дедупликация + сортировка по релевантности
    ← { items, total, query }
  → deepSearchResults = результат
  → renderList() (показ с бейджем)
```

### 14.5. Удаление заметки

```
Пользователь нажимает «×» на карточке заметки (notes_renderer.js)
  → e.stopPropagation() (чтобы не открыть заметку)
  → confirmDeleteNote(title)
    → Создание overlay + dialog в DOM
    → Ожидание Promise: "Удалить" → true, "Отменить"/Escape/overlay click → false
  → Если confirmed:
    → deleteBtn.disabled = true
    → DELETE /api/notes/{id} (notes.py)
      → _ensure_note_owner() — проверка владельца
      → enqueue_sync_operation(OP_DELETE_NOTE, {localNoteId})
      → audit.log_event(NOTE_DELETE)
      → session.delete(note) — SQLAlchemy каскадное удаление
        → Удаление note_chunks, note_tags, note_links, note_sources (CASCADE)
        → files.note_id → SET NULL (файлы остаются, но не привязаны)
      → index.remove(note_id) — удаление из TF-IDF индекса
    ← {"status": "ok"}
    → onNoteDeleted(noteId) (notes_page.js)
      → notesCache = notesCache.filter(...)
      → deepSearchResults.items = deepSearchResults.items.filter(...) (если активен)
      → renderList() — перерисовка списка
  → При ошибке: window.alert('Не удалось удалить заметку.')
  → deleteBtn.disabled = false

Синхронизация удаления (если remote-sync):
  → Background worker → _push_outbox()
    → _flush_delete_note(payload)
      → client.delete(f"/api/notes/{remote_id}")
      → 200 или 404 → success
```

### 14.6. Синхронизация (remote-sync)

```
Background worker (sync_engine.py)
  → trigger_sync_now(access_token, user_id)
    
    PUSH:
    → _push_outbox(session, client, user_id)
      → Для каждого pending SyncOutbox:
        → _flush_operation() → HTTP к remote серверу
        → При успехе: status = done
        → При ошибке: tries++, status = failed

    PULL:
    → _pull_remote_changes(session, client, user_id)
      → GET /api/notes?limit=100 от remote
      → Для каждой remote заметки:
        → Если нет local → создать
        → Если local.updated_at < remote → обновить
        → Если local pending + remote newer → conflict copy
```

---

*Конец документации*
