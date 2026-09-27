# Stage 6 — runtime reliability и публичный HTTPS

Работа локальная, поверх `bd5b9a2` (Stage 0–5.1). Без изменения схемы,
редактора, wire-контрактов sync v1, repair-логики, desktop packaging или возможностей AI.
Alembic head остаётся `20260926_integrity`. Реальные `.env`, БД и uploads не используются
для тестовых записей. Stage 7 этим документом не запускается.

## Границы выполнения

- Upload HTTP: async только на границе, приём multipart ограничен размером и временем.
  Одновременно не больше `RUNTIME_WORKERS` multipart-запросов; превышение — 503/Retry-After.
  CPU/дисковая подготовка в отдельном executor без очереди. ORM-сессии открываются внутри
  нужного потока, закрываются до запуска конвертера. Публикация FileAsset и outbox — одна
  короткая транзакция после появления оригинала. Бюджет job 150 s, конвертера 90 s.
- Image/PDF/DOCX/RTF/PPTX/Excel/CSV/audio/video: отдельный Python-процесс на задание.
  Обычно доли секунды–секунды; сложный Office может занять десятки секунд. Обычные
  note/save/read не используют executor тяжёлых работ. Native parsers не исполняются
  в event loop. Нет Celery/Redis. Ошибки и превышение времени возвращаются вызывающему.
- FFprobe/FFmpeg: найденный executable, argv без shell, 30 s. LibreOffice: 60 s,
  отдельный временный профиль на операцию (нет общей блокировки пользовательского профиля).
  Общий родительский deadline 90 s ограничивает весь набор дочерних операций.
- PDF page / Excel window / Excel CSV: lookup владельца в короткой сессии; конвертация
  через тот же bounded executor и процесс; небольшое ограниченное превью возвращается
  в память, оригиналы передаются потоково. Сохранённые thumbnail/slide/chart/meta/code/MD
  читаются в обычном FastAPI threadpool. Лимиты строк/байтов существующих preview сохранены.
- Search: синхронный endpoint в FastAPI threadpool. Изменение заметки только помечает
  индекс грязным. Первый поиск лениво загружает persisted chunks живых заметок; TF-IDF fit
  вне DB-транзакции. Один search/fit одновременно; конкурирующий получает 503/Retry-After.
  Доступные пользователю ID фильтруются до ранжирования, результаты проверяются по живым
  owned notes. Пустой словарь/пустая БД допустимы. CPU fit не прерывается насильно.
- AI: обычный вызов и SSE producer выполняются в bounded executor; DB-контекст закрыт
  до LLM. Provider timeout 30 s, без автоматических повторных генераций. SSE очередь 8
  событий, общий budget `LLM_TIMEOUT_SECONDS + 5`; network read timeout также конечный.
  Полный ввод с историей/контекстом и ответ ограничены. Отмена прекращает producer,
  transport закрывается в finally; уже начатый синхронный сетевой read завершается по
  своему timeout. Заметку меняет только существующий explicit commit.
- TikTok short URL: bounded worker, общий deadline 10 s. Весь redirect fetch имеет process deadline; системный DNS изолирован в
  killable subprocess (сохраняется macOS/VPN resolver). Каждый HTTPS hop проверяется;
  соединение закреплено за проверенным IP при сохранении TLS hostname verification.
  YouTube/direct TikTok только разбирают URL, не загружают произвольные страницы.
- Desktop remote-file proxy: AsyncClient stream, 12 s network timeout, без redirect,
  лимит bytes, cleanup transport. Синхронный ownership/auth lookup вынесен из event loop.
  Только настроенный remote и identity текущего пользователя; глобального fallback-token нет.
- Sync: существующая ручная/фоновая модель, HTTP timeout 12 s. Скачивание в staging
  потоками с проверкой размера/SHA, подготовка файлов до page transaction. Cursor,
  receipt, ownership и revision-проверки сохранены. Runtime/storage ошибки не выдаются
  за истёкшую авторизацию. Фоновый цикл проверяет сигнал остановки между операциями.
- Auth, CRUD, graph, commit, export: синхронные обработчики в стандартном FastAPI
  threadpool; сессия не переносится между потоками. Supabase network timeout остаётся 10 s.
  Большие CPU export / поисковый fit не имеют принудительного thread-kill: это известная
  граница текущей архитектуры, без переписывания продукта.

## Процессы, хранение и отмена

`runtime.run_tool` использует argv, DEVNULL stdin, ограниченные хвосты stdout/stderr
(64 KiB каждый), deadline, exit-code check и reap. На POSIX создаётся отдельная группа;
при timeout/cancel уничтожаются также FFmpeg/LibreOffice descendants. Conversion worker
следит за PID родителя: аварийная гибель backend завершает его группу. Платформенная
проверка Windows отложена до этапа packaging, она не заявлена выполненной.

Загрузка копируется порциями 1 MiB, оригинал публикуется через rename, сгенерированные
байты пишутся в temp + fsync + replace. Перед записью проверяется свободное место,
в том числе multipart spool. Office zip проверяется по числу entries и expanded size.
Путь/имя от клиента не становится файловым путём. Новая FileAsset публикуется только
после появления оригинала. При rollback/timeout подготовленные UUID-файлы очищаются.
Crash между файловой записью и DB commit может оставить orphan/staging, но не успешную
FileAsset. Неизвестные файлы автоматически не удаляются; GC не входит в этап.

`X-Upload-Op-Id`/`X-Desktop-Op-Id`: повтор того же файла возвращает прежний asset;
другое содержимое или filename с тем же ID — 409. Для batch ID дополняется индексом.
Потеря HTTP-ответа после DB commit остаётся возможной: клиент должен повторять с тем же ID.

Отмена HTTP upload/обычного AI включает cancellation flag; работа занимает свой слот
до фактического завершения. Быстрая атомарная DB-транзакция не обрывается посередине.
Физически остановить произвольный Python thread безопасно нельзя; hard deadline
обеспечивается процессом для конвертаций и конечными сетевыми timeout для AI.

## Бюджеты по умолчанию

- Multipart request: 510 MiB, 30 s на получение тела; JSON/form metadata: меньший из
  request limit и `MAX_AI_CONTEXT_CHARS * 4 + 1 MiB`. Body budget применяется и без Content-Length.
- Один файл: 200 MiB и более строгий существующий лимит типа; конвертируемый документ:
  50 MiB. Video/code/Markdown не загружают весь оригинал в память.
- Preview: 16 MiB на результат; expanded Office: 200 MiB, не более 10000 entries.
- Файлов в запросе: 10. AI context/response: 100000 characters. Запас диска: 128 MiB.
- Тяжёлых HTTP jobs: 4 на процесс, очереди нет. Multipart admission также 4.
- Rate limits на минуту: upload 30/user, AI 30/user, search 120/user, refresh 60/IP
  и 60/user; login/register сохраняют существующие лимиты. Ограничитель потокобезопасен,
  не более 10000 активных ключей. Он локален процессу и сбрасывается при restart.

Статусы: 413 budget, 415 unsupported type, 422 invalid input/conversion, 507 low storage,
503 busy/unavailable, 504 timeout, 429 rate limit. При частично отправленном remote stream
превышение лимита обрывает соединение: заменить уже отправленный 200 на 413 невозможно.
Нельзя заявлять атомарность между SQL и filesystem; публикация/cleanup минимизируют окно.

## Медиа и браузер

Оригиналы/media используют Starlette streaming FileResponse: GET/HEAD, Accept-Ranges,
206 + Content-Range/Length, suffix/open/multipart ranges. Некорректные/невыполнимые ranges
дают 416; HEAD игнорирует Range. Сам header и число диапазонов ограничены.
MIME выбирается из допустимых типов; неизвестный active content — octet-stream attachment.
Имена Content-Disposition экранируются библиотекой. `nosniff` включён.
Сгенерированный doc.html получает отдельный sandbox CSP с `default-src 'none'`.

Permissions-Policy: microphone/self и clipboard-write/self; camera, geolocation,
clipboard-read выключены. Fullscreen/autoplay сохраняют browser default и существующую
iframe allow-delegation: глобальный запрет сломал бы разрешённые внешние видеоплееры. Вне localhost getUserMedia требует HTTPS
и согласия пользователя; OS/browser permissions нельзя исправить response header.
CSP сохраняет необходимые CDN, media blob/data/HTTPS, запрещает object и framing,
добавляет base-uri/self и form-action/self. Исключения img/media HTTPS и inline styles
нужны нынешним viewer/style flows, arbitrary script/connect HTTPS не включается.

## Production и доверенный proxy

Пример для заранее настроенного HTTPS hostname; секрет задаётся отдельно и не коммитится:

```dotenv
APP_ENV=production
PUBLIC_MODE=true
AUTH_MODE=local
DESKTOP_MODE=false
ALLOW_DESKTOP_DEV_FALLBACK=false
DB_AUTO_MIGRATE=false
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=
PUBLIC_BASE_URL=https://notes.example.org
ALLOWED_HOSTS=notes.example.org,127.0.0.1,localhost
CORS_ORIGINS=https://notes.example.org
TRUSTED_PROXY_IPS=127.0.0.1,::1
SYNC_MODE=off
SYNC_ENABLED=false
```

`AUTH_MODE=supabase|both` также поддерживаются с их настоящими server-side настройками.
`SECRET_KEY` должен быть отдельным непустым production secret. Cookie Domain лучше
оставить пустым (host-only). Пустой TRUSTED_PROXY_IPS не доверяет X-Forwarded-*.
Добавляйте только адрес непосредственного proxy, который сам очищает входящие forwarded
headers; это не список IP пользователей и не весь Интернет. Backend bind — loopback или
закрытая сеть. Если другие процессы на том же хосте недоверенные, loopback сам по себе
не является изоляцией proxy от них.

```bash
.venv/bin/python -B -m uvicorn app.main:app --app-dir src \
  --host 127.0.0.1 --port 8000 --no-proxy-headers --timeout-graceful-shutdown 10
```

`--no-proxy-headers` обязателен: application middleware должен видеть настоящий socket
peer; иначе внешний Uvicorn middleware уже мог переписать его. Готовые launch scripts
добавляют этот флаг. Необходимые миграции выполняются явно до запуска, после backup.
Публичный profile отклоняет AUTH_MODE=none (кроме явно dangerous override с warning),
небезопасные cookie, desktop dev fallback, wildcard hosts/proxy/CORS, auto-migration.
Public CORS не включает localhost/Tauri автоматически; нужный доверенный desktop origin
добавляется явно. Development сохраняет существующие local origins.

Secure/HttpOnly auth cookies, SameSite и CSRF double-submit сохраняются. Bearer requests
не требуют cookie-CSRF, пользовательский Origin не получает CORS permission автоматически.
HSTS добавляется только в public mode при достоверном HTTPS scheme. Host проверяется по
ALLOWED_HOSTS. HTTP → HTTPS redirect должен выполнять внешний proxy, приложение не
угадывает scheme по недоверенным заголовкам.

Реальный Cloudflare HTTPS E2E: **NOT VERIFIED** — текущий `.env` локальный AUTH_MODE=none,
публичный endpoint для безопасных изолированных записей не предоставлен. Tunnel не
создавался, production/.env не менялись. Это не доказательство готовности live deployment.

## SQLite, наблюдаемость и остановка

FK ON, busy_timeout 10000 ms, pool_pre_ping. WAL принудительно не включается: это
изменение persistent journal mode и backup-предпосылок, требующее отдельного решения.
SQLite остаётся БД с одним writer; для высокой нагрузки нужна отдельная capacity-проверка.
Краткие блокировки ждут SQLite timeout, затем дают явный 503/Retry-After; автоповтор
сохранений не обходит If-Match. Конкурирующие записи одной revision дают 200 + 409.

X-Request-ID сохраняет только безопасный короткий идентификатор или создаёт UUID.
Логируются status/duration, тип ошибки, timeout, low storage, busy, shutdown counts.
Новые diagnostics не печатают токены, cookies, note bodies или bytes файлов.
Непредвиденная HTTP-ошибка даёт безопасный 500 с correlation ID; приватный exception text
не уходит в response или Uvicorn traceback. После начала streaming соединение обрывается
с обезличенной диагностикой, не маскируя неполный ответ успешным завершением. SQLAlchemy
hide_parameters скрывает bind values в SQL tracebacks. Подробные subprocess stderr
не пересылаются пользователю. readyz делает schema/revision/FK-enabled/storage probe и
free-space check; без full integrity scan, directory scan или network. healthz — liveness.

Shutdown закрывает admission, отменяет jobs и процессы, останавливает sync polling,
освобождает engine. Уже начавшийся sync/auth HTTP может закончиться только по timeout;
лимит graceful shutdown Uvicorn и service manager должен учитывать это. SIGKILL оставляет
staging, но не публикует его и не запускает destructive cleanup при restart.

## Проверки и доказательства

Постоянные сценарии:
`tests/test_stage6.py`, `tests/manual_runtime_smoke.py`, существующие Stage 4.1/5/sync,
`tests/manual_editor_smoke.py`, `tests/note_save.test.mjs`.

```bash
.venv/bin/python -B -m pytest -q
node --test tests/note_save.test.mjs
.venv/bin/python -B tests/manual_editor_smoke.py
OVC_BROWSER_SYNTHETIC_MIC=1 .venv/bin/python -B tests/manual_runtime_smoke.py
```

Все destructive/kill/failure/concurrency scenarios работают только с временными DB/storage.
Результаты браузера относятся к Chromium/macOS, а не к физическому микрофону, Safari,
мобильному устройству, Windows или live Supabase/Groq/Cloudflare.

## Результаты 2026-09-27

До изменения runtime: full Python **233 passed / 0 failed / 0 skipped / 243 warnings**;
JS **7/0/0**, Chromium editor **9 PASS**. Baseline integrity/restore подтвердились.
После изменений: full Python **281 passed / 0 failed / 0 skipped / 208 warnings**.
В полном наборе: Stage 4.1 — 12, Stage 5 — 19, Stage 6 — 48, sync engine/protocol — 103,
legacy audit — 8. Поднаборы не складываются с общим числом.
Отдельный focused прогон Stage 4.1 + Stage 5 + sync + первые 47 Stage 6: **181 passed,
0 failed, 0 skipped, 168 warnings**. После добавления проверки безопасных 500-ошибок
Stage 6 отдельно: **48 passed, 0 failed, 0 skipped, 42 warnings**.
Pytest также печатает один завершающий SWIG DeprecationWarning вне своего summary.
Остальные warnings — существующие Pydantic V2, FastAPI on_event, Jinja API, SWIG;
это не ошибки проверок и не скрытые skip.

JS: **7 passed, 0 failed, 0 skipped, 0 warnings**. Editor Chromium smoke: **9 PASS**.
Runtime Chromium/HTTP/crash smoke: **5 PASS** (источник аудио, audio seek, video seek,
отзывчивость настоящего HTTP сервера при конвертации, kill/restart).
В browser scripts 2 предупреждения Pydantic при импорте app; pytest totals их не включают.
AST parse Python, bash -n и git diff --check: PASS. Новый WebM regression проверяет
различение `audio/webm`/`video/webm`, в том числе MIME с codecs; раньше расширение `.webm`
всегда забирала ветка audio, и video/source возвращал ошибку.

**Проверка микрофона:** headless getUserMedia в данном окружении зависает даже с
fake-device/file-capture flags. Дополнительный **headed Chromium** с виртуальным WAV
устройством выполнил настоящий `getUserMedia → MediaRecorder → WebM upload` без замены
API захвата; все **5 runtime smoke cases PASS**. Дополнительно headless-прогон с
`OVC_BROWSER_SYNTHETIC_MIC=1` проверяет цепочку с WebAudio source. Permissions Policy
проверена через browser featurePolicy. Физический микрофон и OS permission prompt не
тестировались; реальные звуки не записывались. Публичный HTTPS-туннель NOT VERIFIED.

Для полного нативного capture path в этом macOS окружении:

```bash
OVC_BROWSER_HEADED=1 .venv/bin/python -B tests/manual_runtime_smoke.py
```

Локальные измерения настоящего HTTP сервера (test dataset, параллельно с regression suite):

- GET notes: median **1.61 ms**, p95 **18.59 ms**, n=10.
- PATCH note: median **5.68 ms**, p95 **11.14 ms**, n=10.
- Search: median **1.85 ms**, p95 **4.11 ms**, n=10.
- Readiness: median **7.08 ms**, p95 **46.71 ms**, n=10.
- Small TXT upload: median **549.33 ms**, p95 **557.53 ms**, n=5.
- DOCX conversion: median **557.64 ms**, p95 **570.20 ms**, n=5.

p95 — nearest-rank, при n=5 это максимум; это диагностические малые выборки, не capacity
benchmark. Основная фиксированная цена upload — запуск Python-конвертера; для больших
файлов дополнительно native parsing. CPU/memory нагрузка конвертеров не означает
неограниченную масштабируемость; budget 4 jobs задан на один процесс. Тест трёх разных
аккаунтов использует один TestClient portal/event loop: медленная конвертация + AI,
параллельно list/get/PATCH/search/file/health/ready другого владельца; время <2 s.

Реальные данные проверены повторно после тестов и локального перезапуска:

- **1 300 SHA-256 совпали**: реальный `.env`, DB и **1 298 upload-файлов**.
- Новых upload-файлов: **0**, изменённых: **0**; все table counts совпали с baseline.
- `quick_check=ok`, FK=0, canonical refs=0, cross-owner links=0, repair actions=0,
  ambiguous=0; Alembic head остался `20260926_integrity`.
- Legacy: **187 quarantined / 0 auto-sendable / 0 migrated**; очередь не replay-илась.
- Свежая копия `/private/tmp/ovc-stage6/final-backup`, isolated restore **verified=true**,
  quick_check=ok, existingFKWarnings=0, storedPathsChecked=214, source counts unchanged.
- Рабочие `/healthz`, `/readyz`, `/openapi.json`: **200**. Проверочные endpoints не
  выполняли записи заметок, repair или миграции. Реальный режим остался development/none/off.

Приватные manifests, SQL-копии и подробные logs сохранены только в `/private/tmp/ovc-stage6`,
не в Git. Исходный незакоммиченный `tmp/server.pid` не редактировался.

## Остаточные ограничения и решение

- Публичный tunnel, live Supabase/Groq, физический microphone, Safari/mobile и другие ОС
  не проверялись. Изолированный HTTPS proxy/CORS/cookie/CSRF контракт и provider failures
  проверяются автоматическими тестами; это не live production E2E.
- Конвертер отделён процессом для deadline/cleanup, но не является security sandbox.
  Жёсткая OS memory/disk quota, hostile document sandbox и antivirus здесь не вводились.
  Лимиты входа/expanded ZIP/preview/time/free space уменьшают риск, не дают абсолютной
  гарантии против ошибок native библиотек или одновременного заполнения диска извне.
- SQLite — один writer; limiter/executor локальны процессу. Для нескольких worker/server
  процессов лимиты суммируются; высоконагруженный multi-instance deployment не заявлен.
- Orphan/temp после crash не становятся live assets, но требуют отдельного управляемого
  cleanup. Автоматический file GC намеренно отсутствует.
- Уже начавшийся синхронный сетевой read/TF-IDF fit/Python thread не прерывается насильно.
  Конвертации и внешнее URL fetching имеют process deadline; модель использует timeout и
  cooperative cancellation. SSE после отправки 200 передаёт ошибку событием, не новым HTTP status.

**GO — safe to begin Stage 7 desktop packaging**

GO относится к переходу на следующий этап разработки, не к заявлению, что live public
production, физический capture и все OS/WebView уже прошли E2E. Известные границы выше
остаются обязательной частью дальнейшей проверки.

Stage 7 не начинался. Код не коммитился и не пушился.

## Изменённые файлы

- `.env.example`
- `README.md`
- `deploy/cloudflare_tunnel/start_public_server.sh`
- `scripts/start_server.sh`
- `src/.env.example`
- `src/app/agent/context.py`
- `src/app/agent/orchestrator.py`
- `src/app/api/chat.py`
- `src/app/api/commit.py`
- `src/app/api/export.py`
- `src/app/api/files.py`
- `src/app/api/graph.py`
- `src/app/api/notes.py`
- `src/app/api/resolve.py`
- `src/app/api/routes/auth.py`
- `src/app/api/sync.py`
- `src/app/api/upload.py`
- `src/app/core/config.py`
- `src/app/db/engine.py`
- `src/app/db/readiness.py`
- `src/app/db/session.py`
- `src/app/main.py`
- `src/app/providers/llm_provider.py`
- `src/app/rag/tfidf_index.py`
- `src/app/services/files.py`
- `src/app/services/rate_limit.py`
- `src/app/services/sync_engine.py`
- `tests/conftest.py`
- `tests/test_sync_engine.py`
- `docs/stabilization_stage_6.md`
- `src/app/core/http_runtime.py`
- `src/app/services/conversion_worker.py`
- `src/app/services/media_response.py`
- `src/app/services/public_url.py`
- `src/app/services/runtime.py`
- `src/app/services/storage.py`
- `src/app/services/upload_pipeline.py`
- `src/app/services/viewer_jobs.py`
- `tests/manual_runtime_smoke.py`
- `tests/test_stage6.py`
