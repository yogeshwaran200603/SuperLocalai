"""
Astra-Local Ollama Provider
Supports local (http://localhost:11434) and cloud (https://ollama.com) deployments.
Optimized for smaller models (e.g. Qwen, Llama):
- Compact system prompt
- Intelligent keyword tool filtering capped at 12 tools
- Temperature 0.2
- Pre-execution tool argument JSON schema validation
- 2-strike fallback on invalid tool schemas
"""

import os
import sys
import time
import json
import uuid
import shutil
import requests
import subprocess
from typing import List, Dict, Any, Optional, Callable, Tuple

from config import (
    OLLAMA_MODEL,
    OLLAMA_HOST,
    OLLAMA_API_KEY,
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
    InvalidToolCallError,
)
from providers.tool_converter import (
    func_to_schema,
    filter_tools_for_request,
    validate_tool_arguments,
)


def check_ollama_status(host: str, model: str, timeout: float = 0.5) -> Tuple[bool, bool, List[str]]:
    """
    Checks if Ollama is reachable and if the specified model is installed.
    Returns: (is_reachable, model_exists, list_of_models)
    """
    clean_host = host.rstrip("/")
    try:
        resp = requests.get(f"{clean_host}/api/tags", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            models: List[str] = []
            for m in data.get("models", []):
                name = m.get("name") or m.get("model")
                if name:
                    models.append(name)
            
            if not model:
                return True, True, models

            # Check matching model name or base tag
            model_base = model.split(":")[0].lower() if ":" in model else model.lower()
            model_exists = any(
                model.lower() in m.lower()
                or m.lower().startswith(model_base)
                or model_base in m.lower()
                for m in models
            )
            return True, model_exists, models
    except Exception:
        pass
    return False, False, []


def auto_start_ollama(host: str, wait_seconds: int = 10) -> bool:
    """
    Attempts to start 'ollama serve' in background if host is localhost and not running.
    Waits up to wait_seconds for Ollama to become reachable.
    """
    is_localhost = any(h in host.lower() for h in ("localhost", "127.0.0.1", "0.0.0.0"))
    if not is_localhost:
        return False

    reachable, _, _ = check_ollama_status(host, "", timeout=0.5)
    if reachable:
        return True

    try:
        creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )
    except Exception:
        return False

    # Wait up to wait_seconds
    start_time = time.time()
    while time.time() - start_time < wait_seconds:
        time.sleep(0.5)
        reachable, _, _ = check_ollama_status(host, "", timeout=0.5)
        if reachable:
            return True

    return False


class OllamaProvider(BaseProvider):
    """Ollama provider supporting local and cloud instances."""

    def __init__(
        self,
        name: str = "ollama_local",
        model: Optional[str] = None,
        host: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 45,
    ):
        super().__init__(name=name)
        self.model = model or OLLAMA_MODEL
        self.host = (host or OLLAMA_HOST).rstrip("/")
        self.api_key = api_key or OLLAMA_API_KEY
        self.timeout = timeout
        self.consecutive_invalid_tool_calls = 0

    def _get_headers(self) -> Dict[str, str]:
        """Builds HTTP request headers, sending Bearer token if API key is provided."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def is_available(self) -> bool:
        """Verifies if the Ollama endpoint is reachable."""
        reachable, _, _ = check_ollama_status(self.host, "", timeout=2.0)
        return reachable

    def health_check(self, auto_start: bool = False) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluates Ollama readiness.
        If auto_start is True and host is localhost, tries starting 'ollama serve' if down.
        Returns: (is_healthy, status_message, fix_hint)
        """
        reachable, model_exists, models = check_ollama_status(self.host, self.model)
        if not reachable and auto_start:
            auto_start_ollama(self.host, wait_seconds=10)
            reachable, model_exists, models = check_ollama_status(self.host, self.model)

        if not reachable:
            return False, f"Unreachable at {self.host}", f"Run 'ollama serve' and 'ollama pull {self.model}'"
        if not model_exists:
            return False, f"Model '{self.model}' not found at {self.host}", f"Run 'ollama pull {self.model}'"
        return True, f"Online (Model: {self.model})", None

    def list_models(self) -> List[str]:
        """Lists installed or available models via Ollama API or CLI."""
        models: List[str] = []
        try:
            resp = requests.get(
                f"{self.host}/api/tags",
                headers=self._get_headers(),
                timeout=3.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("models", []):
                    name = m.get("name") or m.get("model")
                    if name:
                        models.append(name)
        except Exception:
            pass

        if not models:
            # Fallback to local CLI if installed
            try:
                proc = subprocess.run(
                    ["ollama", "list"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if proc.returncode == 0:
                    lines = proc.stdout.strip().split("\n")
                    for line in lines[1:]:  # skip header
                        parts = line.split()
                        if parts:
                            models.append(parts[0])
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
        Executes a chat request against Ollama /api/chat.
        Implements small-model optimizations:
        - Shorter system prompt
        - Capped at 12 keyword-filtered tools
        - Temperature 0.2
        - JSON schema validation of tool arguments
        """
        # Determine latest user query for keyword tool filtering
        latest_query = ""
        for m in reversed(messages):
            if m.role == "user" and m.content:
                latest_query = m.content
                break

        # Filter to at most 12 relevant tools
        filtered_tools = filter_tools_for_request(latest_query, all_tools=tools, max_tools=12)
        tool_schemas = [func_to_schema(f) for f in filtered_tools] if filtered_tools else []

        # System prompt: use concise small-model prompt
        sys_instruction = system_prompt or get_small_model_system_prompt()

        # Build payload messages
        payload_messages: List[Dict[str, Any]] = []
        if sys_instruction:
            payload_messages.append({"role": "system", "content": sys_instruction})

        for msg in messages:
            role = "assistant" if msg.role in ("assistant", "model") else msg.role
            msg_dict: Dict[str, Any] = {"role": role, "content": msg.content or ""}

            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]

            if msg.role == "tool":
                msg_dict["role"] = "tool"
                msg_dict["content"] = json.dumps(msg.content) if isinstance(msg.content, (dict, list)) else str(msg.content or "")
                if msg.name:
                    msg_dict["name"] = msg.name

            payload_messages.append(msg_dict)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }

        if tool_schemas:
            payload["tools"] = tool_schemas

        # Send request to Ollama endpoint
        url = f"{self.host}/api/chat"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            raise ProviderUnavailableError(f"Ollama request timed out after {self.timeout}s at {self.host}.")
        except requests.exceptions.ConnectionError:
            raise ProviderUnavailableError(f"Could not connect to Ollama at {self.host}. Is Ollama running?")
        except Exception as e:
            raise ProviderError(f"Ollama communication error: {str(e)}")

        if resp.status_code == 429:
            raise ProviderError(f"Ollama rate limit exceeded (429) at {self.host}.")
        if resp.status_code in (503, 504):
            raise ProviderUnavailableError(f"Ollama service unavailable ({resp.status_code}) at {self.host}.")
        if resp.status_code != 200:
            raise ProviderError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except Exception as e:
            raise ProviderError(f"Failed to parse Ollama JSON response: {str(e)}")

        resp_msg = data.get("message", {})
        raw_text = resp_msg.get("content", "")
        raw_tool_calls = resp_msg.get("tool_calls", [])

        # Parse tool calls
        parsed_tool_calls: List[ToolCall] = []

        for idx, tc in enumerate(raw_tool_calls):
            fn = tc.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})

            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {"raw_input": raw_args}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}

            call_id = tc.get("id") or f"ollama_call_{idx}_{uuid.uuid4().hex[:6]}"
            parsed_tool_calls.append(ToolCall(id=call_id, name=name, arguments=args))

        # Fallback for models that output tool JSON inside text content
        if not parsed_tool_calls and raw_text and ("```json" in raw_text or '{"name":' in raw_text):
            try:
                candidate_json = raw_text
                if "```json" in candidate_json:
                    candidate_json = candidate_json.split("```json")[1].split("```")[0].strip()
                elif "```" in candidate_json:
                    candidate_json = candidate_json.split("```")[1].split("```")[0].strip()
                parsed = json.loads(candidate_json)
                if isinstance(parsed, dict) and "name" in parsed:
                    name = parsed["name"]
                    args = parsed.get("arguments") or parsed.get("parameters", {})
                    parsed_tool_calls.append(ToolCall(id=f"ollama_text_{uuid.uuid4().hex[:6]}", name=name, arguments=args))
                elif isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "name" in item:
                            parsed_tool_calls.append(ToolCall(
                                id=f"ollama_text_{uuid.uuid4().hex[:6]}",
                                name=item["name"],
                                arguments=item.get("arguments") or item.get("parameters", {})
                            ))
            except Exception:
                pass

        # Validate tool arguments against schema
        for tc in parsed_tool_calls:
            is_valid, reason = validate_tool_arguments(tc.name, tc.arguments)
            if not is_valid:
                self.consecutive_invalid_tool_calls += 1
                if self.consecutive_invalid_tool_calls >= 2:
                    raise InvalidToolCallError(
                        f"Ollama model '{self.model}' produced invalid tool arguments twice consecutively: {reason}"
                    )
            else:
                self.consecutive_invalid_tool_calls = 0

        return LLMResponse(
            text=raw_text.strip() if raw_text else None,
            tool_calls=parsed_tool_calls,
            raw_response=data,
            model_used=self.model,
        )
