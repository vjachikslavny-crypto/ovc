#!/bin/bash
# OVC: pdf - скрипт для запуска сервера

set -e

# Переходим в корневую директорию проекта
cd "$(dirname "$0")/.."

# Активируем venv
if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Устанавливаем зависимости
echo "Устанавливаю зависимости..."
pip install -r src/requirements.txt

# Запускаем миграцию
echo "Запускаю миграцию базы данных..."
PYTHONPATH=src python -m app.db.migrate

# Запускаем сервер
echo "Запускаю сервер..."
echo "Сервер будет доступен на http://127.0.0.1:8000"
uvicorn app.main:app --app-dir src --reload --host 127.0.0.1 --port 8000
