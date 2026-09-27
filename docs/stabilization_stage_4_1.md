# Этап 4.1 — Cross-subsystem consistency repair

Проверено 2026-09-26. Ветка `develop`, исходный HEAD `5250d17`.
Изменения локальные, поверх незакоммиченных этапов 0–4. Commit/push не выполнялись.

## 1. SUMMARY

Исправлены ровно четыре дефекта независимой проверки: повторное использование
локального ETag после sync-конфликта, зависимость вложений recovery-копии от оригинала,
отказ всей заметки из-за удалённой цели связи и ложный успешный результат preflight sync.
Схема БД, модель блоков, режимы auth и протокол v1 не заменялись. Новых зависимостей
и переменных окружения нет. Этап 5 не начат.

Изменённые в этом этапе файлы:

- `src/app/services/sync_protocol.py`: локальная ревизия, общий preserve-copy, конфликты связей.
- `src/app/services/sync_engine.py`: ack/pull, сохранение relation conflicts, единые результаты/status.
- `src/app/api/notes.py`: защищённый endpoint восстановления копии.
- `src/static/js/editor.js`: recovery через этот endpoint.
- `src/static/js/data_adapter.js`: явное отображение ошибок операций и связей.
- `tests/test_stage41.py`: 12 постоянных regression-проверок.
- `tests/manual_editor_smoke.py`: проверка всех вложений восстановленной копии в браузере.
- `README.md`, `docs/sync_protocol_v1.md`, этот отчёт: актуальный контракт и результаты.

## 2. P0-01 — revision / ETag

Причина: `_ack` и `_apply_page` присваивали `Note.revision` удалённое число.
Одинаковые номера могли обозначать разные локальные состояния. Проверка `If-Match`
поэтому принимала старую версию редактора после подмены содержимого через pull.

Исправление: ack меняет mapping/receipt, не локальный ETag. Pull сравнивает aggregate;
при изменении состояния вызывает общий `advance_local_revision`. Локальный
`updatedAt`, который ещё поддерживается как старый If-Match, также растёт монотонно.
Подтверждение собственного идентичного snapshot не инвалидирует редактор. Удалённая
ревизия остаётся в `SyncEntityMap.remote_revision` и receipts для будущего sync base.

Файлы: `sync_engine.py`, `sync_protocol.py`, `test_stage41.py`.

Регрессия: локальное и удалённое содержимое достигают одного номера ревизии;
после конфликта оригинал получает remote-содержимое с новым локальным номером.
Старый numeric/timestamp If-Match получает 409; устаревший AI `baseRevisions` — тоже 409.
Следующий sync не перезаписывает remote. Отдельно проверены ack при разных пространствах
ревизий, отсутствие ложного конфликта после собственного echo и следующая нормальная правка.
Все проверки прошли.

## 3. P1-01 — вложения recovery-копии

Причина: `recoverDraft` делал обычный `POST /api/notes`, копируя URL исходных FileAsset.
После tombstone оригинала строгий file ownership guard закономерно возвращал 404.

Исправление: редактор использует `POST /api/notes/{id}/recovery-copy`. Endpoint проверяет
владельца исходной заметки, допускает его tombstone и вызывает тот же `preserve_copy`,
что sync. Каждое вложение получает новый FileAsset ID, родителя-копию и переписанные
ссылки в канонических блоках. Физические оригиналы/preview-пути разделяются безопасно
без дублирования байтов. Проверки чужого файла/родителя остаются строгими; ошибка
откатывает транзакцию. При remote-sync копия и uploads ставятся в обычную очередь.

Файлы: `notes.py`, `sync_protocol.py`, `editor.js`, `test_stage41.py`, `manual_editor_smoke.py`.

Регрессия: копия читается до и после удаления оригинала; её FileAsset принадлежит
копии и тому же пользователю. Проверены уже tombstoned оригинал, отказы другому
пользователю и попытка подложить чужие вложения. Desktop recovery → upload → sync
проходит после удаления оригинала. Прежний тест sync conflict-copy с вложением
также проходит. Реальный Chromium восстанавливает черновик через UI, проверяет
байты всех вложений и повторяет чтение после удаления оригинала.

## 4. P1-02 — удалённая цель связи

Причина: `replace_note` проверял каждую связь как ссылку только на живую заметку;
одна tombstone вызывала 404 и permanent failure всего snapshot с новым текстом.

Выбран минимальный вариант B: нормализация полного snapshot. Если цель существует,
принадлежит тому же пользователю и является tombstone, тело заметки и живые связи
применяются, а исходные `toId/reason/confidence` сохраняются как `relation_target_deleted`
в `SyncConflict`. Сервер сохраняет их в одной транзакции с изменением и receipt;
ответ содержит `relation_conflicts`. Клиент сохраняет эти сведения при ack.
Операция остаётся `applied`, target не восстанавливается, активной связи не возникает.

Детали доступны в durable receipt (`result_json`) и `sync_conflicts`, привязаны
к владельцу/source note/op/client/remote. В status/trigger есть `relationConflicts`,
desktop показывает «конфликты связей». Replay op_id не дублирует запись. Отсутствующая
или чужая цель по-прежнему отклоняется, как и новая CRUD/AI-связь на tombstone.

Файлы: `sync_protocol.py`, `sync_engine.py`, `data_adapter.js`, `test_stage41.py`.

Регрессия A→B: offline-правка A достигает сервера после remote delete B; B остаётся
tombstone, активной связи нет, очередь продолжает следующие правки A. Конфликт
записан на обеих сторонах, счётчик изолирован по пользователю. Replay и три сценария
невалидной ownership/missing цели прошли.

## 5. P1-03 — согласованный результат sync

Причина: `_claim` мог записать `failed_permanent`, вернув None, но trigger считал
только исключения после отправки. Получалось `ok=true/failed=0` при ошибке в очереди.

Исправление: `_cycle_result` использует ту же durable сводку, что `/api/sync/status`.
`failed` — число permanent failures текущего scope, включая preflight и прежние циклы.
При таких ошибках `ok=false`; `pending/retry/lastError` совпадают со status. Сеть/auth
также возвращают `ok=false` с отдельным reason, не выдавая retry за permanent failure.
Backoff очереди не превращается в ложный успех. Сохранённый row error остаётся видимым,
даже если hello/pull очистил старую транспортную ошибку peer. Desktop прежде всего
показывает число failed operations, затем прочие ошибки.

`ok=true` не означает пустую очередь или отсутствие сохранённых конфликтов:
для них есть отдельные counters. `lastSuccessAt` — успешная связь/применение pull,
не гарантия успешности всех операций. Worker и manual trigger используют общий путь.

Файлы: `sync_engine.py`, `data_adapter.js`, `test_stage41.py`.

Регрессия: после изменения владельца до claim операция получает permanent failure,
payload не отправляется, два последовательных цикла и реальные trigger/status API
показывают одинаковые `failed=1`, `pending=1`, `lastError`. Проверка прошла.

## 6. REVISION MODEL

- `Note.revision`: локальное наблюдаемое состояние aggregate для editor, CRUD, AI и If-Match.
  Изменение через pull увеличивает его; чужое число ему не присваивается.
- `SyncEntityMap.remote_revision`: последняя подтверждённая версия этой сущности на
  конкретном remote. Она или receipt предшественника задаёт sync `base_revision`.
- `SyncChangeLog.sequence` / peer cursor: порядок доставки событий сервера,
  не версия содержимого и не третий ETag. Применение страницы и cursor атомарны.

## 7. CONFLICT / RECOVERY MODEL

Один `preserve_copy` обслуживает editor recovery и sync conflicts. Общая семантика:
канонический snapshot, новая Note, независимые FileAsset IDs/родитель, тот же owner,
переписанные URL, сохранённые байты. Для editor меняется только суффикс названия.
Сохранение копии не требует оживления оригинала и не ослабляет доступ к его файлам.
Отклонённые tombstone-связи копий также сохраняются отдельными conflict-записями.
Очистка локального черновика в браузере происходит только после успешного ответа.

## 8. TEST RESULTS

- Полный Python suite: **214 passed / 0 failed / 0 skipped**, включая прежние 202 теста.
- Новые постоянные проверки: **12 passed / 0 failed / 0 skipped** в `test_stage41.py`.
  Все четыре исходных adversarial-сценария закрыты (attachment сценарий проверен
  с двумя моментами tombstone). Дополнительно проверены AI, echo/ack, ownership,
  replay, normal CRUD и desktop recovery sync.
- Прежние sync suites внутри полного прогона: engine **34/34**, protocol **69/69**.
- JS: **7/7**, без failed/skipped.
- Chromium: **9/9**, без page errors; recovery сценарий расширен проверкой вложений.
- Backup/restore: **PASS**, fresh backup в `/private/tmp/ovc-stage41/backup`, 1299
  файлов снимка, 214 stored paths, `quick_check=ok`; восстановление в отдельный temp.
- Legacy audit: **PASS**, 187 pending legacy / 187 quarantined / 0 автоматически мигрировано.
- Python AST: **78 модулей** app/tests/scripts разобраны; `node --check` editor/data_adapter/note_save — PASS.
- `git diff --check`: **PASS**.
- 243 предупреждения Python (deprecations и существующая конфигурация Pydantic)
  оставлены в рамках запрета на несвязанный cleanup; ошибок тестов нет.

Первый запуск основных новых проверок до правок дал **5 failed**: ETag, два варианта
recovery, deleted relation и preflight. Затем сценарии прошли на исправленном коде.
Браузерная проверка дополнительно отличает копию metadata от старых URL оригинала.

Воспроизведение из корня репозитория:

```bash
.venv/bin/python -B -m pytest -q --tb=short
.venv/bin/python -B -m pytest tests/test_stage41.py tests/test_sync_engine.py tests/test_sync_protocol.py -q
node --test tests/note_save.test.mjs
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tests/manual_editor_smoke.py
./scripts/backup_local_data.sh /private/tmp/ovc-stage41-new-backup
./scripts/verify_backup_restore.sh /private/tmp/ovc-stage41-new-backup
.venv/bin/python -B scripts/audit_legacy_sync.py --summary-only
git diff --check
```

Тестовые БД и uploads изолируются fixtures/browser harness; реальный model API
и внешние HTTP-ресурсы не используются. Результаты последнего прогона сохранены
в `/private/tmp/ovc-stage41` и отдельно в `OVC-stage41-evidence` среди локальных
артефактов этой задачи. Секреты, БД и вложения в артефакты отчёта не копировались.

## 9. WORKING DATA SAFETY

Сравнение SHA-256 и перечня файлов до/после: **1300/1300 без изменений**.

- Рабочая `src/ovc.db`: не изменилась.
- `.env`: не изменился.
- 1298 файлов `/Users/vjachikslavny/data/uploads`: не изменились; добавлений/удалений нет.
- Users 8, notes 130, files 118, links 16, tags 8, legacy outbox 187 — без изменений.
- 117 исторических FK-нарушений и старая cross-owner link не исправлялись.

## 10. REMAINING RISKS

- Исторические FK/cross-owner данные и legacy quarantine требуют отдельно
  согласованной работы; этот этап их не мигрирует и не исправляет.
- Conflict-записи связей сохраняются, но новый экран разрешения/закрытия конфликтов
  и их автоматическая очистка не добавлялись. Старые failed rows тоже остаются видимыми.
- Уже созданные старым recovery способом копии не переоформляются автоматически.
  Обычный POST создания заметки не заменяет специальный API независимой копии.
- Разделяемые оригиналы/preview-пути нужно учитывать при будущем garbage collection.
  Удаление физических файлов или GC здесь не вводилось.
- Старые CRUD-клиенты без If-Match сохраняют прежнюю совместимость; защита от
  устаревшего редактора проверена для текущего editor и переданного If-Match/baseRevisions.
- PostgreSQL, Cloudflare, реальная упаковка Tauri и deprecated warnings вне этого этапа.
  GO ниже относится к началу этапа 5, а не к доказанной готовности всех этих окружений.

## 11. READY FOR STAGE 5?

**GO — safe to begin Stage 5**

Все четыре подтверждённых блокера закрыты постоянными проверками. Работа
останавливается после 4.1; этап 5 не запускался.
