# Stage 5.1 — применение ремонта к рабочей SQLite

Дата: 2026-09-26. Область: только применение уже проверенного Stage 5 и проверка реального
окружения. Миграции, auth/editor/sync, Cloudflare, Tauri и AI не перепроектировались.

## 1. EXECUTIVE VERDICT

**STAGE 5 COMPLETE**

**APPLIED TO REAL WORKING SQLITE.** Явное разрешение на применение получено в задании
Stage 5.1. Ремонт завершён атомарно, рабочая БД на head `20260926_integrity`, quick_check=ok,
FK/canonical/cross-owner=0. Реальный backend запущен и готов. Два recovery point проверены
восстановлением, все регрессии проходят. Stage 6 не начат, commit/push не выполнялись.

## 2. PRE-APPLY STATE

Ветка `develop`, HEAD `5250d1754744b50a30cbfdaab63875f03635ecd0`.
Stage 0–5 оставались локальными/uncommitted: 37 modified tracked files и 42 untracked
entries (как показывает git status --short; директории считаются одной строкой).
Полный список перед применением сохранён в приватном `environment-before.json` evidence.
Во время Stage 5.1 runtime code не изменялся; обновлены только README и отчёты.

DATABASE_URL: `sqlite:////Users/vjachikslavny/OVC/src/ovc.db`.
DB path: `/Users/vjachikslavny/OVC/src/ovc.db`.
Upload root: `/Users/vjachikslavny/data/uploads`.
APP_ENV=development, AUTH_MODE=none, SYNC_MODE=off, SYNC_ENABLED=false,
DESKTOP_MODE=false, DB_AUTO_MIGRATE=false. Эти настройки сохранены.

До backup и непосредственно перед apply проверены процессы, открытые DB/upload handles,
слушатели web 8000 и desktop 18741. Активных OVC writers не было, останавливать/убивать
чужие процессы не понадобилось. В БД — 19 старых таблиц, без Alembic marker, без неизвестных
таблиц/триггеров. Все 1 300 DB/.env/upload SHA-256 совпали с прежним checkpoint Stage 5.

Счётчики: users=8, notes=130, files=118, links=16, tags=8, refresh=1 403, audit=4 250,
legacy outbox=187. Declared FK=117, canonical broken references=119, cross-owner link=1,
orphan notes/files=0, invalid file parent ownership=0, ambiguous=0.

## 3. PRE-APPLY BACKUP

Recovery ID: `stage5-apply-20260926-200444`.
Путь: `/Users/vjachikslavny/OVC/data/backups/stage5-apply-20260926-200444`.

Новая SQLite backup API snapshot, storage originals/derivatives, внешние files.path_*,
manifest SHA-256, все table counts и schema metadata. Временное restore успешно:
quick_check=ok, 1 299 checksum entries проверены (DB + 1 298 storage files),
214 stored paths доступны. Исторические 117 declared FK явно зафиксированы.
VERIFIED.json создан. Source/snapshot counts до применения полностью совпали.

Рядом со снимком сохранены fresh `repair-plan.json`, `safety-review.json`,
`audit-before.json`, `legacy-before.json`. Companion safety review связывает план
по SHA-256 с backup manifest/database checksum и отдельным schema fingerprint.
Формат проверенного repair tool не изменён; apply получает именно исходный fresh plan.

## 4. FRESH REPAIR PLAN

Свежий read-only план полностью совпал с предыдущим проверенным checkpoint, включая
fingerprint и row IDs. Не только сходство счётчиков: никаких различий данных/схемы не найдено.

- Declared FK: 117; canonical broken references: 119.
- Repair actions: 120; ambiguous: 0.
- 79 legacy outbox: архивировать оригинал, очистить только доказанно сломанный user_id/note_id.
- 38 audit_logs: архивировать оригинал, очистить недействительный user_id.
- 2 refresh_tokens: архивировать, удалить сессии без владельца.
- 1 cross-owner note_link: архивировать, удалить только отношение.
- Ownership reassignment, note/file/block deletion, legacy replay/protocol upgrade: 0.

Перед apply повторно проверены backup checksums/VERIFIED, DB/plan fingerprint, схема,
разрешённые таблицы/колонки действий и ожидаемые post counts. Новых triggers/head не было.
Schema/data drift отсутствует, поэтому дополнительных согласований не потребовалось.

## 5. APPLY RESULT

Использован существующий CLI без обхода guard:
```bash
.venv/bin/python -B scripts/repair_database_integrity.py \
  --database /Users/vjachikslavny/OVC/src/ovc.db --apply \
  --plan /Users/vjachikslavny/OVC/data/backups/stage5-apply-20260926-200444/repair-plan.json \
  --backup /Users/vjachikslavny/OVC/data/backups/stage5-apply-20260926-200444
```
Это запись уже выполненной операции, **повторно запускать старый план не нужно**.
Exit code=0, applied=true, archived_rows=120. Оригиналы, repair, Alembic upgrade и проверки
выполнены внутри существующей атомарной транзакции. Она успешно зафиксирована;
rollback/restore рабочего файла не понадобились. Blind stamp/create_all не использовались.

## 6. POST-APPLY INTEGRITY

Сразу после commit:
- quick_check=ok, foreign_key_check=0, canonical reference issues=0, cross-owner links=0;
- Alembic head=`20260926_integrity`, FK ON на прикладной SQLAlchemy connection;
- users=8, notes=130, files=118, tags=8, links=15;
- refresh_tokens=1 401, audit_logs=4 250, outbox=187, integrity_archive=120;
- все остальные старые table counts совпали; новые служебные sync identities=4,
  mapping/peer/user-group tables пусты. Прогноз свежего плана совпал с результатом.

После read smoke audit_logs=4 266: добавлены ровно 16 штатных NOTE_READ. Это единственная
дополнительная запись в рабочие данные после repair commit; остальные строки/счётчики
не изменились. Повторная проверка FK/canonical/link/legacy после тестов также PASS.

## 7. DATA PRESERVATION

6 413 сохраняющихся строк сравнены по всем исходным столбцам с PRE backup.
Различия допустимы только в предусмотренных планом nullable references.
Все 120 архивных оригиналов совпали с исходными строками; удалены только две сессии
и одно отношение, сохранённые в архиве. Все 130 notes, blocks_json, revisions, owners,
118 file metadata и пути сохранены. Все 1 298 upload file SHA-256 и .env совпали;
дополнительных upload files не появилось. Бесхозные данные никому не назначались.

Read smoke отдельно сравнил текущие строки с POST snapshot: никаких изменений за
пределами 16 новых NOTE_READ audit events. Файлы отдавались с совпадающими контрольными
суммами. Временная readiness storage probe удаляется и не меняет пользовательские bytes.

## 8. LEGACY SYNC

Реальный legacy audit после repair и повторно после tests:
pending total=187, pending legacy=187, quarantined=187, pending nonlegacy=0,
automatic migration allowed/auto-sendable=0, migrated=0, replay=0.

Прежние payload/status/tries сохранены. protocol_version=0, queue client_id/remote_key
не изобретались. Новые sync_identity IDs относятся к БД, не к legacy операциям.
Remote worker не включался. Отсутствующие файлы, упомянутые внутри старых payload,
не подменялись и не восстанавливались автоматически.

## 9. POST-APPLY BACKUP

Recovery ID: `stage5-apply-20260926-200444-after`.
Путь: `/Users/vjachikslavny/OVC/data/backups/stage5-apply-20260926-200444-after`.

Создан сразу после ремонта, до запуска backend/read smoke. Временный restore успешен:
head=`20260926_integrity`, quick_check=ok, FK=0, все table counts и checksums совпали,
214 file paths доступны, integrity_archive=120 включён. VERIFIED.json есть.

Оба recovery point повторно проверены восстановлением после regression suite.
POST snapshot содержит audit=4 250; live DB содержит +16 объяснённых событий чтения.
Инструмент явно показывает эту разницу source counts, не изменяет backup и не скрывает её.
Это не потеря/изменение пользовательского контента. PRE snapshot хранит исходную старую
схему и исторические FK нарушения для контролируемого восстановления в новый путь.

## 10. REAL BACKEND

Запущен `/Users/vjachikslavny/OVC/.venv/bin/python -m uvicorn app.main:app`
на `127.0.0.1:8000`, PID при проверке **34503**. Без reload и access log, с SYNC_MODE=off /
SYNC_ENABLED=false. Runtime auth/environment остались прежними, .env не редактировался.
Миграционный guard пройден. healthz=200, readyz=200; database/revision/tables/columns/
foreign_keys/storage=true. OpenAPI=200. Startup errors/schema failures нет.

28 успешных HTTP GET к реальному серверу в настроенном AUTH_MODE=none, от уже существующего
совместимого dev-user. Новая identity не создавалась. Проверено: notes list и HTML, все
16 доступных этой identity заметок, два её оригинальных файла, одна связь, graph HTML/data,
tags, profile metadata, search (13 совпадений), OpenAPI. Тексты/профиль/токены в отчёт
не выводились. Остальные пользовательские записи проверены полным DB-сравнением,
а не обходом авторизации. Реальных tombstones сейчас 0; их скрытие подтверждено на
изолированных fixtures regression suite, реальные данные ради этого не изменялись.

Сервер оставлен работающим для локального продолжения. Если процесс позже завершится:
```bash
cd /Users/vjachikslavny/OVC
SYNC_MODE=off SYNC_ENABLED=false PYTHONPATH=src .venv/bin/python -m uvicorn \
  app.main:app --app-dir src --host 127.0.0.1 --port 8000
```
Не запускать второй экземпляр на занятом порту.

## 11. TEST RESULTS

Все эти прогоны выполнены после успешного применения реального repair:
- Full Python: **233 passed, 0 failed, 0 errors, 0 skipped, 243 warnings**, 73.20 s.
- Stage 4.1: **12/12**; sync protocol + engine: **103/103**; Stage 5: **19/19**.
  Это части full suite, не дополнительные тесты.
- JS note-save: **7 passed, 0 failed/skipped**.
- Chromium editor smoke: **9 passed**, без page errors; DB/storage/port теста изолированы.
- PRE/POST backup + isolated restore: **PASS / PASS**, проверены повторно после tests.
- Real legacy audit и финальный FK/ownership audit: **PASS**.
- AST syntax src/app, scripts, Alembic: **PASS**; git diff --check: **PASS**.

243 предупреждения — прежние deprecations; чистка не проводилась.
PostgreSQL заново не поднимался: Stage 5 уже проверил 158/158 на PG16, runtime code
не изменился, Stage 5.1 требует применение к SQLite, не новую PG/hosting migration.

Optional safe local sync smoke покрыт full suite: `test_standard_create_update_pull_and_durable_cursor`,
`test_user_switch_legacy_quarantine_and_wrong_token`, `test_all_187_legacy_rows_remain_unchanged_with_null_owner`.
Они проверяют новые v1 outbox/scope, доставку между изолированными БД и сохранение legacy.
Реальная очередь не использовалась, production credentials/remote worker не требовались.

## 12. WORKING ENVIRONMENT

- DB modified: **YES**, только одобренный repair/migration и 16 штатных read-audit событий.
- Uploads modified: **NO** (originals/derivatives и полный состав файлов совпали).
- .env modified: **NO**.
- Production remote modified: **NO**.
- Runtime code modified in Stage 5.1: **NO**.
- Commit/push: **NO**; Stage 6 started: **NO**.

Обновлены README.md, docs/stabilization_stage_5.md и этот docs/stabilization_stage_5_1.md.
Приватные планы/manifest/checksums/архивы находятся в игнорируемом data/backups,
операционные logs/evidence — /private/tmp/ovc-stage51. Note content, tokens,
password/session hashes и original_json в публичную документацию не включены.

## 13. REMAINING RISKS

- AUTH_MODE=none сохранён как исходный development mode; live HTTP smoke проверял его
  существующего dev-user, а не вход во все восемь аккаунтов. Auth/session регрессии
  отдельно прошли на isolated local-auth fixtures.
- На реальных данных нет tombstones; проверка этого edge case изолированная.
- Legacy queue остаётся карантином и может содержать ссылки на уже отсутствующие файлы.
  Автоматического replay нет; новый scope или восстановление bytes — отдельное задание.
- Backup/архив содержат приватные DB данные; не коммитить и не публиковать их.
- Запущенный backend локальный, remote sync выключен. Packaging/production/deprecation
  cleanup не проверялись повторно и не выполнялись, как требовало задание.
- Recovery points фиксируют моменты до/сразу после repair; более поздняя легитимная
  работа требует следующих регулярных backups. Старый repair-plan уже устарел для live DB.

Блокирующих проблем Stage 5 не осталось.

## 14. STAGE 5 FINAL STATUS

**STAGE 5 COMPLETE — real working SQLite is repaired, migrated, verified, backed up, and ready for further development.**

## 15. READY FOR STAGE 6?

**GO — safe to begin Stage 6**

Stage 6 не начат. Работа остановлена на завершении Stage 5/5.1.
