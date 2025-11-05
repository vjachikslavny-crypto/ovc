# Repo Map

```
simple_app/
├── app/
│   ├── api/          # FastAPI эндпоинты
│   ├── agent/        # DraftAction + оркестратор
│   ├── db/           # SQLAlchemy модели и миграции
│   ├── log/          # JSONL‑лог
│   ├── providers/    # моковые провайдеры LLM/embeddings
│   ├── rag/          # TF-IDF индекс и чанкирование
│   └── main.py       # точка входа приложения
├── static/           # CSS и клиентский JS (D3 граф, чат)
├── templates/        # HTML-шаблоны
├── requirements.txt  # зависимости Python
└── run.sh            # автозапуск (venv → миграция → uvicorn)
```

Дополнительно:

- `README.md` — инструкция по запуску и развитию проекта.
- `.gitignore` — игнорируемые артефакты (venv, база, логи).
