from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Generator, Optional

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Абстракция языковых моделей."""

    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        raise NotImplementedError

    def chat_with_history(
        self,
        system: str,
        history: list[dict],
        user: str,
    ) -> str:
        """Чат с историей диалога. По умолчанию — игнорирует историю."""
        return self.chat(system, user)

    def stream_chat(
        self,
        system: str,
        user: str,
        history: Optional[list[dict]] = None,
        json_mode: bool = False,
    ) -> Generator[str, None, None]:
        """Стриминг ответа. По умолчанию — отдаёт весь ответ одним куском."""
        yield self.chat(system, user)


class MockLLM(LLMProvider):
    def chat(self, system: str, user: str) -> str:
        return '{"reply": "MOCK: нет подключения к AI", "draft": []}'

    def stream_chat(self, system, user, history=None, json_mode=False) -> Generator[str, None, None]:
        yield "MOCK: нет подключения к AI"


class GroqLLM(LLMProvider):
    """Groq API provider via OpenAI client."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 2048,
        temperature: float = 0.4,
        timeout: float = 30.0,
    ):
        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout,
        )
        self._model_name = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content

    def chat_with_history(
        self,
        system: str,
        history: list[dict],
        user: str,
    ) -> str:
        """Чат с историей диалога.
        """
        messages = [{"role": "system", "content": system}]
        
        for msg in history:
            role = "assistant" if msg.get("role") == "model" else "user"
            content = ""
            for part in msg.get("parts", []):
                content += part.get("text", "")
            messages.append({"role": role, "content": content})
            
        messages.append({"role": "user", "content": user})
        
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content

    def stream_chat(
        self,
        system: str,
        user: str,
        history: Optional[list[dict]] = None,
        json_mode: bool = False,
    ) -> Generator[str, None, None]:
        messages = [{"role": "system", "content": system}]
        if history:
            for msg in history:
                role = "assistant" if msg.get("role") == "model" else "user"
                content = ""
                for part in msg.get("parts", []):
                    content += part.get("text", "")
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user})

        kwargs: dict = dict(
            model=self._model_name,
            messages=messages,
            stream=True,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        stream = self._client.chat.completions.create(**kwargs)
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content


class OllamaLLM(LLMProvider):
    """Заготовка для подключения Ollama/vLLM. Пока не используется."""

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "mistral:7b-instruct"):
        self.endpoint = endpoint.rstrip('/')
        self.model = model

    def chat(self, system: str, user: str) -> str:  # pragma: no cover
        raise NotImplementedError("Ollama integration is not enabled yet")


def get_llm() -> LLMProvider:
    """Фабрика: возвращает настроенный LLM-провайдер или MockLLM как fallback."""
    from app.core.config import settings

    if not settings.groq_api_key:
        logger.warning("GROQ_API_KEY not set — using MockLLM fallback")
        return MockLLM()

    return GroqLLM(
        api_key=settings.groq_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )
