# Repo Map

```
simple_app/
├── app/
│   ├── api/          # notes/chat/commit/export
│   ├── agent/        # blocks_schema + DraftAction + orchestrator
│   ├── db/           # модели, миграция, сессия
│   ├── providers/    # LLM-провайдер, структуризатор (stub)
│   ├── rag/          # TF-IDF индекс
│   └── main.py       # FastAPI приложение
├── static/
│   ├── css/styles.css            # темы Clean/Brief, mobile layout
│   └── js/
│       ├── blocks_render.js      # рендер JSON блоков
│       ├── editor.js             # основной контроллер редактора
│       ├── toolbar.js, inline_bubble.js, palette.js
│       ├── smart_insert.js, inspector.js, hints.js, theme.js, utils.js
│       └── notes_page.js, notes_renderer.js
├── templates/        # base.html, notes.html, editor.html
├── requirements.txt  # зависимости Python
└── run.sh            # автозапуск (venv → миграция → uvicorn)
```

Документация:

- `README.md` — обзор и запуск.
- `simple_app/README_simple.md` — детали API/блоков/экспорта.
