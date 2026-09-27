# Baseline: стабилизация OVC, этапы 0–2

Исходная ветка: `develop`, commit `5250d17`. Изменения выполняются локально;
`maksigma`, серверный PostgreSQL и упаковка desktop в этот этап не входят.

Фактическое состояние среды на момент копирования 2026-09-23:

- SQLite: `/Users/vjachikslavny/OVC/src/ovc.db`.
- Вложения: `/Users/vjachikslavny/data/uploads` (существующий legacy-каталог имеет приоритет).
- Режимы: `AUTH_MODE=none`, `APP_ENV=development`, `DESKTOP_MODE=false`, `SYNC_MODE=off`.
- Копия: `/Users/vjachikslavny/OVC/data/backups/20260923-190359-535280`.
- Изолированное восстановление: успешно; `quick_check=ok`, 214 путей и 1299 файлов снимка.
- Счётчики: users 8; notes 130; files 118; note_links 16; note_tags 8; sync_outbox 187.

Системы изменения схемы: SQLAlchemy metadata/create_all, `src/app/db/migrate.py`
(исторические SQLite ALTER TABLE), его вызов при старте FastAPI и из `scripts/start_server.sh`,
Alembic (`alembic/versions/20251226_init_auth_tables.py`), legacy-проверка
`email_verified_at` в auth, отдельный `scripts/migrate_desktop_to_shared.py`.
Это несколько механизмов, а не единая миграционная история. Не запускайте их вслепую.

Новый `src/app/db/stabilization_schema.py` добавляет только таблицу персональных предпочтений
графа и `refresh_tokens.auth_provider`. Рабочая БД не использовалась для тестового запуска;
добавления проверяются на временных БД и применятся при обычном запуске новой версии.
Старые записи refresh считаются local; в Supabase-only режиме после обновления нужно войти
заново, чтобы получить сессию с подтверждённым провайдером.

Неразрешённые данные, требующие отдельного контролируемого этапа:

- 117 FK-нарушений: sync_outbox 77, audit_logs 38, refresh_tokens 2;
- 1 связь между заметками разных владельцев (теперь скрыта проверками доступа);
- 41 файл без note_id: допустимые самостоятельные загрузки, **не считать автоматически мусором**;
- 1 outbox-запись без user_id; все 187 операций pending, не отправлять общим токеном;
- бесхозных заметок/файлов и отсутствующих файловых путей не обнаружено;
- дубликатов Supabase ID и конфликтующих email→Supabase mappings не обнаружено;
- после расширения контракта все 130 заметок читаются: 125 без нормализации,
  5 с добавлением канонических значений по умолчанию; неподдерживаемых — 0.

Не удалять `sync_applied_ops`, `sync_change_log`, `sync_state`, `sync_maps`,
`sync_outbox`, `sync_conflicts`, `group_preferences` и другую legacy-историю.
Не включать SQLite `foreign_keys=ON` глобально до отдельного ремонта данных.
Текущий протокол sync и альтернативный `maksigma` ещё не выбраны/не объединены.

Повторяемая проверка без записи: `.venv/bin/python -B scripts/audit_local_data.py`.
Инструкции восстановления: [data_backup_restore.md](data_backup_restore.md).
