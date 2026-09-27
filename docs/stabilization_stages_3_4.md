# Результат стабилизации OVC: этапы 3–4

Дата: 2026-09-25. База кода: develop `5250d17` + незакоммиченная стабилизация 0–2.
Работа локальная: коммитов, push, merge/cherry-pick maksigma, запуска production sync
и применения миграций к рабочей БД не было. Этап 5 не начат.

## 1. Baseline verification

До sync-изменений прошли 94 Python-теста, 7 JS-тестов и 9 Chromium editor smoke сценариев.
Recovery point `data/backups/20260923-190359-535280` восстановлен/проверен.
В конце те же гарантии подтверждены полным новым suite и теми же browser/JS сценариями.

Сохранены block contract, dirty/save/retry/recovery, If-Match/conflict copy, ownership,
запрет email auto-link, refresh/logout/lockout, cookies/CSRF и backup/restore.
Сравнение всех строк всех **19** таблиц рабочей БД с recovery point: полное совпадение.
Проверены backup hashes, quick_check, 214 сохранённых file paths; FK warnings остались 117.

## 2. Stage 3 — current sync

До изменения: outbox + обычные CRUD requests, timestamp/full-list pull, глобальные
note mappings. HTTP внутри транзакции, нет надёжного replay receipt, файлового mapping,
доставки удалений; при переполнении enqueue мог пропустить операцию. Stage2 уже ограничил
владельца, но этот транспорт ещё не обеспечивал offline/retry гарантии.
Полный аудит: [sync_protocol_selection.md](sync_protocol_selection.md).

## 3. Stage 3 — maksigma

Просмотрена локальная ветка `maksigma`, commit `c97552256808dbeed0eafebcced50c8c46d45bfd`.
Полезны идеи журнала, applied operations, revisions/tombstones. Не перенесены timestamp
cursor, глобальные mappings/state, предположение равных FileAsset IDs, owner fallbacks,
destructive reset и HTTP внутри транзакции. Прямого переноса файлов не было.
Матрица Current/Maksigma/Target составлена до реализации в документе выбора протокола.

## 4. Selected protocol

Canonical v1: UUID операции + request fingerprint + атомарный durable result,
существующая Note.revision для web/AI/sync, отдельный монотонный sequence для pull,
замороженный wire payload, persistent client/server UUID, scoped mappings/cursor,
dependencies, leases, backoff, explicit errors. Полный [контракт v1](sync_protocol_v1.md).

## 5. Legacy outbox audit

187 pending legacy: create_note **52**, update_note **98**, upload_file **36**, commit **1**.
Валидных владельцев **184**, отсутствующих user records **2**, NULL owner **1**.
Payload с проверяемыми блоками: **150 valid**, без блоков **37**. Это не совместимость
протокола: у всех 187 отсутствуют доказанные client/remote scope, у 99 нет base revision;
также есть ссылки на отсутствующие сущности.

Совместимых для автоматической отправки **0**, quarantined **187**, migrated **0**.
`protocol_version=0/NULL/missing` никогда не отправляется v1. Старые status/payload/tries
не переписываются. Инструмент проверил **каждую** строку; JSON не содержит контент/секреты.
[Инструмент и стратегия карантина](sync_legacy_quarantine.md).

## 6. Schema changes

Аддитивные изменения outbox/applied_ops/change_log/conflicts; новые scoped
`sync_entity_map`, `sync_peer_state`, маленькая `sync_identity` (UUID/sequence/version/
active sync account). Старые несовместимые scope keys в sync_state/sync_note_map сохранены
и не используются worker. Старый NULL-owner backfill outbox удалён.
Повторный upgrade не меняет исторические данные, неизвестная будущая schema_version
блокирует downgrade. Глобальные FK не включались.

## 7. Server changes

Authenticated hello, per-operation batch push, multipart file upload, owner-scoped
исторический original download, sequence pull. Изменение, event и receipt коммитятся
вместе. Replay возвращает прежний ID/revision/snapshot. Невалидный batch element не
откатывает соседей. Notes/commit/upload пишут journal; metadata/links/tags поднимают
ревизию, remove_link доступен через commit. Удаления — tombstones, исключённые из обычных
списков, graph, search, AI и file-access через централизованный ownership contract.

## 8. Client changes

Enqueue атомарен с пользовательской записью. Claim/lease и ack — короткие транзакции,
между ними HTTP без открытой локальной сессии. Dependencies сначала создают identities,
потом отправляют files/full snapshots, в том числе циклические связи. Загрузка файла
к существующей unmapped заметке также сохраняет её полный snapshot, не оставляет пустую
identity shell вместо её содержимого.

`wire_json` переживает restart без смены UUID/базы/payload. Retry deadlines переживают
restart, auth errors останавливают worker. Переключение активного sync-аккаунта через
ручной trigger приостанавливает прежний background user без удаления его очереди.
Outbox overflow возвращает 503 с rollback новой записи и сохранением editor draft.

## 9. Conflict model

Remote original остаётся, входящий snapshot становится conflict copy + metadata.
Клиент сохраняет и более поздние локальные правки поверх отправленной версии. Payload
конфликтных/ошибочных операций не удаляется, конфликт не выдаётся за applied.
Вложения копии получают отдельные metadata IDs; удаление оригинала не закрывает файлы копии.
Неизвестный результат отправки сначала replay-ится; cursor не перескакивает через новое
событие, способное скрыться после позднего ack.

## 10. File sync model

SHA256/size/name/MIME проверяются; upload receipt возвращает прежний remote ID при повторе.
Local/remote FileAsset IDs явно различаются в tests. Block URLs переписываются через
scope mapping. Pull сначала скачивает/проверяет bytes, затем применяет страницу и cursor.
Восстановление missing/corrupt mapped original сохраняет опубликованные local URLs.
Существующие конвертеры/viewer endpoints используются без изменения форматов.

## 11. User / client / remote isolation

Все новые queues/maps/cursors отделены по user/client/normalized remote URL hash;
peer дополнительно закрепляет server UUID и remote account. Wire remote_key — server UUID.
Principal проверяется на обеих сторонах; dev fallback не является sync credential.
Смена аккаунта/remote не переиспользует чужую очередь или cursor. Замена server UUID
на прежнем URL блокируется. NULL-owner legacy никогда не claim-ится.

## 12. Test results

- Полный Python suite: **202 passed, 0 failed, 0 skipped**.
- В составе suite: sync client/integration **34**, sync server/migration **69**, legacy audit **8**;
  остальные **91** — существующий suite. Три старых transport tests заменены v1 integration
  tests; ownership test обновлён под canonical service без ослабления проверки.
- JS note-save: **7 passed, 0 failed, 0 skipped**.
- Chromium editor smoke: **9 passed, 0 failed, 0 skipped**.
- Backup restore verification: passed; 19 рабочих таблиц совпадают с recovery point.
- AST: **38** изменённых Python-файлов; syntax check изменённого JS; `git diff --check`: passed.
- 204 предупреждения Python suite — существующие deprecated Pydantic/FastAPI/SWIG API,
  не ошибки тестов. Их отдельная миграция не входила в этапы 3–4.

Проверки только на временных SQLite/storage, реальном ASGI API через MockTransport
и локальном Chromium. Рабочая БД читалась readonly. PostgreSQL, Tauri packaging и
production network не запускались: это границы проверки, а не pytest skipped tests.

Команды воспроизведения:

```sh
.venv/bin/python -m pytest -q
node --test tests/note_save.test.mjs
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tests/manual_editor_smoke.py
.venv/bin/python -B scripts/audit_legacy_sync.py --summary-only
./scripts/verify_backup_restore.sh data/backups/20260923-190359-535280
git diff --check
```

## 13. Failure scenarios / mandatory matrix

1. Create push — `test_standard_create_update_pull_and_durable_cursor`.
2. Update push — тот же тест, frozen sequential full snapshots.
3. Pull — remote web update + local apply в том же тесте.
4. Identical op retry — `test_create_and_retry_replay_exact_durable_receipt`.
5. Lost response after commit — `test_lost_create_response_frozen_op_survives_restart`.
6. Pull interruption — `test_pull_interrupted_apply_rolls_back_cursor_and_note`.
7. Restart with pending — lost-response test с dispose connections, прежний durable wire.
8. Restart with cursor — standard cycle + dispose + no repeated changes.
9. Remote unavailable — `test_remote_unavailable_does_not_consume_pending_queue`.
10. 401/expiry — `test_operation_error_classification_and_reauthentication[401]`.
11. Concurrent conflict — parallel server edits + `test_concurrent_offline_edit_preserves_both_and_sync_continues`.
12. Web If-Match vs sync — `test_web_editor_ai_and_sync_share_one_revision_and_tombstone_contract`.
13. Offline delete — `test_offline_delete_and_stale_update_cannot_resurrect`.
14. Delete vs pending update — тот же тест, server tombstone + retained copy.
15. Link create/delete — `test_tags_links_create_remove_and_dependency_mapping`.
16. Tag assignment/unassignment — тот же тест + replace aggregate server test.
17. Offline upload — `test_file_upload_retry_mapping_and_viewer_urls`.
18. Duplicate upload — тот же тест + `test_upload_retry_returns_same_mapping_and_durable_checksum`.
19. File mapping persistence — dispose + scoped map сохраняется; separate local/remote IDs.
20. User A vs B — authenticated server ownership tests + `test_user_switch_legacy_quarantine_and_wrong_token`.
21. Account switch — отдельные state/cursor + `test_account_switch_pauses_previous_users_background_worker_even_after_restart`.
22. Remote A vs B — `test_two_independent_remote_servers_never_share_cursor_or_outbox`.
23. Worker isolation — `test_worker_reverifies_captured_owner_each_cycle` и account-switch pause.
24. NULL owner — `test_all_187_legacy_rows_remain_unchanged_with_null_owner`.
25. Legacy quarantine — тот же тест + восемь readonly audit tests + фактический readonly inventory.
26. Outbox full — `test_queue_overflow_rolls_back_edit_and_never_drops_prior_rows`.
27. Partial batch — `test_partial_batch_keeps_valid_operations_before_and_after_invalid_one`.
28. Dependencies — link/file tests + `test_dependency_failure_keeps_children_without_attempts`.
29. Restart mid-operation — `test_restart_mid_operation_lease_replays_committed_result`.
30. Editor browser suite — все девять прежних сценариев, включая unsaved metadata/upload,
    failed PATCH/retry, persistent recovery, AI/manual edit, conflict preservation и logout flush.

Дополнительно: concurrent duplicate creates, rollback receipt/journal, sequence ties/user gaps,
checksum mismatch, separate file IDs, future schema refusal, retained attachment after delete,
malformed ack replay, pull download outage, missing/corrupt mapped file recovery,
unknown ack followed by a newer web edit, upload to existing unmapped note.

## 14. Files changed in stages 3–4

Предыдущие незакоммиченные изменения этапов 0–2 оставлены. Этот этап затронул:

- `README.md`; `docs/sync_protocol_selection.md`; `docs/sync_legacy_quarantine.md`;
  `docs/sync_protocol_v1.md`; `docs/stabilization_stages_3_4.md`.
- `scripts/audit_legacy_sync.py`.
- `src/app/db/models.py`; `src/app/db/sync_schema.py`; `src/app/db/migrate.py`.
- `src/app/services/sync_protocol.py`; `src/app/services/sync_engine.py`.
- `src/app/api/sync.py`; `src/app/api/notes.py`; `src/app/api/note_models.py`;
  `src/app/api/commit.py`; `src/app/api/upload.py`; `src/app/api/graph.py`.
- `src/app/core/ownership.py`; `src/app/agent/context.py`; `src/app/main.py`.
- `src/static/js/editor.js`; `src/static/js/note_save.js`; `src/static/js/data_adapter.js`.
- `tests/test_sync_protocol.py`; `tests/test_sync_engine.py`; `tests/test_legacy_sync_audit.py`;
  `tests/test_stabilization.py`.

Рабочие `.env`, SQLite, вложения и пользовательский `tmp/` не изменялись.

## 15. Remaining risks

- Старые 117 FK violations, cross-owner legacy link, orphan/historical identities
  остаются предметом контролируемого следующего этапа. Карантин не является их ремонтом.
- Нет production PostgreSQL/multi-host load подтверждения; legacy migrations по-прежнему
  содержат SQLite-специфичные участки. Этот проход не является PostgreSQL rollout.
- Retention/compaction journals/receipts/tombstones и UI управляемого rebind/legacy migration
  не добавлены. Безопасно сохранять данные; удалять/сбрасывать автоматически нельзя.
- Blob filesystem и DB не атомарны вместе: rollback после нового file write может оставить
  неиспользуемые bytes. Видимого двойного FileAsset нет, автоматической очистки нет.
- Глобальный sequence lock сериализует запись; текущая full-snapshot модель и конвертеры
  сохраняют ограничения памяти/CPU. Оптимизация нагрузки требует отдельного измерения.
- Background token не обновляется автоматически. После auth/account pause manual sync
  доступен под текущим входом; для восстановления config worker требуется перезапуск.

## 16. Ready for stage 5?

**Да — для отдельного этапа “Database integrity repair + migration unification +
SQLite/PostgreSQL correctness”.** Блокеров в проверенной acceptance-матрице этапа 4
не осталось. Это не разрешение автоматического ремонта рабочей БД и не подтверждение
production PostgreSQL готовности. Этап 5 в этой работе не выполнялся.
