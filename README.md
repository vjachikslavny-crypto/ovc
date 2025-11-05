# OVC Simple Agent

Лёгкий офлайн-ассистент заметок на **FastAPI + SQLite**. Агент умеет общаться в чате, предлагать действия над заметками, строить граф связей и хранить журнал действий — всё без внешних API и сложных зависимостей.

## Что внутри

- 💬 **Чат** `/` — агент отвечает дружелюбно и формирует draft-действия (`create_note`, `update_note`, `add_link`, `add_tag`, `add_source`).
- 🗂 **Заметки** `/notes` — список, быстрый ввод новой заметки, поиск по содержимому.
- 📄 **Редактор** `/notes/{id}` — Markdown, приоритет/важность, теги, связи, источники.
- 🕸 **Граф** `/graph` — интерактивная визуализация заметок и групп (цвет и имя можно настроить).
- 🔎 **RAG** — локальный TF‑IDF индекс, семантический поиск без внешних сервисов.
- 🗃 **Логи** — все обращения к агенту и коммиты пишутся в JSONL (`/api/dataset/export`).

## Быстрый старт

```bash
cd ~/OVC
python3 -m venv .venv
source .venv/bin/activate
pip install -r simple_app/requirements.txt
PYTHONPATH=simple_app python -m app.db.migrate   # создаём/обновляем БД
uvicorn app.main:app --app-dir simple_app --reload
```

После запуска откройте `http://localhost:8000`.  
Если схема изменилась, удалите `simple_app/ovc.db` и запустите миграцию снова.

## Переменные окружения

Файл `.env` не обязателен, но можно задать:

```
SIMPLE_DB_URL=sqlite:///./simple_app/ovc.db
VECTOR_DIM=384
OFFLINE_MODE=true
```

## Структура проекта

```
simple_app/
├── app/
│   ├── api/          # REST-эндпоинты (чат, коммит, заметки, граф, экспорт логов)
│   ├── agent/        # DraftAction, оркестратор и правила поведения
│   ├── db/           # SQLAlchemy модели, миграции, сессия
│   ├── log/          # JSONL-логгер действий агента
│   ├── providers/    # моковые LLM и embeddings, готовые к замене на реальные
│   ├── rag/          # чанкирование Markdown и TF-IDF индекс
│   └── main.py       # точка входа FastAPI
├── templates/        # HTML-шаблоны (чат, заметки, карточка, граф)
├── static/           # CSS/JS, тема и граф на D3
├── requirements.txt  # зависимости Python
└── run.sh            # скрипт автозапуска (venv + миграция + uvicorn)
```

## Работа с данными

- База по умолчанию — `simple_app/ovc.db` (SQLite).
- TF‑IDF индекс автоматически пересчитывается при создании/изменении заметок.
- Логи для обучения лежат в `simple_app/dataset.log`; выгрузка — `GET /api/dataset/export`.

## Куда развивать дальше

- Подключить локальную модель через Ollama/vLLM вместо mock-провайдера.
- Добавить мини-историю коммитов и “undo”.
- Реализовать экспорт/импорт заметок (Markdown/JSON).
- Настроить e2e‑тесты UI (Playwright/pytest + httpx).

OVC Simple Agent остаётся полностью офлайн и готов к кастомизации под вашу рабочую среду.
