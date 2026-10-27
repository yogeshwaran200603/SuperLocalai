"""
Astra-Local Multi-Provider Base Interface
Defines common data structures and abstract base provider for LLM integrations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple


@dataclass
class ToolCall:
    """Represents a unified tool/function call across all providers."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMMessage:
    """Represents a conversational message in provider-neutral format."""
    role: str  # 'system', 'user', 'assistant' (or 'model'), 'tool'
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    raw_content: Any = None
    provider: Optional[str] = None


@dataclass
class LLMResponse:
    """Represents the response from an LLM invocation."""
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_response: Any = None
    raw_content: Any = None
    finish_reason: Optional[str] = None
    model_used: Optional[str] = None


class ProviderError(Exception):
    """Base exception for provider communication or operational errors."""
    pass


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is offline, unreachable, or timed out."""
    pass


class ProviderQuotaExhaustedError(ProviderError):
    """Raised when a provider has exhausted rate limits or daily quotas (HTTP 429)."""
    def __init__(self, message: str, retry_delay: str = "24 hours"):
        super().__init__(message)
        self.retry_delay = retry_delay


class InvalidToolCallError(ProviderError):
    """Raised when a model produces malformed or un-executable tool calls."""
    pass


class BaseProvider(ABC):
    """Abstract base class for all LLM providers in Astra-Local."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Callable]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        **kwargs
    ) -> LLMResponse:
        """
        Executes a chat completion turn with optional tool declarations.
        Returns a unified LLMResponse containing text and/or tool calls.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the provider is currently reachable and configured."""
        pass

    def list_models(self) -> List[str]:
        """Lists available models for this provider."""
        return []

    def health_check(self) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluates provider readiness.
        Returns: (is_healthy, status_message, fix_hint)
        """
        if self.is_available():
            return True, f"Online ({self.name})", None
        return False, f"Provider '{self.name}' is unavailable", f"Configure credentials or endpoints for {self.name}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}')>"
