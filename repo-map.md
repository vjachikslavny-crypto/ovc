# Repo Map

```
simple_app/
├── app/
│   ├── api/          # notes/chat/commit/export/graph
│   ├── agent/        # blocks_schema + DraftAction + orchestrator
│   ├── db/           # модели, миграция, сессия
│   ├── providers/    # LLM-провайдер, структуризатор (stub)
│   ├── rag/          # TF-IDF индекс
│   └── main.py       # FastAPI приложение
├── static/
│   ├── css/styles.css            # темы Clean/Brief, mobile layout
│   └── js/
│       ├── blocks_render.js, editor.js
│       ├── toolbar.js, inline_bubble.js, palette.js, smart_insert.js
│       ├── inspector.js, hints.js, notes_page.js, notes_renderer.js
│       ├── theme.js, utils.js
│       └── graph.js, vendor/d3.v7.min.js
├── templates/        # base.html, notes.html, editor.html, graph.html
├── requirements.txt  # зависимости Python
└── run.sh            # автозапуск (venv → миграция → uvicorn)
```

Документация:

- `README.md` — обзор и запуск.
- `simple_app/README_simple.md` — детали API/блоков/экспорта.
