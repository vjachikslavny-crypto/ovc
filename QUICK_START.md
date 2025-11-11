# Быстрый запуск сервера OVC

## Правильный способ запуска

**ВСЕГДА запускайте из корневой директории проекта `OVC`!**

```bash
# 1. Перейдите в корневую директорию проекта
cd ~/OVC

# 2. Активируйте виртуальное окружение (если еще не активировано)
source .venv/bin/activate

# 3. Убедитесь, что все зависимости установлены (включая pymupdf)
pip install -r simple_app/requirements.txt

# 4. Запустите миграцию базы данных
PYTHONPATH=simple_app python -m app.db.migrate

# 5. Запустите сервер
uvicorn app.main:app --app-dir simple_app --reload
```

Или используйте скрипт:
```bash
cd ~/OVC
./START_SERVER.sh
```

## Проверка установки pymupdf

После установки `pymupdf` убедитесь, что библиотека доступна:

```bash
cd ~/OVC
source .venv/bin/activate
python3 -c "import fitz; print('PyMuPDF version:', fitz.VersionBind)"
```

Если команда выдает ошибку, библиотека не установлена в правильном venv.

## Если сервер не запускается

1. **Убедитесь, что вы в корне проекта:**
   ```bash
   pwd  # Должно показать: /Users/vjachikslavny/OVC
   ```

2. **Проверьте, что venv активирован:**
   ```bash
   which python  # Должно показать путь к .venv/bin/python
   ```

3. **Убедитесь, что все зависимости установлены:**
   ```bash
   pip list | grep pymupdf
   ```

4. **Перезапустите сервер после установки библиотек**

## Решение проблем с PDF

Если PDF не рендерится:
1. Установите `pymupdf`: `pip install pymupdf`
2. Перезапустите сервер
3. Проверьте логи сервера при старте - должно быть: `PDF rendering libraries: PyMuPDF=True`

