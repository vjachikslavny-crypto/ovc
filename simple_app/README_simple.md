# OVC Human Notes (FastAPI)

Простой офлайн-редактор заметок с блочной моделью данных. Интерфейс работает без Markdown, ориентирован на мобильные устройства и готов к будущей интеграции собственной GPT-модели.

## Быстрый старт

```bash
cd ~/OVC
python3 -m venv .venv
source .venv/bin/activate
pip install -r simple_app/requirements.txt
PYTHONPATH=simple_app python -m app.db.migrate
uvicorn app.main:app --reload --app-dir simple_app
```

После запуска откройте:

- `/` — визуальный редактор выбранной заметки
- `/notes` — список заметок и быстрый поиск
- `/graph` — интерактивный граф связей с управлением цветами/названиями групп
- `/api/dataset/export` — журнал взаимодействий в формате JSONL

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
- `add_link{fromId, toId, reason?, confidence?}`
- `set_style{noteId, styleTheme, layoutHints?}`

`/api/commit` применяет действия транзакцией и пересобирает локальный TF-IDF индекс.

## Интерфейс редактора

- Верхний мини-Toolbar и inline-пузырь для форматирования (`toolbar.js`, `inline_bubble.js`).
- Floating `＋` открывает палитру блоков (bottom sheet). Голос/вложения создают соответствующие блоки.
- Smart Insert (URL → источник, `- ` → список, `Сводка:` → блок сводки).
- Боковая панель «Паспорт заметки»: теги, связи, свойства и тумблер «Авто-оформление моделью (эксперимент)».
- Две темы оформления: `Clean` и `Brief` (переключаются в верхнем баре, сохраняются в `localStorage`).
- Подсказки-одноразки (макс. три показа).

## Экспорт

- Кнопка «Поделиться» вызывает печать (PDF) или проброс на `/api/export/docx/{note_id}` (пока stub, TODO: `python-docx`).

## Локальный поиск

TF-IDF индекс (`app/rag/tfidf_index.py`) обновляется при создании и изменении блоков. Индексируем только текст из заголовков, абзацев, списков, цитат, таблиц, сводок и чек-листов.

## Будущая GPT-модель

- Абстракция провайдера: `app/providers/llm_provider.py` (mock + заготовка Ollama).
- Конвертер сырья в DraftAction: `app/providers/structurizer.py` (пока возвращает пустой список).
- Оркестратор (`app/agent/orchestrator.py`) сейчас отвечает вручную, но совместим с LLM (достаточно передать провайдер и обработать предложения).

При включении автоматизации DraftAction будут применяться через `/api/commit`, сохраняя атомарность и контроль пользователя.
