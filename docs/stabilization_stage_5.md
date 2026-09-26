# Stage 5 — целостность БД, миграции, SQLite/PostgreSQL

Дата проверки: 2026-09-26. Ветка `develop`, изменения локальные, commit/push не выполнялись.
Это отчёт только о Stage 5; ранее накопленные правки Stage 0–4.1 остаются отдельным baseline.
Обновление Stage 5.1: **APPLIED TO REAL WORKING SQLITE / STAGE 5 COMPLETE**.
Фактическое применение, recovery points и повторные проверки описаны в
[stabilization_stage_5_1.md](stabilization_stage_5_1.md). Разделы о baseline и изолированных
прогонах ниже сохраняют исторические результаты проверки реализации Stage 5.

## 1. EXECUTIVE SUMMARY

**STAGE 5 COMPLETE — APPLIED TO REAL WORKING SQLITE.** Первоначальный статус был
READY TO APPLY / NOT APPLIED; в Stage 5.1 получено явное разрешение и выполнен ремонт.
Рабочая SQLite изменена по проверенному плану; uploads и .env не изменены.
В рабочей базе: 0 FK-нарушений, 0 cross-owner links, все 130 заметок, 118 файлов
и 187 quarantined outbox сохранены. Единственный механизм
эволюции схемы — Alembic. Проверены PostgreSQL 16 и SQLite, включая регрессии Stage 4.1.
Stage 6 не начат. Реальный backend успешно запущен, healthz/readyz=200.

## 2. BASELINE VERIFICATION

До изменения database code:
- полный Python: 214 passed, 0 failed/error/skipped, 243 warnings;
- Stage 4.1 и sync входят в этот набор;
- JS: 7 passed, 0 failed/skipped;
- Chromium editor smoke: 9 passed, 0 failed, page errors не обнаружены;
- свежий backup и временное restore: quick_check=ok, 1 299 файлов снимка
  (SQLite + 1 298 объектов storage), 214 уникальных сохранённых путей;
- исходные 117 FK-нарушений явно зафиксированы как исторические;
- legacy audit: 187 quarantined, 0 auto-sendable;
- 1 300 контрольных сумм DB/.env/uploads совпали с checkpoint Stage 4.1;
- git diff --check: PASS.

## 3. MIGRATION ARCHITECTURE BEFORE

Схему одновременно меняли ручной db/migrate.py, stabilization_schema.py, sync_schema.py,
неполный первоначальный Alembic auth revision и ALTER TABLE users в auth-request.
Startup пытался выполнить ручную миграцию, скрывал её ошибку warning, затем запускал ещё
два schema-helper. Тесты создавали ORM metadata напрямую; SQLite FK не были обязательны.

## 4. SELECTED MIGRATION ARCHITECTURE

Одна цепочка Alembic:
`20251225_core → 20251226_init_auth → 20260926_stable → 20260926_integrity`.
Новый core prerequisite позволяет выполнить исторический auth revision на пустой БД.
ID существующего auth revision сохранён; его FK-операции адаптированы к SQLite batch mode.
Замороженный schema_v5.json не зависит от будущих изменений ORM. Новые изменения схемы
должны быть новыми Alembic revision, не редактированием уже выпущенного snapshot.

`app.db.migrate` — runner/detection/transaction guard, без самостоятельного DDL.
Распознанная ручная схема принимается на auth revision и полностью проверяется/доводится
новыми revision. Неизвестные таблицы, будущая sync-schema и неизвестный Alembic head
не угадываются. Compatibility helpers вызывают additive revision; это не готовность к работе.

SQLite: BEGIN IMMEDIATE и временный FK OFF только в maintenance connection для атомарной
пересборки; FK check до commit, FK ON после commit/rollback. PostgreSQL: transactional DDL
и advisory transaction lock. Сбой после создания всех ограничений откатывает таблицы,
данные и marker; повторный запуск проверен на обеих СУБД. Ошибка больше не маскируется.

## 5. CANONICAL SCHEMA

Полная карта всех 24 таблиц, PK/FK/UNIQUE/indexes, nullable ownership, ON DELETE и
совместимости: [database_schema.md](database_schema.md). Плюс Alembic version table.
Сохранены исторические sync_state, group_preferences, sync_note_map, email_verified_at
и совместимые дополнительные поля files. Дополнительные исторические индексы и
ограничения не выкидываются; неизвестные triggers требуют отдельного разбора.

Добавлены целевые составные индексы для notes owner/updated_at, scoped outbox/due,
conflict scope/kind, change-log owner/protocol/sequence; files.note_id индексирован.
Остальные индексы lookup/PK/UNIQUE сохранены. Очистка дублирующихся idx_* не проводилась.
Note.files и User.notes/files теперь используют DB delete semantics через passive_deletes.
Hard delete note отделяет FileAsset (SET NULL), а не удаляет metadata/bytes.
Hard delete user каскадно удаляет его notes/files/session metadata; audit/outbox остаются
с NULL reference. Физические файлы не удаляются; tombstone API не перепроектирован.

## 6. DATA INTEGRITY AUDIT

Рабочая БД до ремонта: 8 users, 130 notes, 118 files, 16 links, 8 tags, 187 legacy outbox.
117 объявленных FK-нарушений: outbox 77, audit 38, refresh 2.
Дополнительно обнаружены 2 outbox.user_id на исчезнувших пользователей: старая таблица
не объявляла этот FK. Поэтому каноническая проверка выявляет **119** сломанных references.
Без их классификации новая схема правильно отказывалась завершать миграцию.

Одна cross-owner связь создана 2026-04-18 17:49:19.267783. Владельцы концов:
`dc39e0d9-3ae1-4e61-b626-37f9d9b82032` и `cc6f5b29-242b-41c9-a584-864ad657e0ad`.
Автор/контекст создания достоверно не восстановлены: audit не содержит ID этой связи.
Текущий продукт не разрешает cross-user relation. Владельцы обеих заметок не меняются.
Бесхозных notes/files и foreign-owner file parents нет; 41 standalone file допустим.

## 7. REPAIR PLAN

Dry-run — поведение по умолчанию, без изменений даже Alembic marker. На текущих данных:
- 79 legacy outbox: архивировать исходную строку и очистить только сломанный note_id/user_id;
- 38 audit_logs: архивировать исходную строку и выставить недействительный user_id=NULL;
- 2 refresh_tokens: архивировать и удалить недействительные сессии без владельца;
- 1 cross-owner note_link: архивировать и удалить само отношение;
- reassociate: 0; ambiguous: 0.

Итого 120 архивных оригиналов. Никаких новых владельцев, повторов sync или преобразования
legacy payload. Блоки, заметки, файлы, audit content, session originals сохраняются.
Архив приватный, не доступен через API и не выводится в консоль. Его original_json может
содержать хеши сессий: резервная копия остаётся приватной и не должна попадать в Git.

Apply требует `--apply --plan --backup`: checksum проверенной копии, соответствие БД,
логический fingerprint схемы/строк, полный повторный dry-run под BEGIN IMMEDIATE,
отсутствие ambiguous, архивирование оригиналов, миграция, FK/quick check в одной транзакции.
Изменение базы после плана/backup или ошибка DDL полностью отменяют apply.

## 8. ISOLATED REPAIR RESULT

Копия настоящей БД и всех storage roots подготовлена отдельно; files.path_* перенесены
только в эту копию. Перед ремонтом копии создана и восстановлена отдельная резервная копия.
После ремонта: quick_check=ok, FK=0, canonical reference issues=0, cross-owner links=0,
head=20260926_integrity.

Счётчики: users 8, notes 130, files 118, links 15, tags 8, outbox 187;
audit_logs 4 250 (не удалялись), refresh_tokens 1 401 (было 1 403), integrity_archive 120.
Проверены 6 413 сохраняющихся строк по всем прежним полям, включая byte-for-byte Text JSON;
отличия только в запланированных references. Все 120 архивных оригиналов совпали с
исходными строками. SHA-256 всех 1 298 storage files совпал.

## 9. SQLITE RESULT

Пустая БД zero→head работает; повторный запуск безопасен. Тесты приложения используют
Alembic, не create_all. Схема реальной восстановленной копии также прошла полный набор:
каждый тест получает отдельный clone этой схемы, приватные строки заменяются тестовыми
fixtures; исходная repaired snapshot не изменяется. Это не запуск destructive tests над
пользовательскими данными.

Отдельный app smoke над populated copy: startup, healthz, readyz, OpenAPI = PASS;
прочитаны 130 заметок и 118 оригинальных вложений. Прежние строки не изменились.
Штатный read-audit добавил 130 событий в disposable app-test copy; это ожидаемая работа
существующего API, не изменение контента и не действие ремонта.

## 10. POSTGRESQL RESULT

Одноразовый PostgreSQL 16 (`pgvector/pgvector:pg16`) с tmpfs data directory,
портом 127.0.0.1:55435 и отдельным именем ovc-stage5-isolated. Пользовательский контейнер
ovc-db-1 и production Supabase не использовались. Fixture разрешает только этот
loopback/port/database; внешний DATABASE_URL не подставляется.

Zero→head, rollback/restart, app readiness, user/login/session rotation, CRUD,
If-Match, preserve-copy, tags/links, attachments, search ownership, sync push/pull,
idempotent receipts, concurrent conflicts, tombstone, file mappings, cursors = PASS.
Один и тот же набор critical contracts выполняется на обеих СУБД; sync pair проверяет
SQLite client ↔ PostgreSQL server. Portable fix: sequence TEXT counter увеличивается
как BIGINT и явно приводится обратно к TEXT. Остальная семантика sync v1 не изменена.

## 11. READINESS

`GET /healthz`: 200 означает живой процесс.
`GET /readyz`: 200 только при reachable DB, ожидаемом Alembic head, required tables/columns,
FK ON на SQLite connection и доступном для чтения/записи storage root. Проверка storage
использует удаляемый temporary file. Возвращаются только boolean checks, без URL/токенов/SQL.
При проблеме — 503. Startup делает те же проверки и завершает запуск ошибкой, а не warning.

Production: миграции явно до worker startup. Development/test: автоматическая миграция
допустима только при DB_AUTO_MIGRATE=true; default false. В production этот флаг запрещён.
Готовность не заменяет регулярный полный integrity audit/backup; live probes не сканируют
все строки и все исторические связи при каждом запросе.

## 12. LEGACY SYNC SAFETY

После ремонта legacy audit: pending_total=187, pending_legacy=187, quarantined=187,
pending_nonlegacy=0, automatic_migration_allowed=0. Все payload/status/tries сохранены;
protocol_version остаётся 0, queue client_id/remote_key не создаются. В sync_identity
создаются только служебные идентификаторы новой схемы данной БД.
Ссылки на исчезнувшие файлы внутри legacy payload остаются историей; они не превращаются
в активные операции. Replay/migration очереди требует отдельного будущего задания.

## 13. BACKUP / RESTORE RESULT

Проверен backup после ремонта и независимый restore: head совпадает, quick_check=ok,
FK=0, все table counts совпадают, 214 stored paths найдены, 1 299 checksum entries совпали.
Новый manifest включает все таблицы, schema revision и FK count. Старые manifests совместимы.
FK violation в БД, утверждающей текущий head, теперь делает backup/verify неуспешным.
[Процедура восстановления](data_backup_restore.md). PostgreSQL dump/restore production
не выполнялись: это SQLite backup tooling и изолированная проверка PostgreSQL runtime.

## 14. TEST RESULTS

Финальные запуски:
- SQLite clean full Python: **233 passed, 0 failed/error/skipped, 243 warnings** (72.51 s).
- Upgraded SQLite schema full Python: **233 passed, 0 failed/error/skipped, 243 warnings** (33.28 s).
- PostgreSQL integration/parity: **158 passed, 0 failed/error/skipped, 225 warnings** (127.05 s).
- В каждом из этих прогонов: Stage 4.1 **12/12**, sync **103/103**, новые Stage 5 **19/19**;
  это подмножества указанных итогов, а не дополнительные тесты.
- Node: **7 passed, 0 failed/skipped**.
- Chromium browser: **9 passed, 0 failed**, включая stale recovery/attachments/logout-save.
- Real-copy app smoke: **130 notes + 118 files** прочитаны; startup/readiness/OpenAPI PASS.
- AST syntax изменённых Python, JSON snapshot, git diff --check: PASS.

Предупреждения — существующие Pydantic/FastAPI/Starlette/PyMuPDF deprecations; cleanup вне
Stage 5. PostgreSQL результат — integration subset, не весь Python suite: остальные
unit/viewer tests выполнены полным набором на SQLite. Ни один обязательный PG сценарий
не был пропущен. Первые тестовые сбои (новый undeclared FK, legacy future-version guard,
старые fixtures без реального user) исправлены и проверены этими финальными прогонами.

Воспроизводимые команды из корня OVC:
```bash
.venv/bin/python -B -m pytest -q
node --test tests/note_save.test.mjs
.venv/bin/python -B tests/manual_editor_smoke.py
# На read-only snapshot уже отремонтированной копии; сами tests пишут в свой tmpdir:
OVC_STAGE5_SQLITE_SEED=/path/to/repaired/database.sqlite3 .venv/bin/python -B -m pytest -q
# Только одноразовый PG на указанном fixture guard адресе/порту/DB:
OVC_STAGE5_POSTGRES_URL='postgresql+psycopg2://postgres:stage5-isolated-test-only@127.0.0.1:55435/ovc_stage5' \
  .venv/bin/python -B -m pytest -q tests/test_stabilization.py tests/test_sync_protocol.py \
  tests/test_sync_engine.py tests/test_stage41.py tests/test_stage5.py
```
Последняя строка требует предварительно созданного disposable PostgreSQL с тестовым
паролем из примера; это не секрет рабочей базы.

Воспроизведение отдельного контейнера (не использовать существующую рабочую БД):
```bash
docker run -d --name ovc-stage5-isolated --label ovc.task=stage5 \
  --publish 127.0.0.1:55435:5432 \
  --env POSTGRES_PASSWORD=stage5-isolated-test-only --env POSTGRES_DB=ovc_stage5 \
  --tmpfs /var/lib/postgresql/data pgvector/pgvector:pg16
docker exec ovc-stage5-isolated pg_isready
# После тестов удалить только этот созданный для теста контейнер:
docker rm -f ovc-stage5-isolated
```

## 15. FILES CHANGED

Ниже только Stage 5, без ранее накопленных изменений Stage 0–4.1:

- [.env.example](../.env.example)
- [README.md](../README.md)
- [alembic/env.py](../alembic/env.py)
- [alembic/schema_v5.json](../alembic/schema_v5.json)
- [alembic/versions/20251225_core_bootstrap.py](../alembic/versions/20251225_core_bootstrap.py)
- [alembic/versions/20251226_init_auth_tables.py](../alembic/versions/20251226_init_auth_tables.py)
- [alembic/versions/20260926_stable_baseline.py](../alembic/versions/20260926_stable_baseline.py)
- [alembic/versions/20260926_integrity.py](../alembic/versions/20260926_integrity.py)
- [docs/auth_migration.md](../docs/auth_migration.md)
- [docs/data_backup_restore.md](../docs/data_backup_restore.md)
- [docs/database_schema.md](../docs/database_schema.md)
- [docs/stabilization_stage_5.md](../docs/stabilization_stage_5.md)
- [scripts/local_data.py](../scripts/local_data.py)
- [scripts/migrate_desktop_to_shared.py](../scripts/migrate_desktop_to_shared.py)
- [scripts/repair_database_integrity.py](../scripts/repair_database_integrity.py)
- [scripts/repair_orphan_ownership.py](../scripts/repair_orphan_ownership.py)
- [src/app/api/routes/auth.py](../src/app/api/routes/auth.py)
- [src/app/core/config.py](../src/app/core/config.py)
- [src/app/db/engine.py](../src/app/db/engine.py)
- [src/app/db/integrity_repair.py](../src/app/db/integrity_repair.py)
- [src/app/db/migrate.py](../src/app/db/migrate.py)
- [src/app/db/migration_steps.py](../src/app/db/migration_steps.py)
- [src/app/db/models.py](../src/app/db/models.py)
- [src/app/db/readiness.py](../src/app/db/readiness.py)
- [src/app/db/session.py](../src/app/db/session.py)
- [src/app/db/stabilization_schema.py](../src/app/db/stabilization_schema.py)
- [src/app/db/sync_schema.py](../src/app/db/sync_schema.py)
- [src/app/main.py](../src/app/main.py)
- [src/app/models/user.py](../src/app/models/user.py)
- [src/app/services/sync_protocol.py](../src/app/services/sync_protocol.py)
- [src/requirements.txt](../src/requirements.txt)
- [tests/conftest.py](../tests/conftest.py)
- [tests/fixtures/stage5_legacy_schema.sql](../tests/fixtures/stage5_legacy_schema.sql)
- [tests/manual_editor_smoke.py](../tests/manual_editor_smoke.py)
- [tests/test_stabilization.py](../tests/test_stabilization.py)
- [tests/test_stage5.py](../tests/test_stage5.py)
- [tests/test_sync_engine.py](../tests/test_sync_engine.py)
- [tests/test_sync_protocol.py](../tests/test_sync_protocol.py)
- [tests/test_upload_api.py](../tests/test_upload_api.py)

## 16. REAL WORKING DATA

**Рабочая DB: изменена в Stage 5.1. Uploads: НЕ изменены. .env: НЕ изменён.**
До применения Stage 5.1 все 1 300 исходных SHA-256 совпали с checkpoint Stage 5.
После ремонта проверены все исходные строки с учётом плана, 120 архивных оригиналов,
1 298 storage files и .env. 16 запросов чтения создали только штатные NOTE_READ audit
events; текущий audit_logs=4 266. Destructive regression tests по-прежнему изолированы.
Отправки в Git, production/Render/Supabase изменений и изменений Tauri runtime нет.

## 17. REMAINING RISKS

- Реальная БД уже на head после Stage 5.1. Другая старая копия потребует своего reviewed
  repair; нельзя переиспользовать прежний JSON-план. Alembic должен быть установлен
  в Python environment, которым запускается backend.
- Исторический автор cross-owner link не доказан; связь архивируется без смены владельцев.
- Новые ambiguous rows или неизвестные таблицы/triggers остановят repair/upgrade. Перед
  применением всегда свежие backup и dry-run; старый план не следует использовать после edits.
- Nullable legacy owners сохраняются ради совместимости, но не присваиваются автоматически.
  Direct administrative SQL не заменяет ownership API/RLS; перенос владельца заметки требует
  проверки зависимых данных. Новый link INSERT/UPDATE защищён DB trigger.
- Legacy queue остаётся неактивной, недостающие bytes для старых payload не восстанавливались.
- Исторические дополнительные индексы могут дублировать канонические; удаления не проводились.
- PostgreSQL проверен локально на PG16, не на production extensions/RLS/network/deployment.
- Backup содержит приватный архив и hashed sessions, не зашифрован. Не хранить его в Git.
- Desktop packaging, file GC, log compaction, auth redesign и warning cleanup не выполнялись.

## 18. REAL DB REPAIR STATUS

**B) APPLIED — explicitly authorized and verified in Stage 5.1.**
PRE backup: `data/backups/stage5-apply-20260926-200444`.
POST backup: `data/backups/stage5-apply-20260926-200444-after`.
120 действий выполнены атомарно, head `20260926_integrity`, FK=0. Backend readyz=200,
233 Python / 7 JS / 9 browser PASS. Полные результаты: [Stage 5.1](stabilization_stage_5_1.md).

Ниже сохранена общая процедура для отдельной старой базы. На уже отремонтированной
рабочей БД повторно выполнять прежний план не нужно; guard отклонит его как устаревший.

Сначала остановить процессы, пишущие в DB/uploads: web, local desktop backend, sync.
Из корня OVC создать немедленную свежую точку восстановления и read-only план:
```bash
cd /Users/vjachikslavny/OVC
export DATABASE_URL="sqlite:///$PWD/src/ovc.db"
export OVC_UPLOAD_ROOT="/Users/vjachikslavny/data/uploads"
OVC_STAGE5_BACKUP="$PWD/data/backups/stage5-$(date +%Y%m%d-%H%M%S)"
.venv/bin/python -B scripts/local_data.py backup "$OVC_STAGE5_BACKUP"
.venv/bin/python -B scripts/local_data.py verify "$OVC_STAGE5_BACKUP"
.venv/bin/python -B scripts/repair_database_integrity.py \
  --database "$PWD/src/ovc.db" --output "$OVC_STAGE5_BACKUP/repair-plan.json"
```
Просмотреть план: 117 declared / 119 canonical reference violations, 120 actions,
0 ambiguous на проверенном checkpoint. Если данные изменились, число может измениться;
**это новый план для отдельного разбора**, а не основание пропускать защиту.

Только после одобрения свежего плана:
```bash
.venv/bin/python -B scripts/repair_database_integrity.py \
  --database "$PWD/src/ovc.db" --apply \
  --plan "$OVC_STAGE5_BACKUP/repair-plan.json" --backup "$OVC_STAGE5_BACKUP"
.venv/bin/python -B scripts/repair_database_integrity.py --database "$PWD/src/ovc.db"
.venv/bin/python -B scripts/audit_legacy_sync.py --database "$PWD/src/ovc.db" --summary-only
OVC_STAGE5_AFTER="${OVC_STAGE5_BACKUP}-after"
.venv/bin/python -B scripts/local_data.py backup "$OVC_STAGE5_AFTER"
.venv/bin/python -B scripts/local_data.py verify "$OVC_STAGE5_AFTER"
.venv/bin/python -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 8000
```
В другом терминале после запуска:
```bash
curl --fail http://127.0.0.1:8000/readyz
```
Ожидается zero FK/cross-owner/ambiguous и 187 quarantined/0 auto-sendable на прежних данных.
Если apply завершится ошибкой, все изменения откатятся; сначала устранить причину и
сформировать новый plan/backup. Восстановление после успешного commit — через проверенную
копию в новый каталог; не делать destructive Alembic downgrade.

### Production/clean DB procedure

Provision DB/storage/config и backup существующей базы — отдельные административные шаги.
Остановить конкурирующие писатели. Для пустой/распознанной чистой БД:
```bash
.venv/bin/python -m pip install -r src/requirements.txt
PYTHONPATH=src .venv/bin/python -m app.db.migrate
# Только после exit code 0:
.venv/bin/python -m uvicorn app.main:app --app-dir src --host 0.0.0.0 --port "$PORT"
```
`DATABASE_URL`, `OVC_UPLOAD_ROOT`, `APP_ENV`, auth secrets и PORT задаются окружением deploy.
В production DB_AUTO_MIGRATE=false. Runner не чинит историческую грязную SQLite молча:
сначала controlled repair. Несколько workers не должны сами выполнять независимые migrations.
Для обычной zero→head базы также работает `PYTHONPATH=src .venv/bin/alembic upgrade head`;
ручную старую схему нужно принимать через checked runner/repair, а не blind `alembic stamp head`.

## 19. READY FOR STAGE 6?

**GO — safe to begin Stage 6**

Изолированные проверки Stage 5 и применение/проверки реального окружения Stage 5.1
завершены. Рабочая база готова к дальнейшей разработке. Stage 6 в этом задании не начинался.
