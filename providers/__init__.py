"""
Astra-Local Providers Package
Unified LLM multi-provider architecture supporting Gemini, Ollama (local & cloud),
Groq, OpenRouter, and any OpenAI-compatible API with automatic failover on
429/503/timeout/schema errors.
"""

from typing import Dict, List, Optional
from config import (
    PROVIDER_ORDER,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_API_KEY,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    GROQ_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENAI_BASE_URL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from providers.base import (
    BaseProvider,
    ToolCall,
    LLMMessage,
    LLMResponse,
    ProviderError,
    ProviderUnavailableError,
    ProviderQuotaExhaustedError,
    InvalidToolCallError,
)
from providers.tool_converter import (
    func_to_schema,
    filter_tools_for_request,
    validate_tool_arguments,
)
from providers.gemini_provider import GeminiProvider
from providers.ollama_provider import OllamaProvider, check_ollama_status, auto_start_ollama
from providers.openai_compatible_provider import OpenAICompatibleProvider


def get_provider(name: str) -> BaseProvider:
    """Factory creating an instance of the requested provider by name."""
    norm = name.strip().lower()
    if norm == "gemini":
        return GeminiProvider()
    elif norm in ("ollama", "ollama_local"):
        return OllamaProvider(
            name="ollama_local",
            host=OLLAMA_HOST,
            model=OLLAMA_MODEL,
            api_key=OLLAMA_API_KEY if "ollama.com" in OLLAMA_HOST else None,
        )
    elif norm == "ollama_cloud":
        return OllamaProvider(
            name="ollama_cloud",
            host="https://ollama.com",
            model=OLLAMA_MODEL,
            api_key=OLLAMA_API_KEY,
        )
    elif norm == "groq":
        return OpenAICompatibleProvider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=GROQ_API_KEY,
            model=GROQ_MODEL or "llama-3.3-70b-versatile",
        )
    elif norm == "openrouter":
        return OpenAICompatibleProvider(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            model=OPENROUTER_MODEL or "meta-llama/llama-3.3-70b-instruct",
        )
    elif norm in ("openai", "openai_compatible"):
        return OpenAICompatibleProvider(
            name="openai_compatible",
            base_url=OPENAI_BASE_URL or "https://api.openai.com/v1",
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL or "gpt-4o-mini",
        )
    else:
        raise ValueError(
            f"Unknown provider: '{name}'. Supported providers: gemini, ollama_local, ollama_cloud, groq, openrouter, openai_compatible"
        )


def create_provider_chain(order: Optional[List[str]] = None) -> List[BaseProvider]:
    """Instantiates the ordered list of providers based on config or custom sequence."""
    chain_names = order or PROVIDER_ORDER
    providers: List[BaseProvider] = []
    for name in chain_names:
        try:
            p = get_provider(name)
            providers.append(p)
        except Exception:
            pass
    if not providers:
        # Default safety fallback
        providers = [GeminiProvider()]
    return providers


__all__ = [
    "BaseProvider",
    "ToolCall",
    "LLMMessage",
    "LLMResponse",
    "ProviderError",
    "ProviderUnavailableError",
    "ProviderQuotaExhaustedError",
    "InvalidToolCallError",
    "GeminiProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "get_provider",
    "create_provider_chain",
    "func_to_schema",
    "filter_tools_for_request",
    "validate_tool_arguments",
]
