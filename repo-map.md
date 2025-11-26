# Repo Map

```
simple_app/
├── app/
│   ├── api/          # notes/chat/commit/export/graph + files/upload
│   ├── agent/        # blocks_schema + DraftAction + orchestrator
│   ├── db/           # модели, миграция, сессия
│   ├── services/     # files.py — обработка загрузок/превью
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

## Note Block Contract

Каждый блок заметки хранится в JSON-формате:

```
{ "id": "<uuid>", "type": "<kind>", "data": { ... } }
```

Поддерживаемые типы и их `data`:

| Тип | Полезная нагрузка |
| --- | --- |
| `heading` | `{ "level": 1..3, "text": "..." }` |
| `paragraph` | `{ "parts": [{ "text": "...", "annotations": { "bold": true, ... } }] }` |
| `bulletList` / `numberList` | `{ "items": [richText, ...] }` |
| `quote` | `{ "text": "...", "cite": "..." }` |
| `table` | Режим 1 (ручной): `{ "rows": [["cell", ...], ...] }`. Режим 2 (файлы): `{ "kind": "xlsx|xls|csv", "src": "/files/<id>/original", "summary": "/files/<id>/excel/summary.json", "view": "cover|inline", "activeSheet": "Лист1" }` |
| `todo` | `{ "items": [{ "id": "uuid", "text": "...", "done": false }, ...] }` |
| `summary` | `{ "dateISO": "2025-01-01", "text": "..." }` |
| `image` | `{ "src": "/files/<id>/preview.webp", "full": "/files/<id>/original", "alt": "", "w": 1600, "h": 900 }` |
| `audio` | `{ "src": "/files/<id>/audio.mp3", "duration": 123.4, "waveform": "/files/<id>/wave.json" }` |
| `video` | `{ "src": "/files/<id>/video.mp4", "poster": "/files/<id>/poster.jpg", "duration": 42.0, "w": 1280, "h": 720 }` |
| `doc` | `{ "kind": "pdf|docx|rtf|pptx|txt", "src": "/files/<id>/original", "preview": "/files/<id>/preview.webp", "meta": { "pages": 10, "slides": 10, "size": 1048576 } }` |
| `sheet` | `{ "kind": "xlsx|csv", "src": "/files/<id>/original", "sheets": ["Лист1"], "rows": 2500 }` |
| `code` | `{ "language": "python", "src": "/files/<id>/original", "lines": 1200, "sha256": "..." }` |
| `archive` | `{ "src": "/files/<id>/original", "tree": [{ "path": "src/app.py", "size": 2048 }, ...] }` |
| `link` | `{ "url": "https://...", "title": "...", "desc": "...", "image": "/files/<id>/link.jpg" }` |

Валидация схемы описана в `app/agent/blocks_schema.py`, строго типизированные модели лежат в `app/agent/block_models.py`.
