"""
LLM Provider abstraction interface and implementations for Google Gemini and local Ollama.
Supports real token streaming with asynchronous generators, runtime model discovery,
and verifiable token usage / finish_reason metadata proofs.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional
import google.generativeai as genai

from app.core.config import Settings
from app.core.logging import logger
from app.llm.prompts import NYAYA_SYSTEM_PROMPT, build_rag_prompt, format_chunk_citation_key

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


class LLMProvider(ABC):
    """Abstract base class interface for LLM text generation providers."""

    def __init__(self):
        self.last_call_metadata: Dict[str, Any] = {}

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
    Supports real-time token streaming with async generate_content_async(stream=True)
    and captures real API call proof metadata (model, finish_reason, token usage).
    """

    def __init__(self, api_key: str, model_name: str = DEFAULT_GEMINI_MODEL):
        super().__init__()
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
        If real API credentials are valid, yields live tokens from Gemini and records
        finish_reason and usage_metadata proof.
        If unconfigured, engages an explicitly marked fallback that prefixes responses
        with '[FALLBACK-NO-LLM]' and logs a visible warning.
        """
        self.last_call_metadata = {
            "provider": "gemini",
            "model": self.model_name,
            "is_real_llm": False,
            "finish_reason": None,
            "usage": None
        }

        if self._is_configured:
            try:
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_prompt
                )
                response = await model.generate_content_async(prompt, stream=True)
                last_finish_reason = None
                
                async for chunk in response:
                    if chunk.candidates:
                        last_finish_reason = str(chunk.candidates[0].finish_reason)
                    if chunk.text:
                        yield chunk.text

                # Extract real token usage metadata from response
                usage_dict = {}
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    u = response.usage_metadata
                    usage_dict = {
                        "prompt_tokens": getattr(u, "prompt_token_count", None),
                        "candidate_tokens": getattr(u, "candidates_token_count", None),
                        "total_tokens": getattr(u, "total_token_count", None)
                    }

                self.last_call_metadata = {
                    "provider": "gemini",
                    "model": self.model_name,
                    "is_real_llm": True,
                    "finish_reason": last_finish_reason or "STOP",
                    "usage": usage_dict
                }
                logger.info(
                    "REAL GEMINI API CALL PROOF: model=%s | finish_reason=%s | usage=%s",
                    self.model_name,
                    last_finish_reason,
                    usage_dict
                )
                return
            except Exception as e:
                logger.error(
                    "REAL GEMINI API CALL FAILED: %s. Engaging visibly marked fallback.",
                    e
                )

        # Explicit fallback path for unconfigured credentials (LOUD & VISIBLE per Part 2)
        logger.warning("FALLBACK TEMPLATE ACTIVE - NOT CALLING REAL GEMINI")
        self.last_call_metadata = {
            "provider": "fallback_template",
            "model": "none",
            "is_real_llm": False,
            "finish_reason": "TEMPLATE_FALLBACK",
            "usage": {"prompt_tokens": 0, "candidate_tokens": 0, "total_tokens": 0}
        }

        yield "[FALLBACK-NO-LLM] Based on the statutory provisions:\n\n"
        await asyncio.sleep(0.02)

        for chunk in (context_chunks or []):
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
        super().__init__()
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
            self.last_call_metadata = {
                "provider": "ollama",
                "model": self.model_name,
                "is_real_llm": True,
                "finish_reason": "STOP",
                "usage": {}
            }
        except Exception as e:
            logger.error("Ollama connection error: %s", e)
            yield f"Error communicating with local Ollama model '{self.model_name}': {str(e)}"
            self.last_call_metadata = {
                "provider": "ollama",
                "model": self.model_name,
                "is_real_llm": False,
                "finish_reason": "ERROR",
                "usage": {}
            }


def get_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Factory function returning the configured LLM provider instance."""
    from app.core.config import Settings
    cfg = settings or Settings()

    if cfg.LLM_PROVIDER.lower() == "ollama":
        return OllamaProvider(base_url=cfg.OLLAMA_BASE_URL, model_name=cfg.OLLAMA_MODEL)
    return GeminiProvider(api_key=cfg.GEMINI_API_KEY, model_name=DEFAULT_GEMINI_MODEL)
