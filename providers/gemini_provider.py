"""
Astra-Local Gemini Provider
Integrates Google GenAI SDK (Gemini 3) with function calling,
call-ID enforcement, and automatic model chain failover on 429/503 errors.
"""

import re
import math
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path

from config import (
    GEMINI_API_KEY,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    MODEL_CHAIN,
    THINKING_LEVEL,
    QUOTA_PER_DAY,
    QUOTA_WARN_THRESHOLD,
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
)
from memory import MemoryManager


def _sanitize_json(obj: Any) -> Any:
    """Recursively converts numpy types, NaNs, paths, and complex structures to native JSON types."""
    if isinstance(obj, dict):
        return {str(k): _sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_sanitize_json(i) for i in obj]
    elif hasattr(obj, "item") and callable(getattr(obj, "item")):
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, Path):
        return str(obj)
    return obj


def extract_retry_delay(err: Exception) -> str:
    """Extracts human-readable retry delay from Gemini API 429 RetryInfo or error text."""
    err_str = str(err)
    m = re.search(r"retry\s+in\s+([0-9]+[hmsd][0-9a-zA-Z\.]*)", err_str, re.IGNORECASE)
    if m:
        return m.group(1).rstrip(".,;: ")

    m_sec = re.search(r"['\"]retryDelay['\"]\s*:\s*['\"]?([0-9]+)s?['\"]?", err_str)
    if m_sec:
        seconds = int(m_sec.group(1))
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {mins}m"
        elif mins > 0:
            return f"{mins} minutes"
        return f"{seconds} seconds"

    return "24 hours"


class GeminiProvider(BaseProvider):
    """Gemini 3 provider using google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_chain: Optional[List[str]] = None,
        primary_model: Optional[str] = None,
    ):
        super().__init__(name="gemini")
        self.api_key = api_key or GEMINI_API_KEY
        # Exclude computer-use / takeover models from normal text agent chain
        raw_chain = model_chain or list(MODEL_CHAIN)
        self.model_chain = [m for m in raw_chain if "computer-use" not in m.lower()]
        self.primary_model = primary_model or PRIMARY_MODEL
        if "computer-use" in self.primary_model.lower():
            self.primary_model = "gemini-3.8-flash"
        self.active_model = self.primary_model
        self.client = None
        self.memory = MemoryManager()
        self.conversation_contents: List[Any] = []
        self.last_function_calls: List[ToolCall] = []
        self._init_client()

    def reset_conversation(self):
        """Resets native Gemini conversation contents."""
        self.conversation_contents.clear()
        self.last_function_calls.clear()

    def health_check(self) -> Tuple[bool, str, Optional[str]]:
        """Checks Gemini API key, SDK client, and model availability. (Counter warns, never blocks)."""
        if not self.api_key:
            return False, "GEMINI_API_KEY is not configured", "Set GEMINI_API_KEY in .env"
        if not self.client:
            return False, "Google GenAI SDK failed to initialize", "Check python google-genai SDK installation"

        # Check candidate models to see if active model or next in chain has lower calls
        candidate_pool = [self.active_model]
        for m in self.model_chain:
            if m not in candidate_pool:
                candidate_pool.append(m)

        for m in candidate_pool:
            if self.memory.get_daily_api_calls(m) < QUOTA_WARN_THRESHOLD:
                self.active_model = m
                break

        calls_today = self.memory.get_daily_api_calls(self.active_model)
        status_detail = f"Online (Model: {self.active_model})"
        if calls_today >= QUOTA_WARN_THRESHOLD:
            status_detail += f" [Used {calls_today} calls today]"

        if hasattr(self.client, "models") and "mock" in type(self.client).__name__.lower():
            return True, f"Online (Mocked, Model: {self.active_model})", None

        return True, status_detail, None

    def _init_client(self):
        """Initializes the google-genai Client with 60s timeout."""
        if not self.api_key:
            return
        try:
            from google import genai
            from google.genai import types
            http_opts = types.HttpOptions(
                timeout=60000,
                retry_options=types.HttpRetryOptions(attempts=1)
            )
            self.client = genai.Client(api_key=self.api_key, http_options=http_opts)
        except Exception:
            self.client = None

    def is_available(self) -> bool:
        """Checks if API key is configured and SDK client is loaded."""
        return bool(self.api_key and self.client is not None)

    def list_models(self) -> List[str]:
        """Returns the configured Gemini model fallback chain."""
        return list(self.model_chain)

    def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Callable]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        **kwargs
    ) -> LLMResponse:
        """Sends chat request to Gemini with model chain fallback and Gemini 3 call-ID rules."""
        if not self.is_available():
            raise ProviderUnavailableError("Gemini provider is not available. Please verify GEMINI_API_KEY in .env.")

        from google.genai import types

        # Build thinking config defensibly
        thinking_cfg = None
        if THINKING_LEVEL in ("low", "medium", "high"):
            try:
                budget_map = {"low": 256, "medium": 512, "high": 1024}
                budget = budget_map.get(THINKING_LEVEL, 256)
                thinking_cfg = types.ThinkingConfig(thinking_budget=budget)
            except Exception:
                thinking_cfg = None

        config_kwargs: Dict[str, Any] = {
            "temperature": temperature,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        if tools:
            config_kwargs["tools"] = tools
        if thinking_cfg:
            config_kwargs["thinking_config"] = thinking_cfg

        gen_config = types.GenerateContentConfig(**config_kwargs)

        # Check if continuing an existing Gemini multi-turn session
        is_continuing_gemini = (
            bool(self.conversation_contents)
            and len(self.conversation_contents) > 0
            and getattr(self.conversation_contents[-1], "role", "") == "model"
            and bool(self.last_function_calls)
            and any(m.role == "tool" for m in messages[-len(self.last_function_calls):])
        )

        if is_continuing_gemini:
            # Construct a SINGLE user turn containing one function_response part per tool call
            # matching each call's id and name
            function_response_parts: List[types.Part] = []
            for tc in self.last_function_calls:
                matching_msg = next((m for m in reversed(messages) if m.role == "tool" and (m.tool_call_id == tc.id or m.name == tc.name)), None)
                res_content = matching_msg.content if matching_msg else {"result": "ok"}
                clean_res = _sanitize_json(res_content if isinstance(res_content, (dict, list)) else {"result": str(res_content)})
                f_resp_kwargs: Dict[str, Any] = {
                    "name": tc.name,
                    "response": {"result": clean_res}
                }
                if tc.id:
                    f_resp_kwargs["id"] = tc.id

                try:
                    f_resp = types.FunctionResponse(**f_resp_kwargs)
                    function_response_parts.append(types.Part(function_response=f_resp))
                except Exception:
                    function_response_parts.append(types.Part.from_function_response(name=tc.name, response={"result": clean_res}))

            # Send function responses as a single user turn with one function_response part per call
            if function_response_parts:
                self.conversation_contents.append(types.Content(role="user", parts=function_response_parts))

        else:
            # First turn or switched from another provider:
            # Convert history to plain text summaries of tool calls and results.
            # Never send another provider's raw parts or mixed thought_signatures to Gemini!
            self.conversation_contents = []
            for msg in messages:
                if msg.role == "user":
                    if msg.content:
                        self.conversation_contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg.content)]))
                elif msg.role in ("assistant", "model"):
                    if msg.tool_calls:
                        tool_desc = ", ".join(f"{tc.name}({tc.arguments})" for tc in msg.tool_calls)
                        txt = f"Action: Called tools: {tool_desc}"
                        if msg.content:
                            txt = f"{msg.content}\n{txt}"
                        self.conversation_contents.append(types.Content(role="model", parts=[types.Part.from_text(text=txt)]))
                    elif msg.content:
                        self.conversation_contents.append(types.Content(role="model", parts=[types.Part.from_text(text=msg.content)]))
                elif msg.role == "tool":
                    res_txt = f"Tool '{msg.name or 'action'}' output: {msg.content}"
                    self.conversation_contents.append(types.Content(role="user", parts=[types.Part.from_text(text=res_txt)]))

        contents = self.conversation_contents

        # Model candidates from chain
        candidate_pool = [m for m in self.model_chain if m]
        if self.active_model and self.active_model not in candidate_pool:
            candidate_pool.insert(0, self.active_model)

        last_retry_delay = "24 hours"
        response = None

        for candidate_model in candidate_pool:
            # 3 retries with backoff on 503/504 only
            for attempt in range(3):
                try:
                    response = self.client.models.generate_content(
                        model=candidate_model,
                        contents=contents,
                        config=gen_config,
                    )
                    self.active_model = candidate_model
                    self.memory.record_api_call(candidate_model)
                    break
                except Exception as api_err:
                    err_str = str(api_err).lower()
                    if any(term in err_str for term in ("503", "504", "unavailable", "high demand")):
                        if attempt < 2:
                            time.sleep(1.0 * (2 ** attempt))
                            continue
                        else:
                            break
                    elif any(term in err_str for term in ("429", "resource_exhausted", "quota")):
                        last_retry_delay = extract_retry_delay(api_err)
                        break
                    else:
                        raise ProviderError(f"Gemini API error ({candidate_model}): {api_err}")

            if response is not None:
                break

        if not response:
            raise ProviderQuotaExhaustedError(
                f"All Gemini models in chain exhausted. Quota resets in {last_retry_delay}.",
                retry_delay=last_retry_delay
            )

        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content or not candidate.content.parts:
            return LLMResponse(text="", tool_calls=[], raw_response=response, model_used=self.active_model)

        # CRITICAL (BUG 1 FIX):
        # Append the model's ORIGINAL response content object (response.candidates[0].content,
        # with all its parts and thought_signatures) directly to the conversation history.
        # Do not rebuild or copy function call parts by hand, since that drops thought_signature!
        self.conversation_contents.append(candidate.content)

        text_parts = [p.text for p in candidate.content.parts if isinstance(getattr(p, "text", None), str) and getattr(p, "thought", None) is not True]
        fc_parts = [p.function_call for p in candidate.content.parts if p.function_call]

        tool_calls: List[ToolCall] = []
        for idx, fc in enumerate(fc_parts):
            call_id = getattr(fc, "id", None) or f"gemini_call_{idx}"
            tool_calls.append(ToolCall(
                id=call_id,
                name=fc.name,
                arguments=dict(fc.args) if fc.args else {}
            ))

        self.last_function_calls = tool_calls

        return LLMResponse(
            text="\n".join(text_parts).strip() if text_parts else None,
            tool_calls=tool_calls,
            raw_response=response,
            raw_content=candidate.content,
            model_used=self.active_model
        )
