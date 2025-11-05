# Repo Map

## Next.js Stack (original)

- `app/` — страницы и API Next.js
- `components/` — UI-компоненты (chat, graph, diff и т.д.)
- `lib/` — база данных (Drizzle), RAG, markdown утилиты
- `server/` — агент, провайдеры LLM, commitDraft, вспомогательные модули
- `types/` — общие типы для draft/agent/web
- `scripts/` — seed и служебные скрипты
- `docker-compose.yml` — Postgres + pgvector

## Simple App (Python + FastAPI)

- `simple_app/app/main.py` — точка входа FastAPI
- `simple_app/app/api/` — REST: `/api/chat`, `/api/commit`, `/api/notes`, `/api/graph`
- `simple_app/app/agent/` — DraftAction и оркестратор
- `simple_app/app/rag/` — TF-IDF индекс и чанкирование
- `simple_app/app/db/` — SQLAlchemy модели, сессия, миграция
- `simple_app/app/providers/` — моковые LLM/embeddings
- `simple_app/app/log/` — JSONL логгер
- `simple_app/templates/` — HTML-шаблоны (chat, notes, note)
- `simple_app/static/` — CSS/JS
- `simple_app/requirements.txt` — зависимости Python
- `simple_app/run.sh` — быстрый запуск (venv + uvicorn)

## Провайдеры LLM/Embeddings

- TypeScript: `server/providers/llm` (mock + ollama)
- Python: `simple_app/app/providers` (mock заглушки)

## Логи и датасет

- TypeScript: `server/agent/orchestrator.ts` — логика черновиков без внешних поисков
- Python: `simple_app/app/log/dataset_logger.py` — JSONL
- `GET /api/dataset/export` — выгрузка логов
