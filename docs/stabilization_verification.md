# Проверка стабилизации OVC — этапы 0–2

Дата: 2026-09-24. Исходное состояние: `develop`, `5250d17`.
Изменения оставлены локально, без commit/push. Рабочая SQLite и вложения не использовались
для тестовых записей. Реальные PostgreSQL/Supabase, Cloudflare и Tauri не запускались.

## 1. Результат

Добавлены проверяемое резервное копирование, единый контракт блоков editor/AI/legacy,
сохранение с локальным черновиком и подтверждением сервером, строгая изоляция владельцев
и исправления account linking, refresh, logout, lockout и cookie/CSRF.
Протокол sync не переделан: изменения в sync ограничены проверками пользовательского контекста.

## 2. Этап 0

Добавлены `scripts/backup_local_data.sh`, `scripts/verify_backup_restore.sh`,
`scripts/local_data.py`, `docs/data_backup_restore.md`, `docs/stabilization_baseline.md`.

- Исходная SQLite: `/Users/vjachikslavny/OVC/src/ovc.db`.
- Исходные вложения: `/Users/vjachikslavny/data/uploads`.
- Проверенная копия: `/Users/vjachikslavny/OVC/data/backups/20260923-190359-535280`.
- SQLite backup API, полный каталог оригиналов/производных, манифест SHA-256.
- Восстановление в отдельный временный каталог прошло: `quick_check=ok`,
  1299 файлов снимка, 214 путей из БД; счётчики совпали с оригиналом.
- Users 8, notes 130, files 118, links 16, tags 8, sync_outbox 187.
- После работы дополнительно сравнено содержимое всех 19 таблиц с recovery point:
  различий нет; новых/исчезнувших таблиц в рабочей БД нет.

Повторная проверка снимает старый VERIFIED-маркер до проверки контрольных сумм.
Пути не могут выходить из каталога снимка; симлинки отклоняются.
Секреты конфигурации не копируются, но сама БД содержит приватные пользовательские данные.

## 3. Этап 1

Общий контракт — `app.agent.block_models`; используется CRUD, AI draft и commit.
Поддерживаются AI `data.source`, legacy `doc.kind="doc"`, название видео. Неизвестные
поля отклоняются при записи вместо молчаливого удаления. Повреждённый JSON не выдаётся
как пустая заметка. Пустой словарь TF-IDF (например, только знаки пунктуации) не ломает save.

Редактор удерживает dirty до подтверждения конкретной ревизии, последовательно отправляет
PATCH, оставляет локальную копию при ошибке, показывает статус/повтор. Черновики разделены
по пользователю, заметке и вкладке. GET после тегов/связей не заменяет редактируемый текст.
AI commit согласуется с pending-правками, повтор неопределённого коммита блокируется.
Переходы и logout сначала сохраняют текст. `If-Match` отклоняет устаревший снимок кодом 409;
восстановление отдельной заметкой сохраняет обе конфликтующие версии.

## 4. Этап 2

- Центральный ownership-контракт: точное совпадение владельца; orphan не присваивается запросом.
- Изоляция note/file/export/upload/link/tag/graph/search/AI/proxy; графовые предпочтения
  вынесены в новую таблицу с пользовательским ключом. Старую таблицу не удаляли.
- Совпадение email не доказывает право на local-аккаунт: автоматическая Supabase-привязка
  отключена, конфликт возвращает 409, правильная существующая привязка сохранена.
- Refresh rotation и lockout фиксируются транзакционно; reuse отзывает refresh-сессии
  до ответа 401. Logout возвращает ответ с удалением cookies.
- Refresh хранит провайдера. Отключённые механизмы auth не обслуживают запросы.
- Cookie-запросы защищены CSRF; ошибочный Authorization не подменяется cookie-личностью.
- Публичный `AUTH_MODE=none` запрещён без явно опасного override.
- Файловый proxy не использует общий токен; sync не берёт чужие/NULL-owner операции.

Добавления схемы проверены на временных БД: `user_group_preferences` и
`refresh_tokens.auth_provider`. В рабочую БД они применятся при обычном запуске новой версии.
Repair-скрипт по умолчанию делает dry-run; запись требует точного плана и проверенной копии.
На рабочих данных ремонт не запускался.

## 5. Проверки

Команды воспроизводятся из корня OVC:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
node --test tests/note_save.test.mjs
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tests/manual_editor_smoke.py
./scripts/verify_backup_restore.sh data/backups/20260923-190359-535280
.venv/bin/python -B scripts/audit_local_data.py
git diff --check
```

Python: **94 passed** — 66 прежних тестов, 28 новых случаев. JavaScript: **7 passed**.
Browser smoke: **9 сценариев прошли**, процесс завершился с кодом 0; финальных падений нет.
`git diff --check` прошёл. Тестовый сервер остановлен после проверки.
Оставшиеся 88 Python warnings связаны с устаревшими API библиотек; они не скрыты изменениями
продуктового кода. Синтаксис проверен для 72 Python-файлов, трёх JS-модулей и трёх shell-скриптов.

Browser smoke проверяет сохранение/reload, быстрый переход, теги и связи при dirty-тексте,
загрузку вложения при dirty-тексте, ошибку PATCH/повтор, восстановление после reload,
AI draft → commit → ручное редактирование, конфликт версии/сохранение двух копий,
сохранение перед logout. Ответ LLM — тестовая SSE-фикстура; остальные API настоящие.
Тест использует временные SQLite/вложения/localhost-порт и завершает свой сервер.

## 6. Аудит данных

- Бесхозных заметок/файлов, отсутствующих привязанных заметок, файлов с чужим владельцем: **0**.
- 41 файл без note_id — самостоятельные загрузки, не автоматически мусор.
- Нарушений FK: **117**, из них sync_outbox 77, audit_logs 38, refresh_tokens 2.
- Связей между разными владельцами: **1**; запись оставлена, доступ к ней отфильтрован.
- Дубликатов Supabase ID и конфликтующих email→Supabase mappings: **0**.
- Блоки: **125** заметок валидны непосредственно, **5** нормализуются,
  неподдерживаемых заметок **0**.
- Outbox: 187 pending, из них одна запись без user_id; автоматического отправления/ремонта не было.

Команда аудита выводит идентификаторы проблемных записей для последующего контролируемого
ремонта, без содержимого заметок и токенов.

## 7. Файлы

Полный перечень файлов этого этапа приведён ниже. Пользовательский `tmp/` не относится
к изменениям задачи; `.env`, рабочая БД и реальные вложения не менялись.

Всего файлов: 45.

- [README.md](../README.md)
- [deploy/cloudflare_tunnel/start_public_server.sh](../deploy/cloudflare_tunnel/start_public_server.sh)
- [docs/auth_migration.md](../docs/auth_migration.md)
- [docs/data_backup_restore.md](../docs/data_backup_restore.md)
- [docs/stabilization_baseline.md](../docs/stabilization_baseline.md)
- [docs/stabilization_stages_0_2.md](../docs/stabilization_stages_0_2.md)
- [docs/stabilization_verification.md](../docs/stabilization_verification.md)
- [scripts/audit_local_data.py](../scripts/audit_local_data.py)
- [scripts/backup_local_data.sh](../scripts/backup_local_data.sh)
- [scripts/local_data.py](../scripts/local_data.py)
- [scripts/repair_orphan_ownership.py](../scripts/repair_orphan_ownership.py)
- [scripts/verify_backup_restore.sh](../scripts/verify_backup_restore.sh)
- [src/app/agent/block_models.py](../src/app/agent/block_models.py)
- [src/app/agent/context.py](../src/app/agent/context.py)
- [src/app/agent/draft_types.py](../src/app/agent/draft_types.py)
- [src/app/api/commit.py](../src/app/api/commit.py)
- [src/app/api/export.py](../src/app/api/export.py)
- [src/app/api/files.py](../src/app/api/files.py)
- [src/app/api/graph.py](../src/app/api/graph.py)
- [src/app/api/notes.py](../src/app/api/notes.py)
- [src/app/api/routes/auth.py](../src/app/api/routes/auth.py)
- [src/app/api/upload.py](../src/app/api/upload.py)
- [src/app/core/auth_provider.py](../src/app/core/auth_provider.py)
- [src/app/core/config.py](../src/app/core/config.py)
- [src/app/core/ownership.py](../src/app/core/ownership.py)
- [src/app/core/security.py](../src/app/core/security.py)
- [src/app/db/migrate.py](../src/app/db/migrate.py)
- [src/app/db/models.py](../src/app/db/models.py)
- [src/app/db/session.py](../src/app/db/session.py)
- [src/app/db/stabilization_schema.py](../src/app/db/stabilization_schema.py)
- [src/app/main.py](../src/app/main.py)
- [src/app/models/session.py](../src/app/models/session.py)
- [src/app/rag/tfidf_index.py](../src/app/rag/tfidf_index.py)
- [src/app/services/sync_engine.py](../src/app/services/sync_engine.py)
- [src/static/css/styles.css](../src/static/css/styles.css)
- [src/static/js/ai_chat.js](../src/static/js/ai_chat.js)
- [src/static/js/editor.js](../src/static/js/editor.js)
- [src/static/js/note_save.js](../src/static/js/note_save.js)
- [tests/conftest.py](../tests/conftest.py)
- [tests/manual_editor_smoke.py](../tests/manual_editor_smoke.py)
- [tests/note_save.test.mjs](../tests/note_save.test.mjs)
- [tests/test_data_safety.py](../tests/test_data_safety.py)
- [tests/test_stabilization.py](../tests/test_stabilization.py)
- [tests/test_sync_engine.py](../tests/test_sync_engine.py)
- [tests/test_upload_api.py](../tests/test_upload_api.py)

## 8. Оставшиеся ограничения

- Рабочая среда сейчас `AUTH_MODE=none`: она увидит только dev-user. Для личных заметок нужен
  вход в свой аккаунт через подходящий режим. Данные не удалены и не переназначены.
- Новые графовые предпочтения персональны; старые общие значения сохранены в legacy-таблице,
  но не копируются произвольно всем аккаунтам. Старым Supabase bridge-сессиям нужен повторный вход.
- Локальный HTTP требует `COOKIE_SECURE=false`. `SameSite=None` требует Secure.
  Опасный `ALLOW_UNSAFE_PUBLIC_NO_AUTH` существует только как явный диагностируемый обход.
- LocalStorage имеет квоту и не шифруется. Браузер может прервать запрос при закрытии;
  резервный черновик защищает только пока доступно хранилище браузера. Ошибка видна пользователю.
  Отдельного UI списка всех черновиков нет: предлагается самый свежий, другие копии сохраняются.
- Старые клиенты без `If-Match` сохраняют прежний API. CRDT, идемпотентность создания заметок
  и общий протокол многоклиентских конфликтов не реализованы этим этапом.
- Отзыв refresh не отзывает уже выданный stateless access JWT до его истечения.
  Полное переустройство сессий и UI доказанного связывания аккаунтов не входят в задачу.
- Sync всё ещё имеет прежние глобальные maps/cursor/state и legacy-очередь. Добавленные
  ownership-проверки не заменяют отдельный выбор/проверку протокола.
- Миграции всё ещё состоят из нескольких механизмов и исторического SQLite-specific кода.
  PostgreSQL-миграции и живое Supabase/Tauri взаимодействие в этот проход не проверялись.
- Отдельно замечен существующий `Permissions-Policy: microphone=()` в web middleware:
  он способен блокировать запись через getUserMedia. Здесь не менялся, поскольку запись аудио
  не относится к этапам 0–2; нужен отдельный небольшой фикс с проверкой веб-записи.

## 9. Готовность к следующему этапу

**Да — к анализу “Sync protocol selection: current implementation vs maksigma”.**
Есть проверяемая точка восстановления, тесты сохранения и изоляции, список известных
проблем данных. Это разрешает сравнительный анализ; не означает готовность к немедленному
merge альтернативного sync, включению FK или продакшен-развёртыванию без отдельной проверки.
Перепроектирование sync и merge maksigma не начинались.
