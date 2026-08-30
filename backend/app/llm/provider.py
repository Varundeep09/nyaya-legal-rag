"""
LLM Provider abstraction interface and stubs for Gemini and Ollama providers.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List


class LLMProvider(ABC):
    """Abstract base class interface for LLM text generation providers."""

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        context_chunks: List[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Asynchronously streams response tokens from the LLM provider."""
        yield ""


class GeminiProvider(LLMProvider):
    """Google Gemini API Provider implementation stub."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        context_chunks: List[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Streams response tokens from Google Gemini API (stub)."""
        # TODO: Implement Google Gemini API streaming call
        yield "Gemini response stream stub."


class OllamaProvider(LLMProvider):
    """Ollama local self-hosted LLM Provider implementation stub."""

    def __init__(self, base_url: str, model_name: str):
        self.base_url = base_url
        self.model_name = model_name

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        context_chunks: List[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Streams response tokens from local Ollama instance (stub)."""
        # TODO: Implement Ollama local API streaming call
        yield "Ollama response stream stub."
