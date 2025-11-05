# OVC Simple App (Python + FastAPI)

Лёгкая офлайн-версия ассистента заметок. Работает без внешних API и готова к подключению локальных моделей.

## Стек

- FastAPI + Uvicorn
- HTML/CSS/JS (без React)
- SQLite (по умолчанию)
- TF-IDF поиск по заметкам (scikit-learn)
- Логирование датасета в JSONL

## Запуск

```bash
cd ~/OVC
python3 -m venv .venv
source .venv/bin/activate
pip install -r simple_app/requirements.txt
PYTHONPATH=simple_app python -m app.db.migrate
uvicorn app.main:app --reload --app-dir simple_app
```

> Скрипт `simple_app/run.sh` выполняет те же шаги автоматически.

> После обновления схемы рекомендуем удалить старый `simple_app/ovc.db`, чтобы пересоздать таблицы с новыми полями.

После старта откройте `http://localhost:8000`:

- `/` — чат с агентом
- `/notes` — список заметок и форма создания
- `/notes/{id}` — просмотр/редактирование (markdown, теги, связи, приоритет)
- `/graph` — визуализация графа заметок
- `/api/chat` — API для сообщений
- `/api/commit` — API для применения черновиков
- `/api/dataset/export` — выгрузка лога JSONL

## Переменные окружения

```
SIMPLE_DB_URL=sqlite:///./simple_app/ovc.db
VECTOR_DIM=384
OFFLINE_MODE=true
```

## Структура каталога `simple_app/`

- `app/main.py` — точка входа FastAPI
- `app/api/*` — REST-эндпоинты (чат, коммит, заметки)
- `app/agent/*` — генерация черновиков DraftAction
- `app/rag/*` — TF-IDF индекс и чанкинг
- `app/db/*` — SQLAlchemy модели и сессия
- `app/providers/*` — моковые LLM и embeddings
- `app/log/dataset_logger.py` — JSONL лог
- `templates/` — HTML-шаблоны
- `static/` — стили и клиентский JS

## Подготовка к локальным моделям

В `app/providers/` можно заменить заглушки на обращения к Ollama/vLLM. Аналогичные интерфейсы реализованы в TypeScript-коде (`server/providers/llm`).
