# OVC Agent Workspace

Локальный прототип рабочей среды на **Next.js 14 + Postgres (pgvector)**. Чат-агент управляет заметками, строит граф связей, выполняет RAG-поиск и показывает черновик diff-патчей перед применением.

## Возможности

- 💬 Чат `/chat` — агент формирует дружелюбный ответ и набор draft-действий (`create/update/link/add_source/add_tag`), которые можно применить кнопкой «Применить изменения».
- 🗒️ Заметки `/notes` — список заметок, семантический поиск (`/api/search`) и переходы к отдельным заметкам `/n/[id]` (markdown, источники, теги, бэклинки).
- 🕸️ Граф `/graph` — визуализация заметок и связей (wikilink + семантические).
- 🌐 Веб-источники — демо proxy `/api/web/search` и `/api/web/fetch`, агент добавляет источники к заметкам.
- ⏰ Напоминания — демо-эндпойнт `/api/reminders/seed` и кнопка на `/settings`.
- 🧠 AI-слой — заглушка эмбеддингов `server/ai/embeddings.ts`, простые правила агента `server/agent/index.ts`, векторный поиск `lib/rag.ts`.

## Стек

- Next.js 14 (App Router, TypeScript), Tailwind + shadcn-стиль, Zustand, lucide-react, d3-force.
- Postgres + pgvector, Drizzle ORM + migrations.
- `pnpm` в качестве пакетного менеджера.

## Запуск

```bash
# 1. Установите зависимости
pnpm install

# 2. Поднимите Postgres + pgvector
docker compose up -d

# 3. Примените схему
pnpm db:push

# 4. Набейте демо-данные
pnpm seed

# 5. Запустите dev-сервер
pnpm dev
```

Приложение будет доступно на `http://localhost:3000`.

## Переменные окружения

Создайте `.env`, скопировав `.env.example`:

```
DATABASE_URL=postgres://postgres:postgres@localhost:5432/agent_notes
VECTOR_DIM=384
```

## Структура

```
/app                 # App Router (страницы и API-роуты)
/components          # UI-компоненты (чат, diff, граф, таблицы)
/lib
  actions.ts         # Zod-схемы и типы DraftAction
  db.ts              # Инициализация Drizzle
  rag.ts             # Чанки, индекс, поиск и автоссылки
  schema.ts          # Drizzle-схема таблиц
/server
  /agent             # Правила агента и черновик действий
  /ai                # Заглушка эмбеддингов и cosine-similarity
/scripts/seed.ts     # Генерация демо-данных
/drizzle/migrations  # SQL-м миграции
```

## Дальнейшие шаги

- Подключить реальные эмбеддинги и LLM API вместо заглушек.
- Добавить полноценные нотификации (например, Telegram-бот).
- Расширить diff-view и историю действий.
- Улучшить UI (filtering, drag в графе, тёмная тема).

Проект готов к локальному запуску без внешних API и может служить стартовой точкой для дальнейшего развития.
