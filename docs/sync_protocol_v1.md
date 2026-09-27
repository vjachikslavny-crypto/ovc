# Sync v1: контракт и эксплуатация

Состояние реализации: этапы 3–4 и исправления [4.1](stabilization_stage_4_1.md), локальная ветка develop, без merge maksigma,
без изменения рабочей БД и без push. [Выбор протокола](sync_protocol_selection.md)
сделан после проверки этапов 0–2. [Карантин старых операций](sync_legacy_quarantine.md)
обязателен независимо от возраста, владельца и валидности старого payload.

## Режимы и аутентификация

`off`, `shared-db`, `remote-shell` не создают очередь независимой реплики и не
запускают её worker. Обмен двух БД выполняет только `remote-sync`; ручной trigger
и фоновый worker используют одну функцию. `remote-shell` продолжает использовать
удалённый UI/backend без локального обмена репликами.

Новые переменные окружения не требуются. Для клиента задаются `SYNC_MODE=remote-sync`,
`SYNC_REMOTE_BASE_URL`, `AUTH_MODE=local|supabase|both`. Обычный web-сервер может оставаться
в `SYNC_MODE=off`: при этом его аутентифицированные v1 endpoints и журнал работают.
Фоновому клиенту дополнительно нужен `SYNC_BEARER_TOKEN`; ручной trigger использует
текущий access token запроса. Токен проверяется локально каждый цикл, затем remote
подтверждает тот же auth context и subject. Supabase subject может соответствовать
разным внутренним user UUID в двух БД. Local JWT должен быть валиден на обеих сторонах
и идентифицировать один аккаунт. Временный dev-user и `AUTH_MODE=none` не допускаются.

Worker захватывает проверенные user/token при запуске, не подменяет владельца при
изменении глобальной настройки, на auth error останавливается. Успешная локальная
проверка ручного trigger закрепляет активный sync-аккаунт установки. Если другой
аккаунт запускает ручной цикл, прежний background worker приостанавливается до HTTP;
этот выбор сохраняется после перезапуска, старая очередь остаётся целой. После обновления
конфигурационного токена worker запускается заново с процессом; ручной trigger после
повторного входа доступен сразу. Токены не записываются в очередь, receipts или status.

## API

Обмен (`hello/push/pull/files/trigger`) требует настоящую аутентификацию. `status`
использует текущий user context, включая явно включённый локальный dev-режим.
Cookie POST сохраняют общий CSRF-контракт.

- `GET /api/sync/hello`: `protocol_version`, `server_id`, `user_id`, `auth_context`,
  `auth_subject`. Клиент проверяет версию 1, principal и закреплённый server UUID.
- `POST /api/sync/push`: `{ "operations": [...] }`, 1–100 операций. Каждая операция
  проверяется и коммитится отдельно. Ответ `{ "results": [...] }` сохраняет порядок
  и включает `op_id`, `status`, `entity_remote_id`, `revision`, `snapshot`, при конфликте
  `conflict`. У применённой операции с удалённой целью связи есть `relation_conflicts`.
  Невалидный элемент не откатывает уже подтверждённые элементы batch.
- `POST /api/sync/files`: multipart `operation` (JSON v1) + `file`. Проверяются sha256,
  size, filename, MIME и владелец родителя. Повтор возвращает тот же remote asset ID.
- `GET /api/sync/files/{id}/original`: оригинал строго своего файла, в том числе для
  воспроизведения исторического события перед tombstone родителя. Обычные viewer URL
  удалённой заметки остаются закрытыми; конфликтная копия получает свои FileAsset IDs.
- `GET /api/sync/pull?cursor=0&limit=100`: limit 1–500, строгий sequence `> cursor`,
  `changes`, `next_cursor`, `has_more`, `server_id`, `protocol_version`.
- `GET /api/sync/status`: состояние текущего пользователя и настроенного remote.
- `POST /api/sync/trigger`: один цикл с явным user/access token, без токенов в ответе.

Для цикла с проверяемым scope `failed` — количество durable `failed_permanent`
в этом scope, **включая предыдущие циклы и preflight**, как в status. `retry` и
`pending` также берутся из очереди; `lastError` берётся из peer state либо первой
permanent failure. Сетевые/auth ошибки дают `ok=false` и `reason`; они не увеличивают
счётчик permanent failures. При очереди в retry результат также `ok=false`, даже
если backoff пока запрещает отправку. `ok=true` означает цикл без этих ошибок,
но не отсутствие pending/conflict: проверяйте отдельные счётчики. `relationConflicts`
считает сохранённые конфликты связей текущего user/client/remote. Worker и manual
trigger используют этот общий результат; UI показывает ошибки до статуса «подключен».
`lastSuccessAt` отражает успешную связь/применение pull, а не отсутствие ошибок операций.

Canonical operation: UUID `op_id`, `protocol_version=1`, `user_id` удалённого аккаунта,
постоянный UUID `client_id`, `remote_key` (server UUID на wire), `entity_type=note|file`,
`entity_local_id`, `entity_remote_id|null`, `operation_type=create|update|delete|upload`,
`payload`, `base_revision|null`. Неизвестные версии и лишние поля отклоняются.
Время создания, attempts (`tries`), retry deadline, status и зависимости хранятся
в outbox, а не доверяются входящему HTTP-клиенту.

## Локальная ревизия, удалённая ревизия и sequence

Существующая `Note.revision` — версия состояния заметки **в данной БД**. Создание, изменение контента, AI commit,
метаданные, tags/links и удаление увеличивают её в одной транзакции с journal event.
Редактор посылает `If-Match: "r<N>"`; обычные PATCH/DELETE продолжают принимать старый
`If-Match: "<updatedAt>"`. Отсутствие If-Match в старых CRUD-клиентах сохраняет совместимость;
в sync update/delete `base_revision` обязателен. В `POST /api/commit` можно передать
`baseRevisions: {noteId: N или "rN"}`; один `If-Match` допустим только для одного aggregate.
`remove_link` дополняет существующие actions: fromId/toId, опциональный reason.

Ревизия относится к содержимому сущности. Sequence относится к порядку доставки.
Он не является версией заметки. Изменения сериализуются через служебную строку
sequence; запись snapshot, счётчика и receipt фиксируется одним commit. Это простой
вариант для текущего масштаба, а не параллельный distributed sequencer.

Клиент хранит известную удалённую ревизию только в существующем
`SyncEntityMap.remote_revision` и durable receipts. Из неё формируется `base_revision`
на wire; она не присваивается локальному `Note.revision`. Ack обновляет mapping/receipt,
не меняя локальное содержимое и ETag. Pull изменённого aggregate увеличивает локальную
ревизию и локальный `updatedAt` монотонно в одной транзакции с cursor. Собственный
подтверждённый snapshot с тем же содержимым не инвалидирует открытый редактор.
Третьего счётчика версий нет; sequence остаётся только позицией в журнале сервера.

## Durability, зависимости, конфликты

Первое создание identity заметки отправляет минимальный snapshot, затем полный
aggregate. Это позволяет создать обе стороны циклических links и родителя файла
до отправки зависимостей. Полный snapshot включает blocks, layoutHints, passport,
теги и исходящие links. Пустые tags/links означают снятие назначений. Исторические
cross-owner links фильтруются, не исправляются и не переносятся.

Очередь новой правки сохраняется вместе с самой правкой. `base_revision` берётся из
известного scoped mapping при enqueue; если есть предыдущая локальная операция той
же сущности, новая зависит от её durable acknowledgement. При подготовке запроса
база берётся из **конкретного результата предшественника**, не из свежей версии сервера.
Затем `wire_json` замораживается до HTTP. Повтор никогда не меняет op_id/payload/base.
Зависимости ждут подтверждения; failed prerequisite не расходует attempts дочерних операций.

Claim транзакционно сохраняет inflight и lease; HTTP идёт после закрытия сессии.
Отдельная транзакция сохраняет result/mapping. Истёкший lease позволяет повторить
тот же запрос после crash. Применение и receipt на сервере атомарны, повтор сверяется
также с user/client/payload hash. Подмена UUID под другой payload/owner отклоняется.

Клиент отправляет отдельные элементы через batch endpoint: успешный ack сохраняется
сразу; сервер также поддерживает multi-operation batches. Retryable — сеть, timeout,
408/425/429/5xx; backoff около 1/2/4…300 секунд + jitter. 401 приостанавливает очередь,
валидация/ownership дают permanent failure. Все payload сохраняются. Диагностика
не сохраняет тело ответа/текст transport exception с возможными секретами.

При конфликте исходная серверная версия остаётся; входящая получает конфликтную копию
и durable metadata. Клиент дополнительно сохраняет самую новую локальную версию,
если поверх отправленного snapshot были другие правки. Pending операции получают
`conflict`, а не ложный `applied`; их payload остаётся доступным. Копии клонируют metadata
вложений в свои IDs, чтобы удалённый родитель не сделал копию нечитаемой.
Исходная tombstone не отменяется. Разрешение конфликта — явная дальнейшая правка/копия,
автоматического last-write-wins нет.

Редактор восстанавливает черновик через `POST /api/notes/{id}/recovery-copy` и тот же
`preserve_copy`, который используют обе стороны sync. Вход — `NoteCreateRequest`,
выход — `201 NoteDetail` с ETag. Исходная заметка может быть tombstone, но должна
принадлежать текущему пользователю. Все найденные `/files/{id}/...` в блоках получают
новые FileAsset IDs с родителем-копией; байты и производные preview-пути можно разделять.
Чужой/отсутствующий файл или чужой родитель откатывает всю копию. Общий viewer ownership
guard остаётся строгим. В remote-sync новая editor-копия ставится в обычную очередь с
зависимостями uploads. Обычный `POST /notes` не является API независимой recovery-копии.

Полный sync snapshot со связью на существующую tombstone **того же владельца**
применяет тело и живые связи; удалённая связь не активируется. Её исходные
`toId/reason/confidence` сохраняются отдельно в `sync_conflicts` с kind
`relation_target_deleted`, user/client/remote/op scope и source note IDs. Receipt
содержит те же `relation_conflicts`; клиент сохраняет их при ack и показывает
счётчик в desktop status. Повтор op_id не создаёт ещё один конфликт. Операция остаётся
`applied`, поэтому не блокирует следующие изменения. Копии также сохраняют отклонённые
связи как отдельные записи. Отсутствующая или чужая цель по-прежнему отклоняется;
обычный CRUD/AI не разрешает создавать новую связь на tombstone. Автоматического
восстановления цели, удаления конфликтов или нового UI их разрешения в 4.1 нет.

При неизвестном результате ранее отправленной операции pull не перескакивает через
новый remote event: сначала нужен replay/ack. Иначе потерянное подтверждение могло бы
навсегда скрыть следующую серверную правку.

## Pull, файлы, scope

Pull читает сохранённые snapshot, а не текущее состояние по времени createdAt.
Первый cursor=0 добавляет отсутствующие v1 baseline events для своих существующих
заметок/файлов, без replay старого outbox и без изменения Note.revision. События разных
пользователей могут давать пропуски sequence; это нормально.

Файлы скачиваются и проверяются по SHA256 **до** транзакции применения. Временные
placeholder notes скрыты tombstone до получения полного snapshot, если link/parent
пришёл раньше своей заметки. Применение страницы и cursor атомарны. Повтор не создаёт
новых mapped сущностей. Pull не добавляет обратные outbox операции. Каноническая
валидация блоков и обновление поискового индекса используются как в обычном редакторе.

File mapping не предполагает равенства UUID. Block URL `/files/...` переписывается
через mapping; preview/viewer API и конвертеры остаются прежними. На сервере тот же
upload op возвращает прежний asset. На клиенте недостающий/повреждённый mapped original
восстанавливается проверенными байтами при повторном событии, сохраняя локальные URL.

Scope нового outbox/map/cursor — `(local user, installation client UUID, normalized
remote URL hash)`. В peer state закреплены server UUID и remote user. На wire remote_key
равен этому server UUID. Смена URL выбирает отдельную очередь/cursor/maps; возвращение
к URL продолжает прежний scope. Новый server/account на старом URL блокируется, а не
молча присваивает чужие mappings. Автоматического rebind/reset-local-cache нет.

## Аддитивная схема и legacy

- `sync_outbox`: protocol_version (default 0), client_id, remote_key, entity_type/id,
  entity_remote_id, base_revision, dependency_json, wire_json, result_json, next_retry_at.
  Старые id/op_type/payload/tries/status сохранены. `id` — op_id, `tries` — attempts.
- `sync_applied_ops`: protocol_version, client_id, request_hash, полный result_json.
- `sync_change_log`: protocol_version, уникальный integer sequence; прежние UUID,
  owner/entity/operation/revision/deleted/payload/time используются как совместимая основа.
- `sync_conflicts`: user/client/remote/op scope добавлен к прежним полям.
- `sync_identity`: client_id/server_id/sequence/schema_version=1, active_sync_user.
- `sync_peer_state`: scoped cursor/pinned server/account/reachability/auth/error/time.
- `sync_entity_map`: scoped note/file IDs, remote revision, sha256, status.

Старые `sync_state` (PK user) и `sync_note_map` (глобальный PK note) не подходят под scope:
они оставлены без изменений и не читаются новым worker. `sync_schema.upgrade` повторяем,
не удаляет таблицы/строки, не включает глобальные FK. Неизвестная будущая schema_version
останавливает upgrade, предотвращая downgrade. NULL-owner backfill старой очереди убран.

Любой protocol 0/NULL/missing считается legacy и никогда не claim-ится v1. В рабочей
БД 187 таких pending: 52 create, 98 update, 36 upload, 1 commit. Владельцы: 184 valid,
2 missing, 1 NULL. Совместимых для автоматической отправки **0**, мигрировано **0**.
Аудит показывает каждую строку и причины; подходящий shape не доказывает base/remote/owner.

## Диагностика и ограничения

Status показывает protocolVersion, userId/clientId, remoteKey/serverId, cursor,
lastSuccessAt, pending/retry/done/conflicts/failed, quarantinedLegacy, remoteReachable,
authRequired, lastError, mode/worker/desktop. Legacy count в пользовательском API относится
только к этому user; полный административный отчёт включает NULL/missing owners.
Desktop indicator сообщает auth error, permanent error, очередь, конфликтные копии,
legacy quarantine. Пустая новая очередь не выдаёт legacy за синхронизированную.

Лимит относится ко всем не-applied v1 операциям, включая неразрешённые конфликты/ошибки.
Переполнение даёт 503 и откатывает новую транзакцию: прежние заметки/операции сохранены,
редактор оставляет новую правку в recovery storage. Файл/другое API-действие нужно повторить
после устранения очереди; ложного успешного сохранения без outbox нет.

Журналы, receipts и tombstones пока не compact-ятся: автоматическая очистка могла бы
сломать replay/cursor. DB и filesystem не составляют единую транзакцию: сбой после записи
нового blob до DB commit может оставить неиспользуемый файл на диске; видимого двойного
FileAsset/receipt не возникает. Автоматическая уборка не добавлена. Page file downloads
и конвертация сохраняют текущие memory/CPU ограничения viewers. Автоматическая выгрузка
всей старой локальной базы не выполняется: только новые действия, их зависимости и pull.

Проверены временные SQLite + HTTP transport + Chromium. PostgreSQL, multi-host нагрузка,
упаковка Tauri и production rollout — вне этого этапа. 117 старых FK нарушений не исправлялись.
Следующий отдельный этап — integrity repair и унификация SQLite/PostgreSQL migrations.
