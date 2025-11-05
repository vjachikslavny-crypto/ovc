# OVC Human Notes

Лёгкий офлайн-проект на **FastAPI + SQLite** с “человечными” заметками. Вместо Markdown используется блочная модель (заголовки, абзацы, списки, цитаты, задачи, источники и т.д.), мобильный UX с плавающей кнопкой `＋`, нижним bottom-sheet и инлайн-пузырём форматирования. Всё готово для будущего подключения своей GPT-модели, но сейчас работает вручную.

## Основные возможности

- 🗂 **Список заметок** (`/notes`) — быстрый поиск, пагинация и создание заметок в один клик.
- 📝 **Редактор** (`/` или `/notes/{id}`) — блоки рендерятся из JSON, темы `Clean`/`Brief`, верхний мини-toolbar, inline bubble, smart insert (URL → источник, `- ` → список, `Сводка:` → блок сводки), голос/вложения и “паспорт заметки”.
- 🔁 **DraftAction API** (`/api/commit`) — атомарно применяет действия (`insert_block`, `update_block`, `move_block`, `add_tag`, `add_link`, `set_style`).
- 🔎 **Локальный поиск** — TF-IDF индекс по тексту блоков, обновляется при каждом изменении.
- 🗃 **Журнал** (`/api/dataset/export`) — JSONL-лог для обучения модели.
- 🤖 **LLM-интерфейсы** — `app/providers/llm_provider.py` + `structurizer.py` заготовлены под будущий Ollama/vLLM, сейчас возвращают пустой draft.

## Быстрый запуск

```bash
cd ~/OVC
python3 -m venv .venv
source .venv/bin/activate
pip install -r simple_app/requirements.txt
PYTHONPATH=simple_app python -m app.db.migrate  # ⚠️ очищает текущие таблицы
uvicorn app.main:app --app-dir simple_app --reload
```

Откройте `http://localhost:8000`. Чтобы пересобрать схему, удалите `simple_app/ovc.db` и перезапустите миграцию.

## Переменные окружения

```
SIMPLE_DB_URL=sqlite:///./simple_app/ovc.db
VECTOR_DIM=384
OFFLINE_MODE=true
```

## Структура

```
simple_app/
├── app/
│   ├── api/          # REST-эндпоинты (notes, commit, chat, export)
│   ├── agent/        # JSON-схема блоков и DraftAction
│   ├── db/           # SQLAlchemy модели и миграция
│   ├── log/          # JSONL журнал
│   ├── providers/    # LLM-заглушки и заготовка Ollama
│   ├── rag/          # TF-IDF индекс
│   └── main.py       # FastAPI приложение
├── static/           # CSS/JS (рендер блоков, тулбары, palette, hints)
├── templates/        # base.html, notes.html, editor.html
├── requirements.txt  # зависимости
└── run.sh            # venv + миграция + запуск uvicorn
```

## Экспорт

- **PDF** — кнопка “Поделиться” → `window.print()` (кастомный print-CSS).
- **DOCX** — заглушка `/api/export/docx/{note_id}` (TODO: подключить `python-docx`).

## Дальнейшие шаги

- Подключить Ollama/vLLM через `LLMProvider` и `structurizer`, формируя DraftAction автоматически.
- Реализовать историю коммитов + undo/redo.
- Добавить полноценный экспорт DOCX и импортер JSON.
- Настроить e2e-тестирование (Playwright/pytest + httpx).

Проект остаётся полностью офлайн и служит каркасом для собственной “человечной” модели заметок.
