from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass
class NoteContext:
    """Контекст текущей заметки для промпта."""
    title: str
    text_content: str
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    block_count: int = 0


@dataclass
class RelatedNote:
    """Краткая информация о похожей заметке (TF-IDF)."""
    title: str
    snippet: str
    score: float = 0.0


@dataclass
class LinkedNote:
    """Полное содержимое заметки, связанной через NoteLink."""
    title: str
    text_content: str
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Системные промпты — все режимы возвращают обычный текст
# ---------------------------------------------------------------------------

JSON_SCHEMA_INSTRUCTION = """
ВАЖНО: Твой ответ должен быть СТРОГО В ФОРМАТЕ JSON следующего вида:
{
  "reply": "Твой текстовый ответ",
  "draft": []
}

Правило для draft:
- ВСЕГДА возвращай ВЕСЬ конспект ОДНИМ блоком типа "paragraph".
- ЗАПРЕЩЕНО использовать несколько insert_block.
- Весь текст пиши внутри одного "paragraph", разделяя переносами строк (\n).
- НЕ используй символы разметки (##, ###, •, **, *). Пиши чистым текстом.
- Для списков используй нумерацию (1., 2., ...) или тире (- пункт).
- Пример: {"type": "insert_block", "block": {"type": "paragraph", "data": {"parts": [{"text": "Заголовок\n\nТекст конспекта\n\n1. Первый пункт\n2. Второй пункт"}]}}}
"""

SYSTEM_PROMPT = f"""\\
Ты — AI-ассистент приложения OVC Human Notes. Помогай пользователю \\
с его заметками: отвечай на вопросы, объясняй, предлагай улучшения.

Правила:
1. Отвечай на русском языке.
2. Будь кратким и полезным.
3. Используй контекст заметки если он предоставлен.
4. Не выдумывай информацию.
{JSON_SCHEMA_INSTRUCTION}
"""

SYSTEM_PROMPT_SUMMARIZE = f"""\\
Ты — AI-ассистент приложения OVC Human Notes. Создай краткий конспект заметки.

Задача:
- Извлеки ТОЛЬКО факты, тезисы и действия из заметки
- НЕ пересказывай и НЕ комментируй текст заметки ("заметка начинается с...", "автор хочет..." — ЗАПРЕЩЕНО)
- НЕ добавляй информацию которой нет в оригинале
- Сожми до ключевых пунктов

Формат текста в draft:
- Раздели конспект на смысловые блоки, каждый с заголовком ЗАГЛАВНЫМИ БУКВАМИ
- После заголовка — пустая строка, затем пункты через тире (- )
- Между блоками — двойной перенос строки
- НЕ используй символы разметки (##, ###, •, **, *)

Пример формата текста:
ОСНОВНАЯ ТЕМА\n\n- Первый тезис\n- Второй тезис\n\nДЕТАЛИ\n\n- Пункт 1\n- Пункт 2

Правила:
1. Отвечай на русском языке.
2. В 'reply' — только "Краткий конспект:" (без лишних слов).
3. В 'draft' — РОВНО ОДИН insert_block с типом paragraph.
{JSON_SCHEMA_INSTRUCTION}
"""

SYSTEM_PROMPT_DETAILED = f"""\\
Ты — AI-ассистент приложения OVC Human Notes. Создай подробный конспект заметки.

Задача:
- Возьми содержимое заметки за основу и расширь каждую идею
- Добавь контекст, примеры, пояснения из своих знаний
- НЕ пересказывай текст заметки ("заметка содержит...", "автор пишет..." — ЗАПРЕЩЕНО)
- Пиши сразу по существу, как учебный конспект

Формат текста в draft:
- Раздели на смысловые блоки, каждый с заголовком ЗАГЛАВНЫМИ БУКВАМИ
- После заголовка — пустая строка, затем текст или пункты через тире (- )
- Между блоками — двойной перенос строки
- Отмечай свои дополнения словом [дополнено] в начале пункта
- НЕ используй символы разметки (##, ###, •, **, *)

Пример формата текста:
ТЕМА\n\n- Тезис из заметки\n- [дополнено] Расширение и контекст\n\nПРИМЕРЫ\n\n- Пример 1\n- Пример 2

Правила:
1. Отвечай на русском языке.
2. В 'reply' — только "Полный конспект:" (без лишних слов).
3. В 'draft' — РОВНО ОДИН insert_block с типом paragraph.
{JSON_SCHEMA_INSTRUCTION}
"""

SYSTEM_PROMPT_EXPLAIN = f"""\\
Ты — AI-ассистент приложения OVC Human Notes. Объясни содержимое заметки или выделенный фрагмент.

Задача:
- Понятно объясни о чём эта заметка
- Раскрой ключевые понятия и термины
- Если уместно — приведи примеры
- Ответь на конкретный вопрос пользователя если он его задал

Правила:
1. Отвечай на русском языке.
2. Будь конкретным (2-4 абзаца).
3. Используй контекст всей заметки для объяснения.
4. ВАЖНО: Весь свой ответ пиши ТОЛЬКО в поле 'reply'. Массив 'draft' всегда должен быть ПУСТЫМ ([]), ничего не вставляй в саму заметку.
{JSON_SCHEMA_INSTRUCTION}
"""

SYSTEM_PROMPT_STREAM = """\
Ты — AI-ассистент приложения OVC Human Notes. Отвечай на вопросы пользователя.
Отвечай на русском языке. Используй контекст заметки.
Будь кратким и полезным.
"""


@lru_cache(maxsize=16)
def build_system_prompt(mode: str = "chat", user_name: Optional[str] = None) -> str:
    """Собирает системный промпт. Кэшируется по (mode, user_name)."""
    prompts = {
        "chat": SYSTEM_PROMPT,
        "summarize_text": SYSTEM_PROMPT_SUMMARIZE,
        "detailed": SYSTEM_PROMPT_DETAILED,
        "explain": SYSTEM_PROMPT_EXPLAIN,
        "stream": SYSTEM_PROMPT_STREAM,
    }
    base = prompts.get(mode, SYSTEM_PROMPT)

    if user_name:
        return base + f"\n## О пользователе\nИмя: {user_name}\n"
    return base


def build_user_prompt(
    message: str,
    note_ctx: Optional[NoteContext] = None,
    related: Optional[list[RelatedNote]] = None,
    linked: Optional[list[LinkedNote]] = None,
    mode: str = "chat",
) -> str:
    """Собирает user-сообщение с контекстом заметки."""
    parts: list[str] = []

    # Контекст текущей заметки
    if note_ctx:
        ctx_lines = [f"## Текущая заметка: {note_ctx.title}"]
        if note_ctx.tags:
            ctx_lines.append(f"Теги: {', '.join(note_ctx.tags)}")
        if note_ctx.links:
            ctx_lines.append(f"Связи: {', '.join(note_ctx.links)}")
        ctx_lines.append(f"Блоков: {note_ctx.block_count}")
        ctx_lines.append(f"\nСодержимое:\n{note_ctx.text_content}")
        parts.append("\n".join(ctx_lines))

    # Связанные заметки через NoteLink
    if linked:
        link_lines = ["## Связанные заметки"]
        for n in linked:
            link_lines.append(f"\n### {n.title}")
            if n.tags:
                link_lines.append(f"Теги: {', '.join(n.tags)}")
            link_lines.append(n.text_content[:500])
        parts.append("\n".join(link_lines))

    # Похожие заметки через TF-IDF
    if related:
        rel_lines = ["## Похожие заметки"]
        for r in related:
            rel_lines.append(f"- **{r.title}**: {r.snippet}")
        parts.append("\n".join(rel_lines))

    # Инструкция по режиму
    if mode == "summarize_text":
        parts.append("## Задание\nСоздай краткий конспект этой заметки на основе её содержимого.")
    elif mode == "detailed":
        parts.append("## Задание\nСоздай подробный конспект этой заметки, дополнив своими знаниями.")
    elif mode == "explain":
        if message.strip():
            parts.append(f"## Вопрос пользователя\n{message}")
        else:
            parts.append("## Задание\nОбъясни содержимое этой заметки или выделенный фрагмент.")
    else:
        parts.append(f"## Сообщение пользователя\n{message}")

    return "\n\n".join(parts)
