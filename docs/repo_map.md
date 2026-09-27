# Repo Map

Актуальная рабочая структура:

```text
OVC/
├── README.md
├── PROJECT_DOCUMENTATION.md
├── desktop/                         # Tauri desktop wrapper (macOS)
│   └── src-tauri/
├── deploy/
│   └── cloudflare_tunnel/           # публичный запуск через Cloudflare Tunnel
├── docs/
│   ├── quick_start.md
│   ├── repo_map.md
│   ├── auth_migration.md
│   ├── design-fixes.md
│   ├── current_release_notes.md
│   └── pdf/
├── scripts/
│   ├── start_server.sh
│   └── migrate_desktop_to_shared.py
└── src/
    ├── app/
    │   ├── main.py                  # FastAPI точка входа
    │   ├── api/                     # notes/chat/commit/export/graph/sync/upload/files/auth/users
    │   ├── agent/                   # AI-оркестратор и контекст
    │   ├── core/                    # config/security/auth_provider
    │   ├── db/                      # модели, миграции, сессия
    │   ├── services/                # files, sync_engine, password_policy, audit, rate_limit
    │   └── providers/               # LLM provider
    ├── static/
    │   ├── css/styles.css
    │   └── js/                      # editor/notes/graph/auth/viewers/data_adapter и др.
    ├── templates/                   # base, welcome, notes, editor, graph, auth/*
    ├── requirements.txt
    ├── run.sh
    └── README_simple.md
```

Ключевые документы:

- `README.md` — запуск web/desktop + sync + tunnel.
- `PROJECT_DOCUMENTATION.md` — полная техническая документация.
- `docs/current_release_notes.md` — сводка последних нововведений.
- `src/README_simple.md` — практичные детали API/блоков/экспорта.

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
| `video` | `{ "src": "/files/<id>/video/source", "poster": "/files/<id>/video/poster.webp", "durationSec": 42.0, "width": 1280, "height": 720, "mime": "video/mp4", "view": "inline|cover|compact" }` |
| `youtube` | `{ "videoId": "abcdefghijk", "startSec": 47, "view": "inline|cover|compact" }` |
| `doc` | `{ "kind": "pdf|docx|rtf|pptx|txt", "src": "/files/<id>/original", "preview": "/files/<id>/preview.webp", "meta": { "pages": 10, "slides": 10, "size": 1048576 } }` |
| `sheet` | `{ "kind": "xlsx|csv", "src": "/files/<id>/original", "sheets": ["Лист1"], "rows": 2500 }` |
| `code` | `{ "src": "/files/<id>/code/raw", "previewUrl": "/files/<id>/code/preview?maxLines=300", "filename": "demo.py", "language": "python", "sizeBytes": 5120, "lineCount": 4200, "view": "inline" }` |
| `archive` | `{ "src": "/files/<id>/original", "tree": [{ "path": "src/app.py", "size": 2048 }, ...] }` |
| `link` | `{ "url": "https://...", "title": "...", "desc": "...", "image": "/files/<id>/link.jpg" }` |

Валидация схемы описана в `app/agent/blocks_schema.py`, строго типизированные модели лежат в `app/agent/block_models.py`.
