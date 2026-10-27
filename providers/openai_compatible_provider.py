"""
Astra-Local OpenAI-Compatible Provider
Supports OpenAI-compatible APIs including Groq, OpenRouter, LocalAI, vLLM, and others.
Optimized for high-speed small/open models:
- Pre-configured presets for Groq (https://api.groq.com/openai/v1) and OpenRouter (https://openrouter.ai/api/v1)
- Intelligent keyword tool filtering capped at 12 tools
- Temperature 0.2
- Pre-execution tool argument JSON schema validation
- 2-strike fallback on invalid tool schemas
"""

import os
import sys
import json
import uuid
import requests
from typing import List, Dict, Any, Optional, Callable, Tuple

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENAI_BASE_URL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    get_small_model_system_prompt,
    mask_secret,
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


class OpenAICompatibleProvider(BaseProvider):
    """Provider for any OpenAI-compatible chat completions endpoint (Groq, OpenRouter, etc.)."""

    def __init__(
        self,
        name: str = "openai_compatible",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 45,
    ):
        super().__init__(name=name)
        self.timeout = timeout
        self.consecutive_invalid_tool_calls = 0

        # Configure presets according to name
        norm_name = name.lower()
        if norm_name == "groq":
            self.base_url = (base_url or "https://api.groq.com/openai/v1").rstrip("/")
            self.api_key = api_key or GROQ_API_KEY
            self.model = model or GROQ_MODEL or "llama-3.3-70b-versatile"
        elif norm_name == "openrouter":
            self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
            self.api_key = api_key or OPENROUTER_API_KEY
            self.model = model or OPENROUTER_MODEL or "meta-llama/llama-3.3-70b-instruct"
        else:
            self.base_url = (base_url or OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
            self.api_key = api_key or OPENAI_API_KEY
            self.model = model or OPENAI_MODEL or "gpt-4o-mini"

    def _get_headers(self) -> Dict[str, str]:
        """Builds HTTP headers including Bearer authorization."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "https://github.com/yogeshwaran/astra-local"
            headers["X-Title"] = "Superlocal Windows AI Assistant"
        return headers

    def is_available(self) -> bool:
        """Verifies if the provider has an API key and base URL configured."""
        return bool(self.api_key and self.base_url)

    def health_check(self) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluates provider readiness by sending a minimal test request.
        Returns: (is_healthy, status_message, fix_hint)
        """
        if not self.api_key:
            env_var = f"{self.name.upper()}_API_KEY"
            return False, f"{env_var} is not configured", f"Set {env_var} in .env"

        if not self.base_url:
            return False, f"base_url not configured for '{self.name}'", "Set base URL in config or .env"

        url = f"{self.base_url}/chat/completions"
        test_payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }

        try:
            resp = requests.post(url, headers=self._get_headers(), json=test_payload, timeout=5)
            if resp.status_code == 200:
                return True, f"Online (Model: {self.model})", None
            elif resp.status_code in (401, 403):
                return False, f"Authentication failed (HTTP {resp.status_code})", f"Verify {self.name.upper()}_API_KEY in .env"
            elif resp.status_code == 429:
                return False, f"Rate limited / Quota reached (HTTP 429)", "Wait for rate limit window or top up credits"
            else:
                err_text = resp.text[:120].strip()
                return False, f"HTTP {resp.status_code}: {err_text}", f"Check model '{self.model}' availability"
        except requests.exceptions.Timeout:
            return False, f"Connection timed out to {self.base_url}", "Check network or proxy settings"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot connect to {self.base_url}", "Verify base_url is reachable"
        except Exception as e:
            return False, f"Error: {str(e)}", "Check endpoint and key configuration"

    def list_models(self) -> List[str]:
        """Lists available models from the endpoint if supported."""
        models: List[str] = [self.model]
        try:
            resp = requests.get(f"{self.base_url}/models", headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    mid = item.get("id")
                    if mid and mid not in models:
                        models.append(mid)
        except Exception:
            pass
        return models

    def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Callable]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs
    ) -> LLMResponse:
        """
        Sends chat completion request to the OpenAI-compatible endpoint.
        Uses small-model optimizations: tool keyword filtering, schema validation, and 2-strike fallback.
        """
        if not self.is_available():
            raise ProviderUnavailableError(f"Provider '{self.name}' is missing API key or base URL.")

        # Extract last user query for tool keyword filtering
        last_query = ""
        for m in reversed(messages):
            if m.role == "user" and m.content:
                last_query = m.content
                break

        # Filter down to at most 12 tools
        active_tools = filter_tools_for_request(last_query, tools, max_tools=12) if tools else []
        tool_schemas = [func_to_schema(fn) for fn in active_tools]

        # Compact system prompt tailored for small/open models
        active_sys_prompt = system_prompt or get_small_model_system_prompt()

        # Build payload messages
        payload_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": active_sys_prompt}
        ]

        for m in messages:
            if m.role == "user":
                payload_messages.append({"role": "user", "content": m.content or ""})
            elif m.role in ("assistant", "model"):
                asst_msg: Dict[str, Any] = {"role": "assistant"}
                if m.content:
                    asst_msg["content"] = m.content
                if m.tool_calls:
                    asst_msg["tool_calls"] = [
                        {
                            "id": tc.id or str(uuid.uuid4()),
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                            }
                        }
                        for tc in m.tool_calls
                    ]
                payload_messages.append(asst_msg)
            elif m.role == "tool":
                payload_messages.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or "default_call",
                    "name": m.name or "action",
                    "content": json.dumps(m.content) if isinstance(m.content, (dict, list)) else str(m.content or ""),
                })

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
        }

        if tool_schemas:
            payload["tools"] = tool_schemas
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"

        try:
            resp = requests.post(url, headers=self._get_headers(), json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout:
            raise ProviderUnavailableError(f"Request to '{self.name}' timed out after {self.timeout}s.")
        except requests.exceptions.ConnectionError as ce:
            raise ProviderUnavailableError(f"Cannot connect to '{self.name}' at {self.base_url}: {ce}")
        except Exception as e:
            raise ProviderError(f"Network error communicating with '{self.name}': {e}")

        # Check HTTP response status
        if resp.status_code == 429:
            retry_header = resp.headers.get("Retry-After", "60")
            raise ProviderQuotaExhaustedError(
                f"Rate limit / quota exceeded (HTTP 429) for '{self.name}' ({self.model}).",
                retry_delay=f"{retry_header}s"
            )

        if resp.status_code in (500, 502, 503, 504):
            raise ProviderUnavailableError(f"Provider '{self.name}' returned HTTP {resp.status_code}: {resp.text[:120]}")

        if resp.status_code != 200:
            raise ProviderError(f"Provider '{self.name}' error (HTTP {resp.status_code}): {resp.text[:180]}")

        try:
            data = resp.json()
        except Exception as e:
            raise ProviderError(f"Invalid JSON returned by '{self.name}': {e}")

        choices = data.get("choices", [])
        if not choices:
            raise ProviderError(f"No completion choices returned by '{self.name}'.")

        choice = choices[0]
        choice_msg = choice.get("message", {})
        raw_text = choice_msg.get("content")
        raw_tool_calls = choice_msg.get("tool_calls", [])

        parsed_tool_calls: List[ToolCall] = []

        if raw_tool_calls:
            for rtc in raw_tool_calls:
                fn = rtc.get("function", {})
                call_id = rtc.get("id") or str(uuid.uuid4())
                call_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")

                has_json_error = False
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        has_json_error = True
                        self.consecutive_invalid_tool_calls += 1
                        if self.consecutive_invalid_tool_calls >= 2:
                            raise InvalidToolCallError(f"Model generated invalid JSON arguments twice for '{call_name}': {raw_args}")
                        parsed_args = {}
                elif isinstance(raw_args, dict):
                    parsed_args = raw_args
                else:
                    parsed_args = {}

                if not has_json_error:
                    # Validate arguments against tool schema
                    is_valid, validation_err = validate_tool_arguments(call_name, parsed_args)
                    if not is_valid:
                        self.consecutive_invalid_tool_calls += 1
                        if self.consecutive_invalid_tool_calls >= 2:
                            raise InvalidToolCallError(
                                f"Model failed tool schema validation twice on '{call_name}': {validation_err}"
                            )
                    else:
                        self.consecutive_invalid_tool_calls = 0

                parsed_tool_calls.append(ToolCall(id=call_id, name=call_name, arguments=parsed_args))

        return LLMResponse(
            text=raw_text,
            tool_calls=parsed_tool_calls,
            raw_response=data,
            model_used=self.model,
            finish_reason=choice.get("finish_reason"),
        )
