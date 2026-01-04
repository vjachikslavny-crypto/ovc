from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Абстракция будущих языковых моделей."""

    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        raise NotImplementedError


class MockLLM(LLMProvider):
    def chat(self, system: str, user: str) -> str:  # noqa: D401 - simple mock
        return "MOCK: propose no changes"


class OllamaLLM(LLMProvider):
    """Заготовка для подключения Ollama/vLLM. Пока не используется."""

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "mistral:7b-instruct"):
        self.endpoint = endpoint.rstrip('/')
        self.model = model

    def chat(self, system: str, user: str) -> str:  # pragma: no cover - placeholder
        raise NotImplementedError("Ollama integration is not enabled yet")
