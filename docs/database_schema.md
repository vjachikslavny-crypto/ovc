# Каноническая схема OVC — Stage 5

Alembic head: `20260926_integrity`. Полный замороженный контракт: [schema_v5.json](../alembic/schema_v5.json).

24 прикладные/совместимые таблицы и служебная `alembic_version`. Для существующих баз сохраняются дополнительные исторические столбцы, UNIQUE/CHECK/FK и SQL индексов, включая partial/expression indexes. Неизвестные триггеры требуют ручного разбора: миграция останавливается и откатывается.

На SQLite foreign_keys=ON для каждой прикладной SQLAlchemy connection. Только эксклюзивная maintenance-транзакция миграции временно выключает FK для пересборки таблиц и проверяет их перед commit. PostgreSQL использует обычные FK, transactional DDL и advisory transaction lock. Базовые UNIQUE допускают несколько NULL в обеих СУБД; новые правила сравнения регистра не вводились.

Все обычные DateTime остаются UTC без TZ в хранилище согласно существующему контракту. Timestamp и owner исторической записи не придумываются: если обязательное значение отсутствует, финальная миграция требует явного исправления. Text JSON блоков/sync остаётся Text; только audit metadata использует SQLite JSON / PostgreSQL JSONB. Ревизия заметки, remote_revision и sequence имеют разные назначения и не объединяются.

## action_log

Исторический журнал применённых действий с уникальным hash; payload не преобразуется и не удаляется.

- PK: `id`.
- FK: нет.
- UNIQUE: `uq_action_log_hash(hash)`.
- Индексы: PK/UNIQUE.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `hash` String, `payload` Text, `created_at` DateTime.

## group_preferences

Исторические общие настройки сохранены; пользовательские API работают с user_group_preferences, перенос/смена владельца здесь не выполняется.

- PK: `key`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: PK/UNIQUE.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `key` String, `label` String, `color` String, `created_at` DateTime, `updated_at` DateTime.

## integrity_archive

Приватные исходные строки, категория, причина и ID ремонта. Намеренно нет FK на исчезнувшего владельца/сущность. original_json содержит исходные приватные данные и хеши сессий; API его не публикует, логи ремонта не печатают содержимое.

- PK: `id`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_integrity_archive_repair_id(repair_id)`.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `repair_id` String, `source_table` String, `source_id` String, `category` String, `reason` String, `original_json` Text, `created_at` DateTime.

## messages

Исторические user_id/note_id являются метаданными журнала, без новых FK и каскадного удаления текста.

- PK: `id`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_messages_note_id(note_id)`; `ix_messages_user_id(user_id)`.
- Ownership: user_id nullable.
- Столбцы: `id` String, `role` String, `text` Text, `user_id` String?, `note_id` String?, `mode` String?, `created_at` DateTime.

## sources

Общий каталог источников с уникальным URL; нет придуманного user ownership. Связь с заметкой хранится отдельно.

- PK: `id`.
- FK: нет.
- UNIQUE: `uq_sources_url(url)`.
- Индексы: PK/UNIQUE.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `url` Text, `domain` String, `title` Text, `summary` Text, `published_at` String?.

## sync_applied_ops

Durable receipts нельзя удалять каскадом вместе с объектом: повтор op_id после удаления не должен повторить действие. Исторические owner/entity identifiers намеренно не FK. op_id PK обеспечивает idempotency lookup.

- PK: `op_id`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: PK/UNIQUE.
- Ownership: user_id NOT NULL.
- Столбцы: `op_id` String, `user_id` String, `entity_type` String, `entity_id` String?, `created_at` DateTime, `protocol_version` Integer, `client_id` String?, `request_hash` String?, `result_json` Text?.

## sync_change_log

События и tombstones должны переживать hard delete, поэтому entity_id/user_id здесь логические исторические ссылки, не FK. sequence nullable у протокола 0 и unique при заполнении. Индекс user/protocol/sequence обслуживает pull. Счётчик в sync_identity увеличивается portable BIGINT→TEXT SQL.

- PK: `id`.
- FK: нет.
- UNIQUE: `uq_sync_change_log_sequence(sequence)`.
- Индексы: `ix_changes_owner_sequence(user_id,protocol_version,sequence)`; `ix_sync_change_log_user_id(user_id)`.
- Ownership: user_id NOT NULL.
- Столбцы: `id` String, `user_id` String, `entity_type` String, `entity_id` String, `op_type` String, `server_version` Integer, `deleted` Boolean, `payload_json` Text, `created_at` DateTime, `protocol_version` Integer, `sequence` Integer?.

## sync_entity_map

Локальная и удалённая идентичности, remote_revision и удалённые tombstones сохраняются независимо от физического объекта. Поэтому identifiers не FK. UNIQUE scope/local и scope/remote защищают соответствие внутри user/client/remote/entity_type.

- PK: `user_id`, `client_id`, `remote_key`, `entity_type`, `local_id`.
- FK: нет.
- UNIQUE: `uq_sync_entity_remote(user_id,client_id,remote_key,entity_type,remote_id)`.
- Индексы: PK/UNIQUE.
- Ownership: user_id NOT NULL.
- Столбцы: `user_id` String, `client_id` String, `remote_key` String, `entity_type` String, `local_id` String, `remote_id` String, `remote_revision` Integer, `sha256` String?, `status` String.

## sync_identity

Стабильные client/server IDs и счётчик данной БД, schema_version=1. Создание этих четырёх служебных ключей не активирует старую очередь.

- PK: `key`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: PK/UNIQUE.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `key` String, `value` String.

## sync_peer_state

Курсор/идентичность сервера в изолированном scope; не каскадируется вместе с заметками. PK соответствует user/client/remote.

- PK: `user_id`, `client_id`, `remote_key`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: PK/UNIQUE.
- Ownership: user_id NOT NULL.
- Столбцы: `user_id` String, `client_id` String, `remote_key` String, `server_id` String?, `remote_user_id` String?, `cursor` Integer, `last_success_at` DateTime?, `last_error` String?, `reachable` Boolean?, `auth_required` Boolean.

## users

username/email/supabase_id уникальны по текущему контракту, nullable email/supabase_id сохраняются. ORM passive_deletes согласован с CASCADE notes/files; refresh ORM cascade совпадает с DB CASCADE.

- PK: `id`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_users_supabase_id(supabase_id)` UNIQUE; `ix_users_username(username)` UNIQUE; `ix_users_email(email)` UNIQUE.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `username` String, `email` String?, `password_hash` String, `supabase_id` String?, `display_name` String?, `avatar_url` String?, `failed_login_count` Integer, `locked_until` DateTime?, `created_at` DateTime, `updated_at` DateTime, `is_active` Boolean, `role` String, `email_verified_at` DateTime?.

## audit_logs

История переживает удаление пользователя через SET NULL. До очистки сломанного user_id исходная строка сохраняется в integrity_archive. Email verification больше не меняет схему во время запроса.

- PK: `id`.
- FK: `user_id → users(id)`, ON DELETE SET NULL.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_audit_logs_user_id(user_id)`; `ix_audit_logs_created_at(created_at)`; `ix_audit_logs_event(event)`.
- Ownership: user_id nullable.
- Столбцы: `id` String, `user_id` String?, `event` String, `ip` String?, `user_agent` String?, `metadata` JSON?, `created_at` DateTime.

## notes

Владелец nullable для исторической совместимости. Бесхозные записи не назначаются автоматически; API скрывает их. Основной запрос списка — owner + updated_at, поэтому добавлен составной индекс.

- PK: `id`.
- FK: `user_id → users(id)`, ON DELETE CASCADE.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_notes_owner_updated(user_id,updated_at)`; `ix_notes_user_id(user_id)`.
- Ownership: user_id nullable.
- Столбцы: `id` String, `user_id` String?, `title` String, `style_theme` String, `layout_hints` Text, `blocks_json` Text, `passport_json` Text, `created_at` DateTime, `updated_at` DateTime, `revision` Integer, `tombstone` Boolean, `client_origin` String?, `last_client_ts` DateTime?.

## refresh_tokens

Отсутствующий owner делает сессию недействительной; такая строка архивируется и удаляется. Hard delete пользователя каскадный, ORM поведение совпадает. auth_provider — прежний стабилизированный контракт.

- PK: `id`.
- FK: `user_id → users(id)`, ON DELETE CASCADE.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_refresh_tokens_expires_at(expires_at)`; `ix_refresh_tokens_user_id(user_id)`; `ix_refresh_tokens_token_hash(token_hash)`.
- Ownership: user_id NOT NULL.
- Столбцы: `id` String, `user_id` String, `auth_provider` String, `token_hash` String, `created_at` DateTime, `expires_at` DateTime, `rotated_at` DateTime?, `revoked_at` DateTime?, `fingerprint_hash` String?, `ip` String?, `user_agent` String?.

## user_group_preferences

Пользовательские настройки графа изолированы составным PK(user_id,key); пользовательский FK CASCADE.

- PK: `user_id`, `key`.
- FK: `user_id → users(id)`, ON DELETE CASCADE.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: PK/UNIQUE.
- Ownership: user_id NOT NULL.
- Столбцы: `user_id` String, `key` String, `label` String, `color` String, `created_at` DateTime, `updated_at` DateTime.

## files

Standalone file допустим (note_id=NULL). Hard delete заметки делает SET NULL, metadata и bytes сохраняются; удаление пользователя удаляет его metadata по CASCADE, без garbage collection байтов. Совместимые revision/tombstone/updated_at сохранены, новый файловый протокол не вводился.

- PK: `id`.
- FK: `note_id → notes(id)`, ON DELETE SET NULL; `user_id → users(id)`, ON DELETE CASCADE.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_files_upload_op_id(upload_op_id)`; `ix_files_user_id(user_id)`; `ix_files_note_id(note_id)`.
- Ownership: user_id nullable.
- Столбцы: `id` String, `note_id` String?, `user_id` String?, `kind` String, `mime` String, `filename` String, `size` Integer, `path_original` String, `path_preview` String?, `path_doc_html` String?, `path_waveform` String?, `path_slides_json` String?, `path_slides_dir` String?, `path_excel_summary` String?, `path_excel_charts_json` String?, `path_excel_charts_dir` String?, `path_excel_chart_sheets_json` String?, `excel_charts_pages_keep` Text?, `excel_default_sheet` String?, `path_video_original` String?, `path_video_poster` String?, `path_code_original` String?, `path_markdown_raw` String?, `hash_sha256` String?, `upload_op_id` String?, `width` Integer?, `height` Integer?, `pages` Integer?, `duration` Float?, `words` Integer?, `slides_count` Integer?, `video_duration` Float?, `video_width` Integer?, `video_height` Integer?, `video_mime` String?, `code_language` String?, `code_line_count` Integer?, `markdown_line_count` Integer?, `created_at` DateTime, `revision` Integer?, `tombstone` Boolean?, `updated_at` DateTime?.

## note_chunks

Поисковые чанки — дочерние данные заметки; CASCADE соответствует ORM delete-orphan. idx Float оставлен совместимым.

- PK: `id`.
- FK: `note_id → notes(id)`, ON DELETE CASCADE.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_note_chunks_note_id(note_id)`.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `note_id` String, `idx` Float, `text` Text, `embedding` Text.

## note_links

Оба FK CASCADE. Дополнительно BEFORE INSERT/UPDATE проверяет одного существующего ненулевого owner у обоих концов (SQLite triggers / PostgreSQL trigger function). Историческая связь разных пользователей архивируется. Триггер не является RLS; административный перенос владельца заметки требует отдельного согласованного плана.

- PK: `id`.
- FK: `from_id → notes(id)`, ON DELETE CASCADE; `to_id → notes(id)`, ON DELETE CASCADE.
- UNIQUE: `uq_note_links(from_id,to_id,reason)`.
- Индексы: `ix_note_links_to_id(to_id)`; `ix_note_links_from_id(from_id)`.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `from_id` String, `to_id` String, `reason` String?, `confidence` Float?, `created_at` DateTime.

## note_sources

Состав дочерних источников удаляется вместе с заметкой; удаление источника каскадно удаляет отношение, не заметку.

- PK: `id`.
- FK: `note_id → notes(id)`, ON DELETE CASCADE; `source_id → sources(id)`, ON DELETE CASCADE.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_note_sources_note_id(note_id)`.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `note_id` String, `source_id` String, `relevance` Float?.

## note_tags

Теги — дочерние данные; UNIQUE(note_id,tag), индексы note_id/tag соответствуют выборкам редактора и списка тегов.

- PK: `id`.
- FK: `note_id → notes(id)`, ON DELETE CASCADE.
- UNIQUE: `uq_note_tags(note_id,tag)`.
- Индексы: `ix_note_tags_note_id(note_id)`; `ix_note_tags_tag(tag)`.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `id` String, `note_id` String, `tag` String, `weight` Float?.

## sync_conflicts

Данные конфликтной копии сохраняются после удаления локальной заметки (SET NULL). Scope/user/remote/op — исторические идентификаторы, не новые FK на удаляемые сущности. Индекс scope + kind соответствует поиску сохранённых конфликтов.

- PK: `id`.
- FK: `local_note_id → notes(id)`, ON DELETE SET NULL.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_sync_conflicts_local_note_id(local_note_id)`; `ix_sync_conflicts_created_at(created_at)`; `ix_conflicts_scope_kind(user_id,client_id,remote_key,kind)`; `ix_sync_conflicts_remote_note_id(remote_note_id)`.
- Ownership: user_id nullable.
- Столбцы: `id` String, `local_note_id` String?, `remote_note_id` String?, `kind` String, `payload_json` Text, `created_at` DateTime, `user_id` String?, `client_id` String?, `remote_key` String?, `op_id` String?.

## sync_note_map

Старое отображение сохранено; локальный FK CASCADE, remote ID уникален. Не подменяет scoped sync_entity_map и не используется для автоматической активации legacy операций.

- PK: `local_note_id`.
- FK: `local_note_id → notes(id)`, ON DELETE CASCADE.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_sync_note_map_remote_note_id(remote_note_id)` UNIQUE.
- Ownership: через родительскую/логическую связь либо неприменимо.
- Столбцы: `local_note_id` String, `remote_note_id` String, `created_at` DateTime, `updated_at` DateTime.

## sync_outbox

Nullable note/user FK с SET NULL намеренно сохраняют очередь/историю при hard delete. protocol_version=0 — карантин; новые client_id/remote_key этим строкам не присваиваются. Составной индекс соответствует выборке scope + protocol + status + next_retry_at.

- PK: `id`.
- FK: `note_id → notes(id)`, ON DELETE SET NULL; `user_id → users(id)`, ON DELETE SET NULL.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: `ix_sync_outbox_created_at(created_at)`; `ix_sync_outbox_note_id(note_id)`; `ix_sync_outbox_user_id(user_id)`; `ix_sync_outbox_op_type(op_type)`; `ix_sync_outbox_status(status)`; `ix_outbox_scope_due(user_id,client_id,remote_key,protocol_version,status,next_retry_at)`.
- Ownership: user_id nullable.
- Столбцы: `id` String, `op_type` String, `user_id` String?, `note_id` String?, `payload_json` Text, `status` String, `tries` Integer, `last_error` Text?, `created_at` DateTime, `updated_at` DateTime, `protocol_version` Integer, `client_id` String?, `remote_key` String?, `entity_type` String?, `entity_id` String?, `entity_remote_id` String?, `base_revision` Integer?, `dependency_json` Text, `wire_json` Text?, `result_json` Text?, `next_retry_at` DateTime?.

## sync_state

Старый ручной механизм state сохранён как совместимая структура; runtime sync v1 использует sync_peer_state. Здесь нет новых FK или попыток преобразовать старый timestamp в v1 sequence.

- PK: `user_id`.
- FK: нет.
- UNIQUE: нет отдельных ограничений; см. unique indexes.
- Индексы: PK/UNIQUE.
- Ownership: user_id NOT NULL.
- Столбцы: `user_id` String, `last_pull_since` DateTime?, `last_success_at` DateTime?, `last_error` Text?, `updated_at` DateTime.

## Сохранённые старые индексы и миграторы

Чистая БД имеет канонические индексы и совместимые auth-индексы первоначальной Alembic revision. На копии ручной БД также остаются её старые `idx_*`; их SQL содержится в [schema-only fixture](../tests/fixtures/stage5_legacy_schema.sql). Это возможное дублирование индексов оставлено ради безопасного обновления, оптимизация/удаление не входят в Stage 5.

До Stage 5 ответственность была разделена между неполным Alembic auth revision, большим ручным db/migrate.py, stabilization_schema.py, sync_schema.py и ALTER TABLE в auth request. Теперь все изменения схемы находятся в четырёх Alembic revision и вызываемых ими frozen operations. Compatibility helpers останавливаются на additive baseline, не объявляя грязную базу готовой. Основной CLI доводит до проверенного head. Startup только проверяет, кроме явного DB_AUTO_MIGRATE в development/test.

`scripts/migrate_desktop_to_shared.py` — административный импорт данных, а не независимый мигратор схемы. Его merge по ID/email/username исторически существует, не запускается автоматически и не является способом связывания Supabase identity. FK включены, ошибки целостности откатывают импорт; политика сопоставления пользователей не перепроектировалась. `repair_orphan_ownership.py` также меняет только данные по явному плану. `main.rs` запускает тот же app.main; новых desktop схем нет. Тесты и browser harness используют Alembic, а не Base.metadata.create_all.
