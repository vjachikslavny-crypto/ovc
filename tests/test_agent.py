"""
Тесты агентской системы OVC.

Покрывают:
- _parse_llm_response: парсинг ответов LLM
- handle_user_message: все режимы (chat, synopsis, summarize, create_note, explain, translate)
- stream_user_message: SSE-стриминг
- История диалога (ChatMessage)
- build_system_prompt / build_user_prompt
- Счётчик токенов
- AgentReply схема
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.agent.orchestrator import (  # noqa: E402
    _parse_llm_response,
    _history_to_gemini,
    handle_user_message,
    stream_user_message,
    MODES,
)
from app.agent.draft_types import (  # noqa: E402
    AgentReply,
    ChatMessage,
    InsertBlockAction,
    AddTagAction,
    UpdateBlockAction,
    MoveBlockAction,
    AddLinkAction,
    RemoveTagAction,
    SetStyleAction,
)
from app.agent.prompts import (  # noqa: E402
    build_system_prompt,
    build_user_prompt,
    NoteContext,
    RelatedNote,
    LinkedNote,
)
from app.agent.token_counter import count_tokens  # noqa: E402


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_note_ctx(**kwargs) -> NoteContext:
    defaults = dict(title="Тест заметки", text_content="Содержимое заметки.", tags=["ai"], links=[], block_count=3)
    defaults.update(kwargs)
    return NoteContext(**defaults)

_CTX = ("system prompt", "user prompt")


# ---------------------------------------------------------------------------
# 1. Парсинг ответов LLM
# ---------------------------------------------------------------------------

class ParseLLMResponseTests(unittest.TestCase):

    def test_valid_json_empty_draft(self):
        raw = '{"reply": "Привет!", "draft": []}'
        reply, actions = _parse_llm_response(raw)
        self.assertEqual(reply, "Привет!")
        self.assertEqual(actions, [])

    def test_valid_json_with_add_tag(self):
        raw = '{"reply": "Добавил тег.", "draft": [{"type": "add_tag", "noteId": "n1", "tag": "python", "confidence": 0.9}]}'
        reply, actions = _parse_llm_response(raw)
        self.assertEqual(reply, "Добавил тег.")
        self.assertIsInstance(actions[0], AddTagAction)
        self.assertAlmostEqual(actions[0].confidence, 0.9)

    def test_markdown_wrapped_json(self):
        raw = '```json\n{"reply": "Готово", "draft": []}\n```'
        reply, _ = _parse_llm_response(raw)
        self.assertEqual(reply, "Готово")

    def test_markdown_wrapped_without_lang(self):
        raw = '```\n{"reply": "OK", "draft": []}\n```'
        reply, _ = _parse_llm_response(raw)
        self.assertEqual(reply, "OK")

    def test_invalid_json_returns_raw_text(self):
        raw = "Это не JSON"
        reply, actions = _parse_llm_response(raw)
        self.assertEqual(reply, raw)
        self.assertEqual(actions, [])

    def test_json_with_extra_text_before(self):
        raw = 'Вот ответ: {"reply": "Результат", "draft": []}'
        reply, _ = _parse_llm_response(raw)
        self.assertEqual(reply, "Результат")

    def test_invalid_draft_action_skipped(self):
        raw = '{"reply": "OK", "draft": [{"type": "update_block", "noteId": "n1", "patch": {}}]}'
        _, actions = _parse_llm_response(raw)
        self.assertEqual(actions, [])

    def test_mixed_valid_and_invalid_actions(self):
        raw = """{
            "reply": "Частично",
            "draft": [
                {"type": "add_tag", "noteId": "n1", "tag": "good", "confidence": 0.8},
                {"type": "update_block", "noteId": "n1", "patch": {}},
                {"type": "remove_tag", "noteId": "n1", "tag": "old"}
            ]
        }"""
        _, actions = _parse_llm_response(raw)
        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], AddTagAction)
        self.assertIsInstance(actions[1], RemoveTagAction)

    def test_insert_block_with_data_wrapper(self):
        raw = """{
            "reply": "Вставил",
            "draft": [{"type": "insert_block", "noteId": "n1", "afterId": null,
                "block": {"type": "heading", "data": {"level": 2, "text": "Заголовок"}}}]
        }"""
        _, actions = _parse_llm_response(raw)
        self.assertIsInstance(actions[0], InsertBlockAction)
        self.assertEqual(actions[0].block.data["level"], 2)

    def test_insert_block_auto_normalize_no_data_wrapper(self):
        raw = """{
            "reply": "OK",
            "draft": [{"type": "insert_block", "noteId": "n1", "afterId": null,
                "block": {"type": "heading", "level": 2, "text": "Без data"}}]
        }"""
        _, actions = _parse_llm_response(raw)
        self.assertIsInstance(actions[0], InsertBlockAction)
        self.assertIn("level", actions[0].block.data)

    def test_all_draft_action_types(self):
        raw = """{
            "reply": "Все типы",
            "draft": [
                {"type": "insert_block", "noteId": "n1", "afterId": null,
                 "block": {"type": "paragraph", "data": {"parts": [{"text": "Текст"}]}}},
                {"type": "update_block", "noteId": "n1", "id": "b1", "patch": {"text": "New"}},
                {"type": "move_block", "noteId": "n1", "id": "b2", "afterId": "b1"},
                {"type": "add_tag", "noteId": "n1", "tag": "важное", "confidence": 0.95},
                {"type": "remove_tag", "noteId": "n1", "tag": "черновик"},
                {"type": "add_link", "fromId": "n1", "toId": "n2", "reason": "связано", "confidence": 0.7},
                {"type": "set_style", "noteId": "n1", "styleTheme": "dark", "layoutHints": {}}
            ]
        }"""
        _, actions = _parse_llm_response(raw)
        self.assertEqual(len(actions), 7)
        types = [type(a) for a in actions]
        self.assertIn(InsertBlockAction, types)
        self.assertIn(UpdateBlockAction, types)
        self.assertIn(MoveBlockAction, types)
        self.assertIn(AddTagAction, types)
        self.assertIn(RemoveTagAction, types)
        self.assertIn(AddLinkAction, types)
        self.assertIn(SetStyleAction, types)

    def test_empty_draft_field_missing(self):
        raw = '{"reply": "Просто ответ"}'
        reply, actions = _parse_llm_response(raw)
        self.assertEqual(reply, "Просто ответ")
        self.assertEqual(actions, [])

    def test_draft_not_a_list(self):
        raw = '{"reply": "Ответ", "draft": "не массив"}'
        _, actions = _parse_llm_response(raw)
        self.assertEqual(actions, [])


# ---------------------------------------------------------------------------
# 2. handle_user_message: все режимы
# ---------------------------------------------------------------------------

class HandleUserMessageTests(unittest.TestCase):

    def test_modes_constant(self):
        for m in ("chat", "summarize_text", "detailed", "explain"):
            self.assertIn(m, MODES)

    def test_invalid_mode_falls_back_to_chat(self):
        from app.providers.llm_provider import MockLLM
        with patch("app.agent.orchestrator.get_llm", return_value=MockLLM()):
            reply = handle_user_message("Привет", mode="invalid_mode")
        self.assertEqual(reply.mode, "chat")

    # --- chat с mock LLM ---

    def test_chat_mode_with_mock_llm(self):
        mock = MagicMock()
        mock.chat.return_value = '{"reply": "Чем могу помочь?", "draft": []}'
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            reply = handle_user_message("Привет", mode="chat")
        self.assertEqual(reply.reply, "Чем могу помочь?")
        self.assertEqual(reply.mode, "chat")

    def test_chat_mode_draft_cleared(self):
        """В режиме chat draft actions принудительно очищаются."""
        mock = MagicMock()
        mock.chat.return_value = '{"reply": "OK", "draft": [{"type": "add_tag", "noteId": null, "tag": "test", "confidence": 0.8}]}'
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            reply = handle_user_message("Привет", note_id="my-note", mode="chat")
        self.assertEqual(reply.draft, [])

    # --- История диалога ---

    def test_chat_with_history_uses_chat_with_history_method(self):
        """С историей должен вызываться chat_with_history, не chat."""
        mock = MagicMock()
        mock.chat_with_history.return_value = '{"reply": "Помню", "draft": []}'
        msgs = [
            ChatMessage(role="user", text="Привет"),
            ChatMessage(role="assistant", text="Здравствуй"),
        ]
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            reply = handle_user_message("Как дела?", mode="chat", messages=msgs)
        mock.chat_with_history.assert_called_once()
        mock.chat.assert_not_called()
        self.assertEqual(reply.reply, "Помню")

    def test_history_to_gemini_conversion(self):
        msgs = [
            ChatMessage(role="user", text="Привет"),
            ChatMessage(role="assistant", text="Здравствуй"),
            ChatMessage(role="user", text="Как дела?"),
        ]
        result = _history_to_gemini(msgs)
        self.assertEqual(result[0]["role"], "user")
        self.assertEqual(result[1]["role"], "model")  # assistant → model для Gemini
        self.assertEqual(result[2]["role"], "user")
        self.assertEqual(result[0]["parts"][0]["text"], "Привет")

    def test_empty_history_uses_chat_not_chat_with_history(self):
        mock = MagicMock()
        mock.chat.return_value = '{"reply": "OK", "draft": []}'
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            handle_user_message("Привет", mode="chat", messages=[])
        mock.chat.assert_called_once()
        mock.chat_with_history.assert_not_called()

    # --- explain / translate ---

    def test_explain_mode_calls_llm(self):
        mock = MagicMock()
        mock.chat.return_value = '{"reply": "Это значит...", "draft": []}'
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            reply = handle_user_message("Что это?", mode="explain")
        self.assertEqual(reply.mode, "explain")
        self.assertEqual(reply.reply, "Это значит...")

    # --- summarize / create_note ---

    def test_summarize_mode_calls_llm(self):
        mock = MagicMock()
        mock.chat.return_value = '{"reply": "Конспект готов", "draft": [{"type": "insert_block", "noteId": "n1", "afterId": null, "block": {"type": "heading", "data": {"level": 2, "text": "Конспект"}}}]}'
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            reply = handle_user_message("", note_id="n1", mode="summarize_text")
        self.assertEqual(reply.mode, "summarize_text")
        self.assertGreater(len(reply.draft), 0)

    # --- Ошибки и fallback ---

    def test_llm_error_returns_fallback(self):
        mock = MagicMock()
        mock.chat.side_effect = Exception("Network error")
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            reply = handle_user_message("Привет", mode="chat")
        self.assertIn("Не удалось", reply.reply)
        self.assertEqual(reply.draft, [])

    def test_mock_llm_all_modes(self):
        from app.providers.llm_provider import MockLLM
        for mode in ("chat", "summarize_text", "detailed", "explain"):
            with patch("app.agent.orchestrator.get_llm", return_value=MockLLM()):
                reply = handle_user_message("тест", mode=mode)
            self.assertEqual(reply.mode, mode)
            self.assertGreater(len(reply.reply), 0)


# ---------------------------------------------------------------------------
# 3. stream_user_message
# ---------------------------------------------------------------------------

class StreamUserMessageTests(unittest.TestCase):

    def test_mock_llm_yields_done(self):
        from app.providers.llm_provider import MockLLM
        with patch("app.agent.orchestrator.get_llm", return_value=MockLLM()):
            events = list(stream_user_message("Привет"))
        types = [e["type"] for e in events]
        self.assertIn("done", types)

    def test_real_llm_streams_chunks(self):
        mock = MagicMock()
        mock.stream_chat.return_value = iter(["Привет", " мир", "!"])
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            events = list(stream_user_message("Тест"))
        deltas = [e["text"] for e in events if e["type"] == "delta"]
        self.assertIn("Привет", deltas)
        self.assertEqual(events[-1]["type"], "done")

    def test_stream_with_history(self):
        mock = MagicMock()
        mock.stream_chat.return_value = iter(["Ответ"])
        msgs = [ChatMessage(role="user", text="Привет"), ChatMessage(role="assistant", text="Здравствуй")]
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            events = list(stream_user_message("Следующий вопрос", messages=msgs))
        # stream_chat должен получить history
        call_kwargs = mock.stream_chat.call_args
        self.assertIsNotNone(call_kwargs.kwargs.get("history") or
                             (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None))

    def test_stream_error_yields_message(self):
        mock = MagicMock()
        mock.stream_chat.side_effect = Exception("Oops")
        with patch("app.agent.orchestrator.get_llm", return_value=mock), \
             patch("app.agent.orchestrator.assemble_context", return_value=_CTX):
            events = list(stream_user_message("Тест"))
        has_error = any(e["type"] == "error" for e in events)
        self.assertTrue(has_error)


# ---------------------------------------------------------------------------
# 4. Счётчик токенов
# ---------------------------------------------------------------------------

class TokenCounterTests(unittest.TestCase):

    def test_empty_string(self):
        self.assertEqual(count_tokens(""), 0)

    def test_english_text(self):
        # "hello world" = 2 токена в tiktoken cl100k
        tokens = count_tokens("hello world")
        self.assertGreater(tokens, 0)
        self.assertLess(tokens, 10)

    def test_longer_text_more_tokens(self):
        short = count_tokens("привет")
        long = count_tokens("привет мир это длинный текст с несколькими словами")
        self.assertGreater(long, short)

    def test_returns_int(self):
        self.assertIsInstance(count_tokens("test"), int)


# ---------------------------------------------------------------------------
# 5. Промпты
# ---------------------------------------------------------------------------

class PromptsTests(unittest.TestCase):

    def test_chat_system_prompt(self):
        p = build_system_prompt("chat")
        self.assertIn("insert_block", p)
        self.assertIn("draft", p)

    def test_explain_system_prompt(self):
        p = build_system_prompt("explain")
        self.assertIn("объясни", p.lower())

    def test_user_prompt_tags_and_links(self):
        ctx = _make_note_ctx(tags=["важное"], links=["Проект А"])
        prompt = build_user_prompt("Q", note_ctx=ctx, mode="chat")
        self.assertIn("важное", prompt)
        self.assertIn("Проект А", prompt)


# ---------------------------------------------------------------------------
# 6. ChatMessage + AgentReply схемы
# ---------------------------------------------------------------------------

class SchemasTests(unittest.TestCase):

    def test_chat_message_user(self):
        msg = ChatMessage(role="user", text="Привет")
        self.assertEqual(msg.role, "user")

    def test_chat_message_assistant(self):
        msg = ChatMessage(role="assistant", text="Здравствуй")
        self.assertEqual(msg.role, "assistant")

    def test_agent_reply_defaults(self):
        reply = AgentReply(reply="OK", draft=[])
        self.assertEqual(reply.mode, "chat")
        self.assertIsNone(reply.suggested_title)

    def test_agent_reply_with_mode(self):
        reply = AgentReply(reply="OK", draft=[], mode="explain")
        self.assertEqual(reply.mode, "explain")


if __name__ == "__main__":
    unittest.main()
