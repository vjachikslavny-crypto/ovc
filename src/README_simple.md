# OVC Human Notes (FastAPI)

Простой офлайн-редактор заметок с блочной моделью данных. Интерфейс работает без Markdown, ориентирован на мобильные устройства и готов к будущей интеграции собственной GPT-модели.

## Быстрый старт

```bash
cd ~/OVC
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
PYTHONPATH=src python -m app.db.migrate
uvicorn app.main:app --reload --app-dir src
```

После запуска откройте:

- `/` — визуальный редактор выбранной заметки
- `/notes` — список заметок и быстрый поиск
- `/graph` — интерактивный граф связей (явные связи + общие теги), управление цветами/названиями групп
- `/api/tags` — список всех уникальных тегов
- `/login` и `/register` — экраны авторизации

> Миграция удаляет прежние таблицы (используем SQLite + демо-данные).

## Модель заметок

Заметка хранится как JSON-массив блоков (`blocks_json`):

- `heading`, `paragraph`, `bulletList`, `numberList`
- `quote`, `divider`, `summary`, `todo`
- `image`, `table`, `source`

Схема описана в `app/agent/blocks_schema.py`. Рендер выполняется на фронтенде (`static/js/blocks_render.js`).

## DraftAction (будущая GPT-интеграция)

Типы действий (`app/agent/draft_types.py`):

- `insert_block{noteId, afterId, block}`
- `update_block{id, patch}`
- `move_block{id, afterId}`
- `add_tag{noteId, tag, confidence?}`
- `remove_tag{noteId, tag}`
- `add_link{fromId, toId, reason?, confidence?}`
- `set_style{noteId, styleTheme, layoutHints?}`

`/api/commit` применяет действия транзакцией и пересобирает локальный TF-IDF индекс.

## Интерфейс редактора

- Верхний мини-Toolbar и inline-пузырь для форматирования (`toolbar.js`, `inline_bubble.js`).
- Floating `＋` открывает палитру блоков (bottom sheet). Голос/вложения создают соответствующие блоки.
- Smart Insert (URL → источник, `- ` → список, `Сводка:` → блок сводки).
- Боковая панель «Паспорт заметки»: список и добавление тегов, связи, свойства и тумблер «Авто-оформление моделью (эксперимент)».
- Две темы оформления: `Clean` и `Brief` (переключаются в верхнем баре, сохраняются в `localStorage`).
- Подсказки-одноразки (макс. три показа).

## Экспорт

- Кнопка «Поделиться» вызывает печать (PDF) или проброс на `/api/export/docx/{note_id}` (пока stub, TODO: `python-docx`).

## Auth и база

Для PostgreSQL используйте `DATABASE_URL` и Alembic:

```bash
export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/ovc
PYTHONPATH=src alembic upgrade head
```

Для SQLite — прежний путь:

```bash
PYTHONPATH=src python -m app.db.migrate
```

Примечания по авторизации:
- Email подтверждение обязательно для входа.
- При `EMAIL_BACKEND=mock` ссылка подтверждения печатается в консольных логах.
- Refresh токен живёт в HttpOnly cookie, access передаётся как Bearer.

## Локальный поиск

TF-IDF индекс (`app/rag/tfidf_index.py`) обновляется при создании и изменении блоков. Индексируем только текст из заголовков, абзацев, списков, цитат, таблиц, сводок и чек-листов.

## Будущая GPT-модель

- Абстракция провайдера: `app/providers/llm_provider.py` (mock + заготовка Ollama).
- Конвертер сырья в DraftAction: `app/providers/structurizer.py` (пока возвращает пустой список).
- Оркестратор (`app/agent/orchestrator.py`) сейчас отвечает вручную, но совместим с LLM (достаточно передать провайдер и обработать предложения).

При включении автоматизации DraftAction будут применяться через `/api/commit`, сохраняя атомарность и контроль пользователя.
