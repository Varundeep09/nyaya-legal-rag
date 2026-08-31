"""
LLM Provider abstraction interface and implementations for Google Gemini and local Ollama.
Supports real token streaming with asynchronous generators.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional
import google.generativeai as genai

from app.core.config import Settings
from app.core.logging import logger
from app.llm.prompts import NYAYA_SYSTEM_PROMPT, build_rag_prompt, format_chunk_citation_key

DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"


class LLMProvider(ABC):
    """Abstract base class interface for LLM text generation providers."""

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = NYAYA_SYSTEM_PROMPT,
        context_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[str, None]:
        """Asynchronously streams response tokens from the LLM provider."""
        yield ""


class GeminiProvider(LLMProvider):
    """
    Google Gemini API Provider implementation using official google-generativeai SDK.
    Supports real-time token streaming with async generate_content_async(stream=True).
    """

    def __init__(self, api_key: str, model_name: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key
        self.model_name = model_name
        self._is_configured = False

        if self.api_key and self.api_key not in ("your_gemini_api_key_here", "dev-secret-key-change-in-production"):
            try:
                genai.configure(api_key=self.api_key)
                self._is_configured = True
                logger.info("Configured Google Gemini API provider with model: %s", self.model_name)
            except Exception as e:
                logger.warning("Failed to configure Google Gemini API: %s", e)

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = NYAYA_SYSTEM_PROMPT,
        context_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens from Google Gemini API.
        If API key is unconfigured or unreachable, provides a grounded local fallback
        synthesizing retrieved context chunks with their exact citations.
        """
        if self._is_configured:
            try:
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_prompt
                )
                response = await model.generate_content_async(prompt, stream=True)
                async for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception as e:
                logger.error("Gemini API stream error: %s. Engaging grounded statutory fallback.", e)

        # Grounded statutory fallback for offline/test environments
        logger.info("Executing grounded statutory response synthesis from %d context chunks...", len(context_chunks or []))
        if not context_chunks:
            yield "I don't have enough verified information in the Bharatiya Nagarik Suraksha Sanhita or the BNS offence schedule to answer this."
            return

        yield "Based on the statutory provisions:\n\n"
        await asyncio.sleep(0.02)

        for chunk in context_chunks:
            citation = format_chunk_citation_key(chunk)
            sec_title = chunk.get("section_title") or f"Section {chunk.get('section_number')}"
            text = chunk.get("text", "").strip()

            # Format succinct synthesized point
            first_para = text.split("\n\n")[0] if "\n\n" in text else text
            summary_snippet = first_para[:350].strip()
            
            yield f"• Under {citation} ({sec_title}), {summary_snippet} {citation}\n\n"
            await asyncio.sleep(0.03)


class OllamaProvider(LLMProvider):
    """Ollama local self-hosted LLM Provider implementation using httpx streaming."""

    def __init__(self, base_url: str, model_name: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = NYAYA_SYSTEM_PROMPT,
        context_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[str, None]:
        """Streams response tokens from local Ollama instance."""
        import httpx
        import json

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system_prompt,
            "stream": True
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
        except Exception as e:
            logger.error("Ollama connection error: %s", e)
            yield f"Error communicating with local Ollama model '{self.model_name}': {str(e)}"


def get_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Factory function returning the configured LLM provider instance."""
    from app.core.config import Settings
    cfg = settings or Settings()

    if cfg.LLM_PROVIDER.lower() == "ollama":
        return OllamaProvider(base_url=cfg.OLLAMA_BASE_URL, model_name=cfg.OLLAMA_MODEL)
    return GeminiProvider(api_key=cfg.GEMINI_API_KEY, model_name=DEFAULT_GEMINI_MODEL)
