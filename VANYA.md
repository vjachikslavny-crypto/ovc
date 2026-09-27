# OVC Human Notes — Агентская система: полный разбор

> Дата: 2026-04-07  
> Ветка: `claude/analyze-agent-system-y4AEW`

---

## 1. Как устроена агентская система (до изменений)

### Что это такое

Система — **LLM-оркестратор**, а не автономный агент с циклом. На каждый запрос пользователя:
1. Собирается контекст из БД
2. Один вызов LLM (Gemini 2.5-flash)
3. Разбирается JSON-ответ
4. Возвращается текст + список `draft actions` (предложения по изменению заметок)

Архитектурно это stateless request-response: нет персистентной памяти, нет циклического планирования.

---

### Файлы агентской системы

```
src/app/agent/
├── orchestrator.py   — главная логика, точка входа
├── context.py        — сборка промптов из БД и TF-IDF поиска
├── prompts.py        — системные и пользовательские промпты
├── draft_types.py    — Pydantic-модели для draft actions
├── block_models.py   — 19 типов блоков с валидацией
└── blocks_schema.py  — схема блоков

src/app/providers/
├── llm_provider.py   — абстракция LLM: GeminiLLM, MockLLM, OllamaLLM
└── structurizer.py   — вспомогательный конвертер draft actions

src/app/rag/
├── tfidf_index.py    — TF-IDF индекс для поиска похожих заметок
└── chunking.py       — разбивка текста на чанки

src/app/api/chat.py   — FastAPI эндпоинт POST /api/chat
```

---

### Поток данных (оригинальный)

```
POST /api/chat { text, noteId }
      ↓
chat_endpoint()             [api/chat.py]
  → get_current_user()      проверяем JWT
      ↓
handle_user_message(text, note_id, user_id)   [orchestrator.py]
  → get_llm()               GeminiLLM или MockLLM (fallback)
      ↓
assemble_context()          [context.py]
  → get_note_context()      загружаем Note из SQLite: блоки, теги, связи
  → get_related_notes()     TF-IDF поиск по NoteChunk
  → build_system_prompt()   89-строчные инструкции для LLM
  → build_user_prompt()     контекст + сообщение + токен-бюджет
      ↓
llm.chat(system, user)      Gemini API, response_mime_type="application/json"
      ↓
_parse_llm_response(raw)
  → убирает markdown-обёртку ```json...```
  → находит JSON объект через regex
  → валидирует каждый DraftAction через Pydantic TypeAdapter
  → автонормализация: блок без "data" wrapper → оборачивает
  → BUG-3 fix: подставляет noteId если LLM его не заполнил
      ↓
AgentReply { reply: str, draft: list[DraftAction] }
      ↓
ChatResponse { reply, draft: list[dict] }   → клиент
```

---

### DraftAction — 7 типов действий

| Тип | Что делает | Ключевые поля |
|-----|-----------|---------------|
| `insert_block` | Вставить блок в заметку | noteId, afterId, block:{type, data} |
| `update_block` | Обновить поля блока | noteId, id, patch |
| `move_block` | Переместить блок | noteId, id, afterId |
| `add_tag` | Добавить тег | noteId, tag, confidence (0-1) |
| `remove_tag` | Удалить тег | noteId, tag |
| `add_link` | Связать две заметки | fromId, toId, reason, confidence |
| `set_style` | Изменить оформление | noteId, styleTheme, layoutHints |

### 19 типов блоков

`heading`, `paragraph`, `bulletList`, `numberList`, `quote`, `todo`, `divider`,
`table`, `link`, `image`, `audio`, `video`, `doc` (PDF/DOCX), `sheet`, `slides`,
`code`, `markdown`, `youtube`, `instagram`, `tiktok`, `source`, `summary`

### LLM-провайдеры

```python
class LLMProvider(ABC):
    def chat(self, system: str, user: str) -> str: ...

class GeminiLLM(LLMProvider):   # production: gemini-2.5-flash, JSON mode
class MockLLM(LLMProvider):     # fallback без API-ключа
class OllamaLLM(LLMProvider):   # заготовка, raise NotImplementedError
```

**Конфигурация через .env:**
```
GEMINI_API_KEY=...
LLM_MODEL=gemini-2.5-flash
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.4
LLM_CONTEXT_BUDGET=6000
LLM_TIMEOUT_SECONDS=30
```

### Токен-бюджет

Грубая оценка: `len(text) // 4` символов на токен.  
Если контекст с заметкой + связанными заметками превышает `LLM_CONTEXT_BUDGET=6000` токенов — связанные заметки обрезаются (сначала удаляются наименее релевантные).

---

## 2. Что было исправлено

### 2.1 Тест `test_table_block_requires_summary` (test_block_models.py)

**Было:** Тест ожидал `ValidationError` при создании `TableBlock` без поля `summary`.

**Проблема:** В `block_models.py` поле `TableData.summary` объявлено как `Optional[str] = None` — ошибки нет. Тест устарел.

**Исправление:** Переписал тест — теперь он проверяет, что таблица **без** `summary` парсится успешно и `summary == None`.

```python
# Было:
def test_table_block_requires_summary(self):
    with self.assertRaises(ValidationError): ...

# Стало:
def test_table_block_without_summary_is_valid(self):
    parsed = parse_blocks([{"type": "table", "data": {"kind": "csv", "src": "..."}}])
    self.assertIsNone(parsed[0].data.summary)
```

### 2.2 Все тесты `test_upload_api.py` — 401 Unauthorized

**Было:** Все 12 upload-тестов падали с `AssertionError: 401 != 200`.

**Причина:** `TestClient` не передавал JWT-токен, а эндпоинты `/api/upload` и `/files/...` требуют `Depends(get_current_user)` / `Depends(get_current_user_or_refresh)`.

**Исправление:** В `test_upload_api.py` добавлен override зависимостей FastAPI:

```python
_TEST_USER = User(id="test-user-id", username="testuser", ...)

def _override_get_current_user():
    return _TEST_USER

app.dependency_overrides[get_current_user] = _override_get_current_user
app.dependency_overrides[get_current_user_or_refresh] = _override_get_current_user
```

**Дополнительно:** Тест `test_upload_rejects_plain_text` переименован в `test_upload_plain_text_accepted_as_markdown` — выяснилось, что `text/plain` включён в `MARKDOWN_MIME_TYPES` в `services/files.py`, поэтому принимается как markdown.

### 2.3 `test_sync_engine` — два падения

**Проблема 1:** `test_smoke_offline_create_then_update_then_sync` — тест устанавливал `sync_enabled = True`, но `trigger_sync_now()` проверяет `sync_mode`, а дефолт — `"off"`. Результат: `{"ok": False}`, тест падал на `assertTrue(result["ok"])`.

**Исправление:** Добавил в `setUp` / `tearDown`:
```python
self._old_sync_mode = settings.sync_mode
settings.sync_mode = "remote-sync"
# ...в tearDown:
settings.sync_mode = self._old_sync_mode
```

**Проблема 2:** `test_upload_waits_for_note_mapping` — вызов `_flush_upload_file(session, client, payload)` с 3 аргументами, но сигнатура функции `_flush_upload_file(session, client, item: SyncOutbox, payload)` требует 4.

**Исправление:** Создаём `SyncOutbox` запись и передаём как `item`:
```python
upload_item = SyncOutbox(op_type=OP_UPLOAD_FILE, ...)
session.add(upload_item)
sync_engine._flush_upload_file(session, _FakeClient(), upload_item, {...})
```

---

## 3. Новые функции агента — три режима

В API добавлено поле `mode` в запросе и ответе.

### API запрос (POST /api/chat)

```json
{
  "text": "...",
  "noteId": "abc-123",
  "mode": "chat | summarize | synopsis | create_note"
}
```

### API ответ

```json
{
  "reply": "...",
  "draft": [...],
  "mode": "...",
  "suggested_title": null
}
```

---

### Режим `chat` (по умолчанию)

Обычный разговор с ассистентом. Работает как раньше — LLM может предлагать любые draft actions по контексту.

**Промпт:** `SYSTEM_PROMPT` (89 строк, полные инструкции по 7 типам действий и 9 типам блоков).

---

### Режим `summarize` — конспект от LLM

LLM анализирует содержимое заметки и создаёт структурированный конспект в виде новых блоков.

**Как работает:**
1. Загружается полный контекст заметки (блоки, теги, связи)
2. Системный промпт (`SYSTEM_PROMPT_SUMMARIZE`) приказывает создать конспект 20-30% от объёма
3. LLM возвращает draft actions: `insert_block` с `heading` "Конспект", `bulletList` ключевых тезисов
4. Связанные заметки через TF-IDF **не ищутся** (не нужны для суммаризации)

**Системный промпт задаёт структуру конспекта:**
- Начало: `heading` H2 "Конспект" + `divider`
- Ключевые идеи: `bulletList`
- Выводы: `paragraph` или отдельный список

**noteId автоподстановка:** работает (блоки вставляются в ту же заметку).

---

### Режим `synopsis` — конспект от пользователя (без LLM)

Пользователь **сам пишет конспект** — система оформляет его как блоки. LLM **не вызывается**.

**Как работает (в `orchestrator.py::_handle_synopsis`):**
1. Текст пользователя разбивается по строкам
2. Если 1 строка → вставляется как `paragraph`
3. Если несколько строк → вставляется как `bulletList`
4. Перед этим добавляется `heading` H2 "Конспект пользователя" и `divider`

**Пример:**
```
Пользователь: "Главная идея: AI автоматизирует рутину\nВывод: нужно учиться prompt engineering"
Результат: 3 блока — heading, divider, bulletList с двумя пунктами
```

**Преимущество:** работает без API-ключа, мгновенно, без расходов на LLM.

---

### Режим `create_note` — создание новой заметки по теме

LLM создаёт полноценную структуру заметки по заданной теме.

**Как работает:**
1. Контекст существующих заметок **не загружается** (новая заметка)
2. Системный промпт (`SYSTEM_PROMPT_CREATE_NOTE`) приказывает создать 4-6 блоков
3. В draft actions `noteId = null` — клиент сам создаёт заметку и заполняет ID
4. Могут включаться `add_tag` действия для автотегирования

**Важно:** в этом режиме `noteId` в draft actions **не автозаполняется** (намеренно):
```python
if note_id and mode != "create_note":
    for action in actions:
        if action.note_id is None:
            action.note_id = note_id
```

**Клиентская логика (ожидается):**
1. Получить draft с `noteId = null`
2. Создать новую заметку (`POST /api/notes`)
3. Применить draft actions с новым ID

---

## 4. Тесты агента (tests/test_agent.py)

Создан новый файл с 42 тестами. Структура:

### `ParseLLMResponseTests` — парсинг ответов LLM

| Тест | Что проверяет |
|------|--------------|
| `test_valid_json_empty_draft` | Чистый JSON, пустой draft |
| `test_valid_json_with_add_tag` | JSON с AddTagAction |
| `test_markdown_wrapped_json` | Обёртка ` ```json...``` ` |
| `test_markdown_wrapped_without_lang` | Обёртка без языка ` ``` ` |
| `test_invalid_json_returns_raw_text` | Невалидный JSON → raw текст |
| `test_json_with_extra_text_before` | JSON внутри текста |
| `test_invalid_draft_action_skipped` | Невалидный action пропускается |
| `test_mixed_valid_and_invalid_actions` | Смесь валидных и невалидных |
| `test_insert_block_with_data_wrapper` | Блок с корректным `data` |
| `test_insert_block_auto_normalize_no_data_wrapper` | Автонормализация блока |
| `test_all_draft_action_types` | Все 7 типов actions за раз |
| `test_empty_draft_field_missing` | Нет поля `draft` в JSON |
| `test_draft_not_a_list` | `draft` не массив |

### `HandleUserMessageTests` — режимы оркестратора

| Тест | Что проверяет |
|------|--------------|
| `test_modes_constant` | MODES содержит все 4 режима |
| `test_invalid_mode_falls_back_to_chat` | Неизвестный mode → chat |
| `test_synopsis_single_line` | Одна строка → paragraph |
| `test_synopsis_multiline_creates_bullet_list` | Несколько строк → bulletList |
| `test_synopsis_note_id_set_in_actions` | noteId проставлен в действиях |
| `test_synopsis_without_note_id` | synopsis без заметки |
| `test_synopsis_returns_correct_reply_text` | Текст ответа |
| `test_chat_mode_with_mock_llm` | chat с мок LLM |
| `test_chat_mode_note_id_autofill` | Автозаполнение noteId в chat |
| `test_summarize_mode_calls_llm` | summarize вызывает LLM |
| `test_create_note_mode_note_id_not_autofilled` | create_note не заполняет noteId |
| `test_llm_error_returns_fallback` | Ошибка LLM → graceful fallback |
| `test_mock_llm_*` | Заглушки MockLLM для всех режимов |

### `PromptsTests` — системные и пользовательские промпты

Проверяет наличие ключевых секций в промптах для каждого режима.

### `AgentReplyTests` — схема ответа

Валидация Pydantic-модели `AgentReply`: дефолтные значения, новые поля `mode` и `suggested_title`.

---

## 5. Итоговое состояние тестов

```
tests/test_agent.py        42 passed  (новые)
tests/test_block_models.py 11 passed  (было 9 passed, 1 failed)
tests/test_sync_engine.py   3 passed  (было 1 passed, 2 failed)
tests/test_upload_api.py   13 passed  (было 4 passed, 12 failed)

ИТОГО: 69 passed, 0 failed
```

---

## 6. Изменённые файлы

| Файл | Что изменено |
|------|-------------|
| `src/app/agent/prompts.py` | Добавлены `SYSTEM_PROMPT_SUMMARIZE`, `SYSTEM_PROMPT_CREATE_NOTE`; `build_system_prompt()` и `build_user_prompt()` принимают `mode` |
| `src/app/agent/draft_types.py` | `AgentReply` получил поля `mode` и `suggested_title` |
| `src/app/agent/orchestrator.py` | Добавлены `MODES`, `_handle_synopsis()`, поддержка `mode` в `handle_user_message()` и `_stub_reply()` |
| `src/app/agent/context.py` | `assemble_context()` принимает `mode`; в `create_note` не загружает контекст заметки; в `summarize`/`create_note` не ищет related notes |
| `src/app/api/chat.py` | `ChatRequest` получил `mode`; `ChatResponse` получил `mode` и `suggested_title`; `chat_endpoint` передаёт mode в orchestrator |
| `tests/test_agent.py` | **Новый файл** — 42 теста агентской системы |
| `tests/test_block_models.py` | `test_table_block_requires_summary` → `test_table_block_without_summary_is_valid` |
| `tests/test_sync_engine.py` | Исправлены setUp/tearDown (sync_mode); исправлен `test_upload_waits_for_note_mapping` |
| `tests/test_upload_api.py` | Добавлен override `get_current_user`/`get_current_user_or_refresh`; исправлен тест `text/plain` |

---

## 7. Как запустить

```bash
# Установка зависимостей
pip install -r src/requirements.txt

# Запуск всех тестов
PYTHONPATH=src python -m pytest tests/ -v

# Запуск только агент-тестов
PYTHONPATH=src python -m pytest tests/test_agent.py -v

# Запуск сервера
cd src && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 8. Примеры API запросов

### Обычный чат
```json
POST /api/chat
{ "text": "Помоги структурировать заметку", "noteId": "abc-123", "mode": "chat" }
```

### LLM-конспект заметки
```json
POST /api/chat
{ "text": "", "noteId": "abc-123", "mode": "summarize" }
```

### Пользовательский конспект
```json
POST /api/chat
{ "text": "- Главный тезис\n- Вывод 1\n- Вывод 2", "noteId": "abc-123", "mode": "synopsis" }
```

### Создать заметку по теме
```json
POST /api/chat
{ "text": "Квантовые вычисления и их применение в ML", "mode": "create_note" }
```

---

## 9. Phase 4 — Расширение агентской системы (8 новых функций)

### 9.1 История диалога (ChatMessage)

Добавлена модель `ChatMessage` в `draft_types.py`:

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
```

`ChatRequest` теперь принимает поле `messages: List[ChatMessage]`. Если история передана, оркестратор конвертирует её в формат Gemini multi-turn через `_history_to_gemini()`:

```python
def _history_to_gemini(messages):
    # "assistant" → "model" для Gemini API
    return [{"role": "model" if m.role == "assistant" else "user",
             "parts": [{"text": m.text}]} for m in messages]
```

Затем вызывается `llm.chat_with_history(system, gemini_history, user)`, который использует `model.start_chat(history=history).send_message(user)`.

**API:**
```json
POST /api/chat
{
  "text": "Уточни про первый пункт",
  "noteId": "abc-123",
  "mode": "chat",
  "messages": [
    {"role": "user", "text": "Расскажи про машинное обучение"},
    {"role": "assistant", "text": "Машинное обучение — это..."}
  ]
}
```

---

### 9.2 Стриминг ответа (SSE)

Добавлен эндпоинт `POST /api/chat/stream` в `api/chat.py`.

**Формат SSE:**
```
data: {"type": "delta", "text": "Первый"}\n\n
data: {"type": "delta", "text": " фрагмент"}\n\n
data: {"type": "done"}\n\n
```

Или при ошибке:
```
data: {"type": "error", "message": "Ошибка стриминга"}\n\n
```

**Реализация в `orchestrator.py::stream_user_message()`:**
1. Собирается контекст с `mode="stream"` (без JSON-режима)
2. Вызывается `llm.stream_chat()` — генератор, использующий `generate_content(..., stream=True)`
3. Каждый чанк отправляется как SSE `delta`
4. По завершении — `[DONE]` маркер
5. Полный текст логируется в `MessageLog`

**GeminiLLM streaming** (в `llm_provider.py`):
```python
def stream_chat(self, system, user, history=None):
    model = genai.GenerativeModel(model_name=..., system_instruction=system)
    response = model.generate_content(user, stream=True)
    for chunk in response:
        if chunk.text:
            yield chunk.text
```

**Ограничение:** стриминг поддерживает только режим `chat`. Draft actions недоступны в стриминге — для них используйте `POST /api/chat`.

---

### 9.3 Режим `explain` — объяснение фрагмента

LLM объясняет выделенный текст из заметки.

**API:**
```json
POST /api/chat
{
  "text": "Объясни мне это",
  "noteId": "abc-123",
  "mode": "explain",
  "selection": "квантовая запутанность — феномен, при котором..."
}
```

**Промпт** (`SYSTEM_PROMPT_EXPLAIN`): LLM получает выделенный текст, контекст заметки и объясняет понятным языком. Может предлагать `insert_block` с объяснением.

**Параметр `selection`** передаётся через `ChatRequest.selection` → `assemble_context()` → `build_user_prompt()`.

---

### 9.4 Режим `translate` — перевод

LLM переводит содержимое заметки или выделенный фрагмент на целевой язык.

**API:**
```json
POST /api/chat
{
  "text": "",
  "noteId": "abc-123",
  "mode": "translate",
  "targetLanguage": "English",
  "selection": "Необязательный выделенный фрагмент"
}
```

**Промпт** (`SYSTEM_PROMPT_TRANSLATE`): LLM получает целевой язык и контент. Может возвращать `insert_block` с переводом или `update_block` с заменой текста.

**Параметры:** `target_language` (alias `targetLanguage`) + опциональный `selection`.

---

### 9.5 Контекст связанных заметок (NoteLink)

Агент теперь видит содержимое заметок, явно связанных с текущей через таблицу `NoteLink`.

**Реализация в `context.py::get_linked_notes()`:**
```python
def get_linked_notes(note_id, user_id, session, limit=3):
    # Находит NoteLink записи где from_id или to_id == note_id
    # Загружает блоки связанных заметок
    # Возвращает list[LinkedNote] с title и text
```

**`LinkedNote` dataclass** в `prompts.py`:
```python
@dataclass
class LinkedNote:
    title: str
    text: str
```

**Включается в контекст** для режимов `chat`, `explain`, `translate`. Связанные заметки приоритетнее TF-IDF (вставляются раньше в токен-бюджет).

---

### 9.6 Реальный счётчик токенов (tiktoken)

Добавлен файл `src/app/agent/token_counter.py`:

```python
def count_tokens(text: str) -> int:
    enc = _get_tiktoken()          # lazy-init tiktoken cl100k_base
    if enc is not None:
        return len(enc.encode(text))
    # Fallback: считаем слова + пунктуацию через regex
    return len(re.findall(r'\w+|[^\w\s]', text))
```

**Fallback:** если `tiktoken` не установлен — используется подсчёт токенов через `re.findall(r'\w+|[^\w\s]', text)` (точнее, чем `len(text)//4`).

**Зависимость:** `tiktoken>=0.7.0` добавлен в `src/requirements.txt`.

В `context.py` все вычисления бюджета теперь используют `count_tokens()` вместо `len(text)//4`.

---

### 9.7 Кэш промптов (lru_cache)

`build_system_prompt()` в `prompts.py` декорирован `@lru_cache(maxsize=16)`:

```python
@lru_cache(maxsize=16)
def build_system_prompt(mode: str = "chat", user_name: Optional[str] = None) -> str:
    ...
```

Ключ кэша: пара `(mode, user_name)`. Одинаковый mode + user всегда возвращает один и тот же объект — без повторной конкатенации строк.

**Ёмкость:** 16 записей покрывает все комбинации: 6 режимов × несколько user_name.

---

### 9.8 Логирование диалогов (MessageLog)

Каждый диалог записывается в таблицу `messages`.

**Модель** (обновлена в `db/models.py`):
```python
class MessageLog(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=generate_uuid)
    role = Column(String, nullable=False)       # "user" или "assistant"
    text = Column(Text, nullable=False)
    user_id = Column(String, nullable=True, index=True)
    note_id = Column(String, nullable=True, index=True)
    mode = Column(String, nullable=True)        # "chat", "summarize", etc.
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
```

**Вызов** через `_log_dialog(user_id, note_id, mode, user_text, assistant_text)` в `orchestrator.py`. Пишется в конце каждого успешного запроса (включая `stream_user_message`).

**Миграция** добавлена в `db/migrate.py`: ALTER TABLE для добавления колонок `user_id`, `note_id`, `mode` если их нет.

---

## 10. Обновлённый поток данных

```
POST /api/chat { text, noteId, mode, messages, selection, targetLanguage }
      ↓
chat_endpoint()
  → проверяем JWT, mode ∈ MODES
      ↓
handle_user_message(text, note_id, user_id, mode, messages, target_language, selection)
      ↓
  [synopsis?] → _handle_synopsis() без LLM → return
      ↓
  assemble_context(note_id, text, user_id, session, mode, target_language, selection)
    → get_note_context()      — блоки, теги, связи (только для note-режимов)
    → get_linked_notes()      — NoteLink-связанные заметки (chat/explain/translate)
    → get_related_notes()     — TF-IDF поиск (только chat)
    → count_tokens()          — tiktoken cl100k_base
    → build_system_prompt()   — @lru_cache(maxsize=16)
    → build_user_prompt()     — с linked, selection, target_language
      ↓
  [messages?]
    → llm.chat_with_history(system, gemini_history, user)   Gemini multi-turn
    → llm.chat(system, user)                                одиночный запрос
      ↓
  _parse_llm_response(raw)
  _log_dialog(user_id, note_id, mode, ...)    → MessageLog в БД
      ↓
AgentReply { reply, draft, mode }
      ↓
ChatResponse { reply, draft, mode, suggested_title }
```

```
POST /api/chat/stream { text, noteId, messages }
      ↓
chat_stream_endpoint() → StreamingResponse(generate())
      ↓
stream_user_message(text, note_id, user_id, messages)
  → assemble_context(..., mode="stream")
  → llm.stream_chat(system, user, history)   generate_content(stream=True)
      ↓
SSE: data: {"type":"delta","text":"..."}  × N
     data: {"type":"done"}
```

---

## 11. Обновлённое состояние тестов

```
tests/test_agent.py        50 passed  (42 старых + 8 новых для Phase 4)
tests/test_block_models.py 11 passed
tests/test_sync_engine.py   3 passed
tests/test_upload_api.py   13 passed

ИТОГО: 77 passed, 0 failed
```

---

## 12. Полный список режимов агента

| Режим | Описание | LLM? | Контекст заметки | Draft actions |
|-------|---------|------|-----------------|---------------|
| `chat` | Обычный чат | Да | Да | Да |
| `summarize` | LLM создаёт конспект | Да | Да | Да |
| `synopsis` | Пользователь пишет конспект | Нет | Нет | Да |
| `create_note` | LLM создаёт заметку | Да | Нет | Да (noteId=null) |
| `explain` | LLM объясняет фрагмент | Да | Да | Да |
| `translate` | LLM переводит содержимое | Да | Да | Да |

---

## 13. Новые файлы и изменения (Phase 4)

| Файл | Изменение |
|------|-----------|
| `src/app/agent/token_counter.py` | **НОВЫЙ** — tiktoken + fallback подсчёт |
| `src/app/agent/draft_types.py` | Добавлена модель `ChatMessage` |
| `src/app/agent/prompts.py` | `LinkedNote`, `SYSTEM_PROMPT_EXPLAIN/TRANSLATE/STREAM`, `@lru_cache` |
| `src/app/agent/context.py` | `get_linked_notes()`, `count_tokens()`, параметры `selection`/`target_language` |
| `src/app/agent/orchestrator.py` | История, стриминг, explain/translate, `_log_dialog()` |
| `src/app/providers/llm_provider.py` | `chat_with_history()`, `stream_chat()` |
| `src/app/db/models.py` | `MessageLog`: колонки `user_id`, `note_id`, `mode` |
| `src/app/db/migrate.py` | ALTER TABLE для новых колонок `messages` |
| `src/app/api/chat.py` | `messages`, `selection`, `targetLanguage` в запросе; `POST /api/chat/stream` |
| `src/requirements.txt` | `tiktoken>=0.7.0` |
| `tests/test_agent.py` | +8 тестов: StreamUserMessage, TokenCounter, ChatMessage, history |

---

## 14. Phase 5 — Фронтенд AI-чат панели

### Что добавлено

В редакторе заметок теперь есть кнопка **AI** и выдвижная чат-панель для взаимодействия с агентской системой прямо из интерфейса.

### Кнопка AI (FAB)

В группу плавающих кнопок (floating actions) добавлена кнопка `AI` с градиентным фоном:
- Располагается после кнопки "Прикрепить файл" (📎)
- CSS-класс: `.fab--ai` — градиент `accent → #6366f1`, белый текст, жирный шрифт

### AI-чат панель

Панель появляется при нажатии на кнопку AI. Расположена в правом нижнем углу (desktop) или снизу на всю ширину (mobile).

**Элементы панели:**
1. **Заголовок** — "AI Ассистент" + выбор режима + кнопка закрытия
2. **Область сообщений** — скроллируемый список с сообщениями пользователя и AI
3. **Поле ввода** — textarea + кнопка отправки

**Выбор режима** — dropdown с 6 вариантами:
- Чат (chat) — обычный разговор с AI
- Конспект (summarize) — AI создаёт конспект заметки
- Свой конспект (synopsis) — пользователь пишет конспект, система форматирует
- Новая заметка (create_note) — AI создаёт заметку по теме
- Объяснить (explain) — AI объясняет выделенный фрагмент
- Перевод (translate) — AI переводит содержимое

### Функциональность (ai_chat.js)

**Отправка сообщений:**
- Enter отправляет, Shift+Enter — перенос строки
- Отправка через `POST /api/chat` с `mode`, `noteId`, `text`
- Поддержка истории диалога (multi-turn): предыдущие сообщения передаются в `messages[]`

**Draft Actions:**
- Если AI предлагает изменения (insert_block, add_tag) — они отображаются в чате
- Кнопка "Применить" позволяет применить предложенные действия к заметке

**Закрытие панели:**
- Кнопка × в заголовке
- Клавиша Escape
- Клик вне панели (только на мобильных)

### Адаптивность

- **Desktop**: панель 400px, fixed right: 24px, bottom: 24px, z-index: 80
- **Mobile** (max-width: 900px): полная ширина, bottom: 0, border-radius сверху, z-index: 280

### API изменение

`ChatRequest.text` — убран `min_length=1`, теперь допускает пустую строку. Это нужно для режима `summarize`, где текст не обязателен.

### Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `src/templates/editor.html` | Добавлена кнопка `.fab--ai` и `<aside class="ai-chat">` панель |
| `src/static/js/ai_chat.js` | **НОВЫЙ** — логика чат-панели: отправка, история, draft actions |
| `src/static/js/editor.js` | Импорт `initAiChat`, инициализация панели |
| `src/static/css/styles.css` | Стили `.fab--ai`, `.ai-chat`, адаптивность |
| `src/app/api/chat.py` | `ChatRequest.text` допускает пустую строку |


## Переработка агентной системы OVC (Исправление интеграции AI)

### Исправление и отладка (Сессия 2)
В ходе запуска локального сервера и тестирования в браузере (с помощью subagent) были выявлены и устранены следующие проблемы с получением «сырого JSON» в чате:

1. **Очистка промптов от комментариев**: 
   - В файле `src/app/agent/prompts.py` из инструкции `JSON_SCHEMA_INSTRUCTION` удалены JS-подобные комментарии (типа `// массив действий`). Оказалось, что Gemini буквально копировала их в свой ответ, что приводило к ошибке `JSONDecodeError` при парсинге, из-за чего оркестратор выбрасывал сырой JSON-текст прямо в UI пользователя вместо конспекта.
2. **Толерантность к неэкранированным переносам строк**: 
   - Обновлен вызов парсера в `orchestrator.py`: `json.loads(raw, strict=False)`. Это предотвращает падение интерпретации, если Gemini решает генерировать переносы строк напрямую внутри JSON-значений.
3. **Успешное тестирование чат-интерфейса**:
   - Повторный тест UI в браузере показал, что теперь парсинг проходит корректно: в чат выводится только человекочитаемое сообщение (из поля `reply`), без внутренней технической разметки и "странных блоков".
4. **Выявление причин ошибок `summarize_text`**:
   - Обнаружено, что API-ключ Gemini `gemini-2.5-flash` исчерпал бесплатный суточный лимит (ограничение Free-Tier на 20 запросов к `generate_content` в сутки). Из-за этого при генерации конспекта оркестратор честно возвращает «*Не удалось связаться с AI. Попробуйте позже.*». Логика приложения сама по себе написана верно, и для корректной вставки автоматических конспектов требуется лишь восполнение квот/использование платного ключа.

### Предыдущие правки (Сессия 1)
- **Исправление парсинга JSON**: Восстановлена функция `_parse_llm_response` в `orchestrator.py` для корректного разделения текстового ответа (`reply`) и действий-блоков (`draft`).
- **Строгая схема JSON**: В промпты (`prompts.py`) добавлена инструкция о необходимости строго отвечать в формате JSON заданного вида при создании конспектов.
- **Поддерживаемые режимы AI**: Отключены устаревшие, в работе оставлены только требуемые (`chat`, `summarize_text`, `detailed`, `explain`).
- **Интеграция UI и API**: В модуле `api/chat.py` реализована отправка массива `draft actions`. На клиенте в `ai_chat.js` добавлена авто-отправка массива действий на эндпоинт `/api/commit` с последующей перезагрузкой страницы для немедленного отображения сгенерированных блоков.
- **Очистка тестов**: Удалены юнит-тесты для упраздненных функций (`translate`, `create_note`, `synopsis`) и верифицирована работа нового тестового набора для агентов.


### Интеграция с Groq (Отказ от Gemini)
- **Смена провайдера**: В файле `src/app/providers/llm_provider.py` заменен класс `GeminiLLM` на `GroqLLM`, который использует официальный `openai` клиент (PyPI модуль `openai`), поскольку Groq поддерживает совместимость с форматом OpenAI.
- **Очистка настроек**: В классе `Settings` (`src/app/core/config.py`) `GEMINI_API_KEY` был заменен на `GROQ_API_KEY`, а дефолтная модель изменена на `llama-3.3-70b-versatile` (предыдущая `llama3-70b-8192` была выведена из эксплуатации 'decommissioned').
- **Адаптация форматов**: В `chat_with_history` добавлен явный маппинг старых ролей Gemini (`model`) в `assistant` для корректной передачи истории в Groq, а также добавлен параметр `response_format={"type": "json_object"}`, заставляющий модель гарантированно возвращать чистый JSON.
- То же самое было проделано для файла окружения `.env`.

### Итоговое тестирование системы (Groq AI)
После перехода на актуальную модель `llama-3.3-70b-versatile` и указания валидного ключа `GROQ_API_KEY`, агентная система была полностью протестирована в браузере:
- **Отделение JSON**: Groq успешно возвращает ответы в строгом JSON-формате, а бекенд-парсер извлекает только `reply`. Сырых скобок, кавычек или мусора в чате (как и интерфейсных сбоев) больше нет.
- **Добавление блоков**: При запросе конспекта (summarize_text) модель генерирует массив `draft`, который успешно обрабатывается фронтендом, добавляя новые структурированные блоки (`heading`, `list`) напрямую в редактор заметки с перезагрузкой страницы.
- **Итог**: Перенос на Groq завершён успешно, все 4 режима AI полностью функциональны.


### Исправление исчезновения чата (Без перезагрузки страницы)
- **Проблема**: При генерации конспекта или других действий (draft actions) страница принудительно перезагружалась (`window.location.reload()`), что приводило к сбросу состояния всей страницы, внезапному закрытию панели AI и потере локальной истории переписки.
- **Событийное обновление (AJAX)**: Я пробросил функцию `refreshNoteState` из менеджера редактора (`editor.js`) напрямую в коллбэк инициализации `initAiChat` (параметр `onBlocksCommitted`).
- **Результат**: Теперь `ai_chat.js` вместо жесткой перезагрузки страницы вызывает внутреннюю перерисовку блоков редактора `refreshNoteState()`. Интерфейс больше не "скачет" — чат остаётся открытым, история не пропадает, а новые заметки от AI бесшовно появляются на заднем фоне редактора!


### Изоляция контекста истории (Предотвращение путаницы режимов)
- **Проблема**: При смене режима (например, с `чат` на `объяснение`) фронтенд в `ai_chat.js` отправлял на сервер всю историю предыдущего общения. В результате языковая модель путалась в контекстах, начинала заново выполнять старые запросы (например, повторно генерировать конспект) вместо выполнения новой задачи объяснения.
- **Решение**: Добавлен механизм сохранения режима (`mode`) для каждого отправленного и полученного сообщения в локальном списке (`state.messages`). Теперь перед отправкой запроса к `/api/chat` скрипт отфильтровывает историю: на сервер уходят только те сообщения, которые были сделаны в рамках **текущего выбранного режима** (`state.messages.filter(m => m.mode === mode)`).
- **Итог**: Контексты больше не смешиваются. Если ИИ делал конспект, он не вспомнит о нём, когда вы перейдёте в режим `объяснения`, и будет чётко отвечать на конкретно поставленный вопрос согласно системному промпту учителя.


### Блокировка изменений исходной заметки в режимах Chat и Explain
- **Проблема**: В режиме «объяснения» или «чата» ИИ возвращал `draft actions`, а фронтенд вставлял эти блоки (содержащие технический или лишний текст) прямиком в холст оригинальной заметки, хотя пользователь хотел получить ответ только в боковой панели.
- **Двухуровневое решение**:
  1. **На уровне промпта (`prompts.py`)**: В `SYSTEM_PROMPT_EXPLAIN` добавлена строгая директива о том, что массив `draft` всегда должен оставаться пустым (`[]`), а ответ нужно писать только в поле `reply`.
  2. **На уровне оркестратора (`orchestrator.py`)**: Добавлена принудительная очистка `draft_actions = []` для режимов `chat` и `explain`. Теперь бэкенд аппаратно игнорирует любые попытки нейросети модифицировать оригинальный текст заметки в этих режимах.
- **Итог**: Режимы обычного общения и объяснения теперь работают в формате «Только чтение» для ваших заметок — они отвечают строго вам в чат. Сгенерировать конспект в саму заметку могут только специализированные кнопки конспектирования.


### Визуальное обособление контента от ИИ
- **Проблема**: При генерации конспектов в режимах `summarize_text` и `detailed`, добавленные ИИ блоки сливались с основным текстом заметки пользователя.
- **Решение**: В оркестратор (`orchestrator.py`) добавлена логика автоматического внедрения блоков-разделителей (`type: "divider"`). Теперь, если ИИ возвращает массив `draft_actions` с новыми параграфами или списками, бэкенд оборачивает этот ответ в два графических разделителя: один перед началом сгенерированного текста, и один в самом конце.
- **Итог**: Конспекты чётко визуально отделяются от оригинальных мыслей человека с помощью горизонтальных разделителей (---------).


### Система подтверждения генерации ИИ (Approve / Reject)
- **Проблема**: Пользователь испытывал неудобства из-за автоматической вставки предложенных ИИ-блоков прямо в холст заметки, так как было непонятно, где оригинальный текст, а где сгенерированный. Разделители (dividers) не решали проблему спонтанного изменения заметки.
- **Решение**: Полностью переписана концепция добавления изменений от ИИ.
  1. В `ai_chat.js` отключен автоматический вызов `/api/commit`.
  2. Если массив `data.draft` непустой, в пузыре чата отображается карточка-предпросмотр (Preview) с текстом сгенерированных изменений.
  3. Под превью выводятся кнопки **✅ Применить к заметке** и **❌ Отклонить**.
  4. При нажатии "Применить" данные отправляются в базу, и холст заметки обновляется, а статус карточки меняется на "Применено". При нажатии "Отклонить" карточка закрывается без изменений заметки.
  5. Удалены принудительные горизонтальные разделители (dividers) из `orchestrator.py`, так как теперь пользователь сам одобряет каждый вставляемый кусок текста, и мусор в заметке больше не нужен.
  6. Добавлен свежий UI для карточки в `styles.css`.


### Финальная шлифовка UI и маркировка ИИ-контента
- **Исправление заголовков**: В `blocks_render.js` добавлена автоматическая очистка заголовков (heading) от ведущих символов `#`. Ранее модель часто присылала текст вида "## Заголовок", и решетки отображались буквально. Теперь они вырезаются программно.
- **Маркировка блоков от ИИ**: Реализована система визуального контроля за происхождением контента.
  - При подтверждении изменений в чате (`Approve`), каждый блок из `draft` помечается скрытым флагом `source: "ai"`.
  - В рендерер заметок добавлена логика: блоки с меткой `ai` получают специальный бейдж **AI** в верхнем правом углу. Это позволяет всегда отличить, что написал человек, а что добавила нейросеть.
  - Кратковременно тестировалась цветная полоса слева для ИИ-блоков, но по просьбе пользователя она была удалена для сохранения чистоты интерфейса.
- **Репозиционирование кнопок (FAB)**: Группа плавающих кнопок (Добавить, Связи, Голос, Файл, AI) была перенесена и зафиксирована в боковом меню под графом связей.
  - Это решило проблему «прыгающих» кнопок, которые раньше плавали поверх текста и мешали чтению длинных заметок.
  - Кнопки теперь выстроены в компактный горизонтальный ряд внутри сайдбара, всегда доступны и не перекрывают рабочую область.
- **Авария и восстановление структуры**: В процессе переноса панелей была случайно нарушена верстка `editor.html` (пропадал заголовок и связи). Файл был полностью восстановлен с корректной вложенностью тегов, сохранив новый дизайн сайдбара.

### Борьба с дроблением контента (Анти-фрагментация)
- **Проблема**: При генерации конспектов ИИ создавал множество отдельных блоков (заголовок, пункты списка, абзацы). Это приводило к нагромождению бейджей "AI" в редакторе и усложняло управление заметкой.
- **Инструкции для ИИ (`prompts.py`)**: Промпты были обновлены — теперь ИИ строго запрещено использовать несколько `insert_block`. Он обязан упаковывать весь свой ответ в один блок типа `paragraph`, используя внутренние переносы строк для структуры.
- **Системный фильтр (`orchestrator.py`)**: В бэкенд добавлена логика "жесткой склейки". Если модель всё же присылает несколько блоков, сервер перехватывает их и объединяет в один единственный текстовый абзац. Больше никаких списков как набора отдельных объектов.
- **Результат**: Каждый ответ ИИ теперь выглядит как одно цельное сообщение с одним бейджем **AI**. Это сохраняет чистоту холста и делает интерфейс более предсказуемым.


### Усиление промптов для единого блока конспекта
- **Проблема**: Несмотря на anti-fragmentation код, промпты всё ещё содержали упоминания `bulletList` и `insert_block (заголовок + список тезисов)`, что провоцировало LLM создавать несколько блоков.
- **Решение**: В `prompts.py` промпты `SYSTEM_PROMPT_SUMMARIZE` и `SYSTEM_PROMPT_DETAILED` обновлены — теперь явно требуют "РОВНО ОДИН insert_block с типом paragraph", с использованием переносов строк (`\n`) для форматирования внутри одного блока.


### Отделение кнопок управления от мини-графа
- **Проблема**: 5 плавающих кнопок (＋, ↔, 🎙, 📎, AI) были вложены внутрь `<aside class="graph-sidebar">`, который скрывается при ширине окна < 1380px через `display: none`. Кнопки исчезали вместе с графом.
- **Решение**:
  1. В `editor.html` блок `.floating-actions` вынесен из `graph-sidebar` на уровень `.editor-layout` — теперь кнопки и граф являются siblings, а не parent-child.
  2. В `styles.css` базовый стиль `.floating-actions` получил `position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%)` — кнопки всегда видны по центру-низу экрана.
  3. Мобильный media query (`max-width: 899px`) упрощён — убраны дублирующие свойства, оставлен только `--mobile-keyboard-offset`.
- **Результат**: Мини-граф скрывается/показывается при resize, а кнопки управления всегда остаются на экране.


### Улучшение качества и форматирования конспектов
- **Проблема**: Конспекты содержали "воду" (пересказ заметки: "заметка начинается с...", "автор хочет...") и raw markdown-символы (`##`, `•`), которые не рендерились в paragraph-блоках. Текст шёл сплошной стеной без переносов строк.
- **Решение (промпты — `prompts.py`)**:
  1. `SYSTEM_PROMPT_SUMMARIZE` и `SYSTEM_PROMPT_DETAILED` полностью переписаны — запрещены фразы-пересказы, требуется писать сразу по существу как учебный конспект.
  2. Введён формат: заголовки разделов ЗАГЛАВНЫМИ БУКВАМИ, пункты через тире (`- `), блоки разделены двойным переносом.
  3. Запрещены все символы markdown-разметки (`##`, `###`, `•`, `**`, `*`).
- **Решение (рендеринг — `blocks_render.js`)**:
  1. `renderParagraph()` теперь разбивает `part.text` по `\n` и вставляет `<br>` между строками (раньше `textContent` игнорировал переносы).
  2. Строки целиком из заглавных букв автоматически оборачиваются в `<strong>` — заголовки разделов рендерятся жирным.
- **Решение (orchestrator.py)**: Anti-fragmentation код больше не вставляет markdown-символы (`##`, `•`, `>`) при объединении блоков — использует UPPER для заголовков и тире для списков.
- **Результат**: Конспект выглядит структурированно — жирные заголовки разделов, пункты с отступами, чистый текст без мусорных символов.

### Сессия 3: Настройка UI/Улучшение UX для AI Агента
- **Удаление навязчивых элементов AI**:
  - Полностью удалён значок ("бейджик") "AI" с блоков текста, сгенерированных агентом (`blocks_render.js`). Теперь они просто отмечены стилем левой вертикальной линии (акцентного цвета) с очень лёгким фоном.
  - Это делает интерфейс редактора чище и органичнее, при этом ИИ-контент визуально отделен от человеческого текста блочным оформлением `quote-style` (`styles.css`).
  - Убрана кнопка `AI` из группы плавающих кнопок (FAB) в нижнем меню (`editor.html`). Взаимодействие с AI теперь не загромождает основной интерфейс редактора.
- **Корректировка Layering'a для чата (z-index)**:
  - Панель AI чата теперь гарантированно открывается **поверх** плавающих элементов управления (FAB), предотвращая наложение кнопок на заголовок чата (`styles.css`, установлен `.ai-chat--open { z-index: 300 }`).
- **Изоляция Контекста при Повторной Генерации**:
  - Внесены изменения в логику извлечения текста для контекста: функция `_blocks_to_text` (`context.py`) теперь игнорирует блоки, имеющие признак источника `source: "ai"`.
  - Благодаря этому, при генерации нескольких конспектов подряд, AI не опирается на свои же предыдущие ответы/генерации, а анализирует **только** исходный человеческий текст заметки. Это решает проблему "самозацикливания" и многократного пересказа собственных ответов нейросетью.


### Исправление архитектурных минусов агентской системы (2026-04-09)

#### 1. Стриминг для всех режимов (Fix #1)
- **Проблема**: `stream_user_message()` работал только в chat-режиме. Для summarize/detailed пользователь ждал полный ответ без фидбека (10-15 сек).
- **Решение**:
  - `orchestrator.py` — `stream_user_message()` теперь принимает параметр `mode` и возвращает dict-события вместо строк:
    - `{"type": "delta", "text": "..."}` — чанк текста (chat/explain, стримится в реальном времени)
    - `{"type": "reply", "text": "..."}` — полный reply (summarize/detailed, после сборки JSON)
    - `{"type": "draft", "draft": [...]}` — draft actions (summarize/detailed)
    - `{"type": "error", "message": "..."}` / `{"type": "done"}` — ошибка / конец
  - `llm_provider.py` — `stream_chat()` получил параметр `json_mode: bool` для передачи `response_format: {"type": "json_object"}` при стриминге JSON-ответов.
  - `chat.py` — SSE-эндпоинт `/api/chat/stream` теперь принимает `mode` и передаёт dict-события напрямую.
  - `ai_chat.js` — фронтенд переведён с `fetch` + `res.json()` на SSE-стриминг для ВСЕХ режимов. Текст chat/explain появляется по мере генерации; для конспектов сначала приходит reply, потом draft-превью.
- **Результат**: Пользователь сразу видит, что AI работает. Нет "мёртвого" ожидания.

#### 2. Рефакторинг anti-fragmentation (Fix #3)
- **Проблема**: 40-строчная inline-логика объединения блоков дублировалась бы в `handle_user_message` и `stream_user_message`.
- **Решение**: Вынесена в функцию `_consolidate_drafts(draft_actions) -> list[DraftAction]` в `orchestrator.py`. Используется в обоих местах без дублирования.
- **Результат**: Единая точка anti-fragmentation, легче поддерживать.

#### 3. Token counter с коррекцией под Llama-3 (Fix #5)
- **Проблема**: `tiktoken cl100k_base` (GPT-4 tokenizer) занижал подсчёт токенов для кириллицы на 15-20% относительно Llama-3 BPE (128k vocab). Token budget расходовался неточно.
- **Решение**: В `token_counter.py` добавлен коэффициент коррекции `_LLAMA_CORRECTION = 1.15`. Результат `tiktoken` умножается на 1.15 перед возвратом.
- **Результат**: Token budget точнее отражает реальное потребление контекста.

#### 4. Кросс-режимная история сообщений (Fix #6)
- **Проблема**: `ai_chat.js` фильтровал историю строго по текущему режиму. Если пользователь задал вопрос в chat, потом переключился на detailed — AI не знал о предыдущем разговоре.
- **Решение**: Фронтенд теперь отправляет последние 10 сообщений **всех режимов**. Сообщения из других режимов помечаются меткой `[Краткий конспект]`, `[Полный конспект]` и т.д. через `modeLabels()`.
- **Результат**: AI сохраняет контекст разговора при переключении между режимами.

#### 5. Лимит входного текста + уведомление при обрезке (Fix #7)
- **Проблема**: Длинные заметки обрезались token budget'ом незаметно — пользователь не знал, что конспект покрывает только часть заметки.
- **Решение**: В `context.py` → `assemble_context()`:
  1. Если `note_ctx.text_content` не влезает в бюджет, текст обрезается до `available * 4` символов с пометкой `[... текст обрезан из-за ограничения контекста]`.
  2. В `user_prompt` добавляется предупреждение `⚠️ ВНИМАНИЕ: Текст заметки был обрезан...`.
  3. Логируется `logger.info()` вместо `debug()` при обрезке.
- **Результат**: LLM знает об обрезке и сообщает пользователю. Пользователь понимает, что конспект неполный.

