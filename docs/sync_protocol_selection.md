# Этап 3: выбор протокола sync

Baseline 0–2 перед изменениями: 94 Python, 7 JS, 9 browser smoke — passed;
проверка recovery point `20260923-190359-535280` — passed. Рабочая БД не изменялась.
Источники: текущий develop `5250d17` + локальная стабилизация;
локальная maksigma `c97552256808dbeed0eafebcced50c8c46d45bfd` (без checkout/merge).

## Текущий sync

`services/sync_engine.py`: sync_outbox(id/op_type/user/note/payload/status/tries) получает
create/update/delete из notes.py, commit из commit.py, upload из upload.py. Один trigger
открывает БД, делает все HTTP push/pull, затем коммитит. Создание через обычный POST notes,
обновление через PATCH без If-Match, при 404 может создать заметку заново. Upload отправляет
desktop op/file headers, но mapping файла не сохраняет. SyncNoteMap глобален по local_id.
Pull перечитывает список заметок с offset, сравнивает updatedAt; удаление не доставляется.
Старый конфликтный путь помечает очередь done, не сохраняя доказательства remote ack.
Очередь переполнения молча пропускает операцию. UI опрашивает trigger/status каждые 15 сек
в Tauri. Stage2 ограничил владельца, но не заменил этот протокол.

## Maksigma

`services/sync_protocol.py`, `api/sync.py`, `services/sync_engine.py`,
`alembic/versions/20260302_sync_hardening.py`: applied_ops, change_log, revision/tombstone,
push batches, timestamp pull, retries, зависимости и bootstrap списка. Пять тестов sync.
Повтор операции не возвращает полный прежний result/mapping; op_id глобален, курсор только
created_at (потеря событий на границе одинакового времени). Maps не разделены по remote/user.
Файлы требуют совпадения локального/удалённого ID. В некоторых путях допускается NULL owner,
AUTH_MODE=none и глобальные настройки групп. Есть destructive reset-local-cache — не переносится.
HTTP остаётся внутри локальной транзакции. Полный merge нарушил бы гарантии этапов 0–2.

## Сравнение до реализации

| Guarantee | Current | Maksigma | Target v1 |
|---|---|---|---|
| op_id | UUID только в очереди/header | UUID, журнал | UUID + payload hash + scope |
| idempotent create | не гарантирован | без полного replay result | атомарный result replay |
| idempotent update | нет | частично | неизменный op_id/result |
| durable ack | только клиентский status | applied marker | mutation + result одной транзакцией |
| revision/version | dormant revision, editor timestamp | integer revision | существующий Note.revision |
| If-Match integration | updatedAt | отдельная проверка sync | revision ETag + совместимый updatedAt |
| server change log | историческая неиспользуемая таблица | UUID/time log | та же таблица + sequence/snapshot |
| pull cursor | full list offset | timestamp | строго sequence |
| tombstones | delete не pull-ится | есть | note tombstone, stale update conflict |
| conflict detection | часы | частично revision | обязательная base_revision |
| conflict preservation | copy + drop pending | copy | отдельная копия + durable result |
| file mapping | отсутствует | ожидает одинаковый ID | явный scoped entity map |
| file retry | upload header best effort | ID assumption | SHA256 + atomic op result |
| links | push commit, pull неполон | outgoing snapshot | note aggregate + ownership |
| tags | snapshot/commit | snapshot | note aggregate + revision |
| user scope | Stage2 guards | местами ослаблен | точный authenticated user |
| client scope | нет | недостаточен | постоянный installation UUID |
| remote scope | URL/global map | global map | normalized URL + server UUID pin |
| retry/backoff | грубые повторы | op backoff | durable next_retry + jitter |
| restart safety | дубли/глобальное состояние | частично | durable wire payload/lease/cursor |
| partial failure | один большой transaction | nested operations | отдельный commit на operation |
| legacy outbox handling | pending отправляется | pending отправляется | protocol 0 всегда quarantined |

## Решение

Один v1 протокол: журнал операций + журнал последовательных изменений. Концепции revisions,
tombstones и applied-op из maksigma полезны; реализация пишется под нынешний ownership/block
контракт, без cherry-pick. Прямая переносимость старого кода не доказана; старые тесты
недостаточны для обязательной матрицы 30 сценариев.

Note — aggregate (текст/метаданные/tags/outgoing links). Любое изменение поднимает одну revision;
snapshot с пустым tags/links выражает удаление связей/тегов. File upload — отдельная операция
и mapping, note snapshots ждут file/note dependencies. Файлы не получают пользовательские пути
из wire payload. Существующий If-Match updatedAt остаётся совместимым; новый editor использует
`r<revision>`. Change sequence отвечает только за порядок pull, не за разрешение конфликтов.

Существующие sync_outbox/applied_ops/change_log/conflicts расширяются аддитивно. Исторические
sync_state (PK=user) и sync_note_map (PK=local note) не подходят под новый составной scope:
они сохраняются, новые sync_peer_state и sync_entity_map имеют user/client/remote keys.
Installation/server ID и счётчик sequence находятся в небольшой sync_identity.

Legacy rows получают protocol_version=0 по default, без переписывания старых payload/status.
Их эффективное состояние — quarantined_legacy. Ни одна из 187 операций не допускается в v1
автоматически. Преобразование старых операций требует отдельного проверенного плана после
доказательства владельца/remote/base_revision; в этом проходе миграции данных не будет.

Переполнение очереди отклоняет всю новую записывающую транзакцию кодом 503: уже сохранённые
данные/операции остаются; редактор сохраняет новую правку локально и показывает ошибку.
Невозможно подтвердить запись как синхронизируемую, не сохранив соответствующую операцию.

Все проверки реализации проводятся на временных SQLite/вложениях и тестовом HTTP transport.
Рабочая база, 117 исторических FK-нарушений и настоящие удалённые сервера не изменяются.
