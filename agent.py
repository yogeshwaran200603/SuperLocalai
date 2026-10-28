"""
Astra-Local Agent Core
Implements the Gemini 3 agent loop with function calling, max 15 steps,
safety confirmation checks, retry logic, and SQLite memory persistence.
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.markup import escape

from config import (
    GEMINI_API_KEY,
    MODEL_NAME,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    MODEL_CHAIN,
    PROVIDER_ORDER,
    QUOTA_PER_DAY,
    CACHE_TTL_SECONDS,
    THINKING_LEVEL,
    MAX_STEPS,
    DESKTOP_DIR,
    DOCUMENTS_DIR,
    DOWNLOADS_DIR,
    WORKSPACE_DIR,
    load_shortcuts,
    get_system_prompt,
    get_small_model_system_prompt,
)
from providers import (
    BaseProvider,
    ToolCall,
    LLMMessage,
    LLMResponse,
    GeminiProvider,
    OllamaProvider,
    get_provider,
    create_provider_chain,
    ProviderError,
    ProviderUnavailableError,
    ProviderQuotaExhaustedError,
    InvalidToolCallError,
    validate_tool_arguments,
)
from safety import (
    confirm_action,
    log_action,
    is_emergency_stopped,
    reset_emergency_stop,
    start_emergency_stop_listener,
    reset_desktop_session,
)
from tools.desktop import reset_desktop_action_count, reset_verification_failures
from memory import MemoryManager
from tools import (
    TOOL_REGISTRY,
    run_powershell,
    open_url,
    open_app,
    browser_goto,
    browser_click,
    browser_type,
    browser_press,
    browser_read_text,
    browser_screenshot,
    browser_wait_for,
    whatsapp_send,
    desktop_screenshot,
    desktop_click,
    desktop_type,
    desktop_hotkey,
    desktop_locate_element,
    file_read,
    file_write,
    file_list,
    file_move,
    file_delete,
    run_python,
    data_inspect,
    data_clean,
    data_chart,
    data_train_model,
    doc_create_pptx,
    doc_create_docx,
    doc_create_xlsx,
    doc_create_pdf,
    scaffold_project,
    run_tests,
    fix_and_rerun,
    test_website,
)

console = Console()

# Complete list of callable tools exposed to Gemini
AGENT_TOOLS = [
    run_powershell,
    open_url,
    open_app,
    browser_goto,
    browser_click,
    browser_type,
    browser_press,
    browser_read_text,
    browser_screenshot,
    browser_wait_for,
    whatsapp_send,
    desktop_screenshot,
    desktop_click,
    desktop_type,
    desktop_hotkey,
    desktop_locate_element,
    file_read,
    file_write,
    file_list,
    file_move,
    file_delete,
    run_python,
    data_inspect,
    data_clean,
    data_chart,
    data_train_model,
    doc_create_pptx,
    doc_create_docx,
    doc_create_xlsx,
    doc_create_pdf,
    scaffold_project,
    run_tests,
    fix_and_rerun,
    test_website,
]


import math


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


# ==============================================================================
# Local-First Execution, Quota Helpers & Summary Builder
# ==============================================================================

def extract_retry_delay(err: Exception) -> str:
    """Extracts human-readable retry delay from Gemini API 429 RetryInfo or error text."""
    err_str = str(err)
    # Check for "retry in <time>"
    m = re.search(r"retry\s+in\s+([0-9]+[hmsd][0-9a-zA-Z\.]*)", err_str, re.IGNORECASE)
    if m:
        return m.group(1).rstrip(".,;: ")

    # Check for retryDelay in seconds e.g. 'retryDelay': '58016s'
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


def is_read_only_prompt(prompt: str) -> bool:
    """Checks if prompt is a query or inspection that does not mutate files/system."""
    p = prompt.strip().lower()
    read_only_starters = ("find ", "list ", "show ", "check ", "what ", "inspect ", "get ", "display ", "count ", "how ", "where ")
    mutation_terms = ("create", "make", "delete", "write", "send", "click", "type", "drag", "remove", "drop", "kill", "format", "scaffold", "install")
    if any(m in p for m in mutation_terms):
        return False
    return any(p.startswith(s) for s in read_only_starters)


def sanitize_messages_for_provider_switch(messages: List[LLMMessage]) -> List[LLMMessage]:
    """
    Converts conversation history to plain text summaries of tool calls and results.
    Ensures that when switching providers mid-task, one provider's raw parts,
    candidate objects, or thought_signatures are never sent to another provider.
    """
    clean_msgs: List[LLMMessage] = []
    for m in messages:
        if m.role == "user":
            clean_msgs.append(LLMMessage(role="user", content=m.content or ""))
        elif m.role in ("assistant", "model"):
            txt = m.content or ""
            if m.tool_calls:
                call_strs = [f"{tc.name}({json.dumps(tc.arguments)})" for tc in m.tool_calls]
                call_desc = f"Action: Called tools: {', '.join(call_strs)}"
                txt = f"{txt}\n{call_desc}".strip()
            clean_msgs.append(LLMMessage(role="assistant", content=txt))
        elif m.role == "tool":
            res_content = m.content
            if isinstance(res_content, (dict, list)):
                res_str = json.dumps(res_content)
            else:
                res_str = str(res_content or "")
            clean_msgs.append(LLMMessage(
                role="user",
                content=f"Tool '{m.name or 'action'}' result: {res_str}"
            ))
    return clean_msgs


def try_local_first_execution(prompt: str) -> Optional[str]:
    """
    Attempts to fulfill the user request locally using shortcuts.json and simple system rules.
    Consumes ZERO Gemini API calls!
    """
    p = re.sub(r'^[\\\'"\s]+|[\\\'"\s]+$', '', prompt).strip()
    p_lower = p.lower()

    # Slash commands handled locally with 0 model calls
    if p_lower.startswith("/"):
        if p_lower in ("/help", "help"):
            return "Command handled locally: Use /help for the commands menu."
        if p_lower in ("/shortcuts", "shortcuts"):
            return "Command handled locally: Use /shortcuts to view configured shortcuts."
        if p_lower == "/new":
            return "Command handled locally: Fresh session initialized."
        if p_lower == "/sessions":
            return "Command handled locally: Showing recent sessions."
        if p_lower == "/health":
            return "Command handled locally: Provider health status checked."
        if p_lower.startswith("/quota"):
            if "reset" in p_lower:
                MemoryManager().reset_daily_usage()
                return "Daily quota usage counter has been reset to 0 in SQLite memory."
            total = MemoryManager().get_daily_api_calls()
            return f"Current daily requests logged: {total}."
        if p_lower.startswith("/provider"):
            return "Provider status displayed locally."
        if p_lower == "/models":
            return "Local models listed locally."
        if p_lower.startswith("/voice"):
            return "Voice command handled locally: Use /voice on|off|live|test|devices."
        if p_lower.startswith("/auto") or p_lower in ("/jobs", "jobs") or p_lower.startswith("/jobs"):
            from autopilot import run_autopilot, undo_last_step, list_jobs_summary, get_active_job_status
            if p_lower == "/auto status":
                st = get_active_job_status()
                return f"Active Job: {st['id']} ({st['status']}) - Step {st['current_step']}/{st['total_steps']}" if st else "No active autopilot job found."
            if p_lower == "/auto undo":
                return undo_last_step()
            if p_lower in ("/jobs", "jobs") or p_lower.startswith("/jobs"):
                past = list_jobs_summary(5)
                return f"Found {len(past)} recent autopilot jobs."
            is_dry = "--dry" in p_lower or "-d" in p_lower
            goal = re.sub(r"^/auto\s*(?:--dry|-d)?\s*", "", p, flags=re.IGNORECASE).strip()
            if goal:
                job = run_autopilot(goal, dry_run=is_dry)
                return f"Autopilot {'plan generated' if is_dry else 'completed'}: {job.id} ({len(job.steps)} steps)"
        if p_lower.startswith("/computer"):
            from computer import run_computer_mode
            res = run_computer_mode(p)
            return res.get("summary", "Computer Mode completed.")
        if p_lower.startswith("/poki"):
            from poki import handle_poki_command
            return handle_poki_command(p)
        if p_lower.startswith("/optimize"):
            from optimizer import handle_optimizer_command
            return handle_optimizer_command(p)

    if p_lower.startswith("@computer"):
        from computer import run_computer_mode
        res = run_computer_mode(p)
        return res.get("summary", "Computer Mode completed.")
    if p_lower.startswith("@poki"):
        from poki import handle_poki_command
        return handle_poki_command(p)
    if p_lower.startswith("@optimize"):
        from optimizer import handle_optimizer_command
        return handle_optimizer_command(p.replace("@optimize", "/optimize"))

    # Natural Language Emergency Stop Fast Path
    if p_lower in ("stop", "/stop", "emergency stop", "quit game", "stop game", "stop playing"):
        from safety import trigger_emergency_stop
        trigger_emergency_stop("Stopped by user command 'stop'")
        return "Emergency stop signal triggered. Active game or automation stopped."

    # Natural Language Poki Game Fast Path (Zero model calls)
    # Intercepts: "play <game>", "play the game", "play cricket", "can you play <game>", "play"
    poki_play_match = re.search(
        r"^(?:can\s+you\s+|could\s+you\s+|please\s+)?(?:start\s+)?play(?:ing)?(?:\s+(?:the\s+)?game)?(?:\s+(.*))?$",
        p_lower
    )
    if poki_play_match:
        target_game = (poki_play_match.group(1) or "").strip()
        target_game = re.sub(r"^(?:on\s+poki|in\s+poki|poki)\s*", "", target_game).strip()
        from poki import handle_poki_command
        if target_game:
            return handle_poki_command(f"/poki play {target_game}")
        else:
            return handle_poki_command("/poki play")

    # Natural Language PC Optimizer Fast Path
    if any(trigger in p_lower for trigger in ("why is my pc slow", "why is pc slow", "pc is slow", "computer is slow", "optimize my pc", "clean my pc", "pc optimizer")):
        from optimizer import handle_optimizer_command
        return handle_optimizer_command("/optimize scan")

    shortcuts = load_shortcuts()
    apps = shortcuts.get("apps", {})
    websites = shortcuts.get("websites", {})
    discord_servers = shortcuts.get("discord_servers", {})
    paths = shortcuts.get("paths", {})

    # 0. Direct app / command prompt launch without 'open'
    direct_system_apps = {
        "cmd": "cmd",
        "cmd prompt": "cmd",
        "command prompt": "cmd",
        "cmd.exe": "cmd",
        "terminal": "cmd",
        "windows terminal": "wt",
        "wt": "wt",
        "powershell": "powershell",
        "notepad": "notepad",
        "calc": "calc",
        "calculator": "calc",
        "explorer": "explorer",
        "file explorer": "explorer",
        "task manager": "taskmgr",
        "taskmgr": "taskmgr",
    }
    if p_lower in direct_system_apps:
        app_target = direct_system_apps[p_lower]
        open_app(app_target)
        return f"Launched application '{p}' locally."

    # 1. 'go to <discord server>' or 'open discord and go to <server>'
    m_discord = re.search(r"(?:open discord\s+(?:and\s+)?go to|go to\s+discord server|go to)\s+(.+)", p_lower)
    if m_discord:
        target = m_discord.group(1).strip().strip("'\"")
        for sname, sval in discord_servers.items():
            if sname.lower() in target or target in sname.lower():
                res = open_app(sname)
                return f"Opened Discord server '{sname}' locally via deep link: {res.get('deep_link', sval)}"

    # 2. 'open <name>'
    if p_lower.startswith("open "):
        target = p[5:].strip().strip("'\"")
        target_lower = target.lower()

        # Check Discord servers
        for sname, sval in discord_servers.items():
            if sname.lower() in target_lower or target_lower in sname.lower():
                res = open_app(sname)
                return f"Opened Discord server '{sname}' locally: {res.get('deep_link', sval)}"

        # Check folders
        folder_map = {
            "desktop": DESKTOP_DIR,
            "downloads": DOWNLOADS_DIR,
            "documents": DOCUMENTS_DIR,
            "workspace": WORKSPACE_DIR,
        }
        clean_target = re.sub(r"^(?:the\s+)?(?:folder\s+)?", "", target_lower).strip()
        clean_target = re.sub(r"\s+folder$", "", clean_target).strip()

        if clean_target in folder_map:
            fpath = folder_map[clean_target]
            run_powershell(f'Start-Process explorer "{fpath}"')
            return f"Opened {clean_target.capitalize()} folder in File Explorer: {fpath}"

        for pname, pval in paths.items():
            if clean_target == pname.lower():
                run_powershell(f'Start-Process explorer "{pval}"')
                return f"Opened folder '{pname}' in File Explorer: {pval}"

        # Check websites in shortcuts
        for wname, wurl in websites.items():
            if clean_target == wname.lower():
                open_url(wurl)
                return f"Opened website '{wname}' locally: {wurl}"

        # Check generic website or URL
        if clean_target.startswith(("http://", "https://", "www.")) or (("." in clean_target) and not clean_target.endswith((".exe", ".txt", ".bat", ".cmd", ".ps1"))):
            url = clean_target if clean_target.startswith("http") else f"https://{clean_target}"
            open_url(url)
            return f"Opened website locally: {url}"

        # Check apps in shortcuts
        for aname, aval in apps.items():
            if clean_target == aname.lower():
                open_app(aval)
                return f"Opened application '{aname}' locally: {aval}"

        # Check common built-in system applications
        system_apps = {
            "notepad": "notepad",
            "calc": "calc",
            "calculator": "calc",
            "explorer": "explorer",
            "file explorer": "explorer",
            "code": "code",
            "vs code": "code",
            "vscode": "code",
            "cmd": "cmd",
            "cmd prompt": "cmd",
            "command prompt": "cmd",
            "cmd.exe": "cmd",
            "terminal": "cmd",
            "windows terminal": "wt",
            "wt": "wt",
            "powershell": "powershell",
            "paint": "mspaint",
            "task manager": "taskmgr",
            "taskmgr": "taskmgr",
            "control panel": "control",
        }
        if clean_target in system_apps:
            app_target = system_apps[clean_target]
            open_app(app_target)
            return f"Launched application '{clean_target}' locally."

    return None


def build_local_summary(executed_tools: List[Dict[str, Any]]) -> str:
    """Builds a clear, concise summary locally from tool execution results without making extra Gemini API calls."""
    if not executed_tools:
        return "Task completed."

    if len(executed_tools) == 1:
        item = executed_tools[0]
        name = item["name"]
        res = item.get("result", {})
        if isinstance(res, dict):
            msg = res.get("message") or res.get("stdout") or res.get("error") or str(res)
        else:
            msg = str(res)
        return f"Completed `{name}`: {msg.strip()}"

    lines = ["**Completed Actions:**"]
    for idx, item in enumerate(executed_tools, 1):
        name = item["name"]
        res = item.get("result", {})
        if isinstance(res, dict):
            detail = res.get("message") or res.get("stdout") or res.get("error") or str(res)
        else:
            detail = str(res)
        detail_clean = detail.strip().split("\n")[0][:120]
        lines.append(f"{idx}. `{name}`: {detail_clean}")
    return "\n".join(lines)


class AstraAgent:
    def __init__(
        self,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
        memory: Optional[MemoryManager] = None,
    ):
        self.memory = memory or MemoryManager()
        self.session_id = session_id or self.memory.create_session("Superlocal Interactive")
        
        # Initialize multi-provider chain
        self.provider_chain: List[BaseProvider] = create_provider_chain()
        self._gemini_provider = next((p for p in self.provider_chain if isinstance(p, GeminiProvider)), None)
        if not self._gemini_provider:
            self._gemini_provider = GeminiProvider()

        if provider:
            self.active_provider = get_provider(provider)
        else:
            self.active_provider = self.provider_chain[0] if self.provider_chain else self._gemini_provider

        self._client = getattr(self._gemini_provider, "client", None)
        self._active_model = getattr(self.active_provider, "active_model", getattr(self.active_provider, "model", MODEL_NAME))
        start_emergency_stop_listener()

    @property
    def client(self):
        if hasattr(self, "_gemini_provider") and self._gemini_provider:
            return self._gemini_provider.client
        return getattr(self, "_client", None)

    @client.setter
    def client(self, value):
        self._client = value
        if hasattr(self, "_gemini_provider") and self._gemini_provider:
            self._gemini_provider.client = value
            # If client was explicitly mocked, prioritize Gemini
            if hasattr(value, "models"):
                self.active_provider = self._gemini_provider

    @property
    def active_model(self):
        if hasattr(self, "active_provider") and self.active_provider:
            if hasattr(self.active_provider, "active_model"):
                return self.active_provider.active_model
            if hasattr(self.active_provider, "model"):
                return self.active_provider.model
        return getattr(self, "_active_model", PRIMARY_MODEL)

    @active_model.setter
    def active_model(self, value):
        self._active_model = value
        if hasattr(self, "active_provider") and self.active_provider:
            if hasattr(self.active_provider, "active_model"):
                self.active_provider.active_model = value
            elif hasattr(self.active_provider, "model"):
                self.active_provider.model = value

    def set_provider(self, provider_name: str) -> BaseProvider:
        """Switches active provider to the specified provider name."""
        new_provider = get_provider(provider_name)
        self.active_provider = new_provider
        if isinstance(new_provider, GeminiProvider):
            self._gemini_provider = new_provider
            if self._client:
                new_provider.client = self._client
        return new_provider

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates, seeks safety confirmation, executes a tool, and returns the result.
        """
        if is_emergency_stopped():
            return {
                "success": False,
                "status": "EMERGENCY_STOPPED",
                "error": "Execution cancelled: Emergency stop (Ctrl+Alt+Q) is active."
            }

        if tool_name not in TOOL_REGISTRY:
            return {"error": f"Tool '{tool_name}' not found."}

        func = TOOL_REGISTRY[tool_name]

        # 1. Ask user confirmation through safety module
        allowed = confirm_action(tool_name, args)
        if not allowed:
            res = {
                "success": False,
                "status": "USER_DENIED",
                "message": f"Action {tool_name} was cancelled by user."
            }
            self.memory.record_tool_execution(self.session_id, tool_name, args, res, "DENIED")
            return res

        # 2. Execute tool
        try:
            console.print(f"[dim]Running {tool_name}...[/dim]")
            result = func(**args)
            self.memory.record_tool_execution(self.session_id, tool_name, args, result, "SUCCESS")
            return result
        except Exception as e:
            err_res = {"success": False, "error": str(e)}
            self.memory.record_tool_execution(self.session_id, tool_name, args, err_res, "ERROR")
            log_action(tool_name, args, "ERROR", str(e))
            return err_res

    def run(self, user_prompt: str) -> str:
        """
        Runs the agentic execution loop for up to MAX_STEPS across configured providers.
        Optimized for quota efficiency and resilience:
        - Checks local-first rules before calling any model (0 API calls).
        - Checks 10-minute SQLite request cache (0 API calls).
        - Switches providers automatically on 429/503/timeouts/connection/schema errors.
        - Builds summary locally from tool results without extra summary requests.
        """
        # 1. Local-First Execution (Zero API Calls!)
        local_result = try_local_first_execution(user_prompt)
        if local_result:
            self.memory.add_message(self.session_id, "user", user_prompt)
            self.memory.add_message(self.session_id, "model", local_result)
            return local_result

        # 2. 10-Minute SQLite Cache Check (Zero API Calls!)
        cached_result = self.memory.get_cached_response(user_prompt)
        if cached_result:
            self.memory.add_message(self.session_id, "user", user_prompt)
            self.memory.add_message(self.session_id, "model", cached_result)
            console.print("[dim cyan]Cached result retrieved from SQLite (10-minute cache, 0 API calls).[/dim cyan]")
            return cached_result + "\n\n*(Cached response from SQLite)*"

        # Check provider availability (allow mock clients in tests)
        is_client_mocked = hasattr(getattr(self, "client", None), "models")
        if not is_client_mocked and not self.active_provider.is_available() and not any(p.is_available() for p in self.provider_chain):
            msg = (
                "[bold red]No AI providers available.[/bold red]\n\n"
                "Please configure either:\n"
                "- [bold]Gemini[/bold]: GEMINI_API_KEY in .env\n"
                "- [bold]Ollama[/bold]: Ensure Ollama is running at http://localhost:11434 (or configure OLLAMA_HOST / OLLAMA_API_KEY)"
            )
            console.print(Panel(msg, title="Configuration Missing", border_style="red"))
            return "Configuration missing: No available LLM providers configured."

        # Retrieve prior session messages from SQLite memory
        history_msgs = self.memory.get_session_messages(self.session_id)
        messages: List[LLMMessage] = []

        for m in history_msgs:
            if m.get("content"):
                role = "user" if m.get("role") == "user" else "assistant"
                messages.append(LLMMessage(role=role, content=m["content"]))

        # Add current user prompt
        messages.append(LLMMessage(role="user", content=user_prompt))
        self.memory.add_message(self.session_id, "user", user_prompt)

        # Reset task-level desktop safety counters
        reset_desktop_action_count()
        reset_verification_failures()
        reset_desktop_session()
        reset_emergency_stop()

        # Reset native conversation state on providers if applicable
        for p in self.provider_chain:
            if hasattr(p, "reset_conversation"):
                p.reset_conversation()

        step = 0
        final_text = ""
        failed_attempts = 0

        # Build fallback provider chain list for this run
        chain_candidates: List[BaseProvider] = [self.active_provider]
        for p in self.provider_chain:
            if p.name != self.active_provider.name and p not in chain_candidates:
                chain_candidates.append(p)

        candidate_idx = 0

        with console.status(f"[bold green]Superlocal ({self.active_provider.name}) is analyzing your request...[/bold green]", spinner="dots") as spinner:
            while step < MAX_STEPS:
                if is_emergency_stopped():
                    spinner.stop()
                    console.print("[bold red]Execution stopped: Emergency stop (Ctrl+Alt+Q) triggered.[/bold red]")
                    return "Superlocal execution halted: Emergency stop (Ctrl+Alt+Q) triggered by user."

                step += 1
                response: Optional[LLMResponse] = None

                while candidate_idx < len(chain_candidates):
                    current_prov = chain_candidates[candidate_idx]
                    self.active_provider = current_prov

                    # Sync client if Gemini
                    if isinstance(current_prov, GeminiProvider):
                        current_prov.client = self.client

                    # Skip provider that failed its health check (don't count as step failure)
                    try:
                        h_res = current_prov.health_check()
                        if isinstance(h_res, tuple) and len(h_res) >= 2:
                            is_healthy, status_msg = h_res[0], h_res[1]
                            fix_hint = h_res[2] if len(h_res) > 2 else None
                            if not is_healthy:
                                console.print(f"[dim yellow]Skipping provider '{current_prov.name}': {status_msg}. Fix: {fix_hint}[/dim yellow]")
                                candidate_idx += 1
                                continue
                    except Exception:
                        pass

                    try:
                        response = current_prov.chat(
                            messages=messages,
                            tools=AGENT_TOOLS,
                            system_prompt=get_system_prompt() if isinstance(current_prov, GeminiProvider) else None,
                        )
                        break
                    except Exception as prov_err:
                        err_msg = str(prov_err)
                        candidate_idx += 1
                        if candidate_idx < len(chain_candidates):
                            next_prov = chain_candidates[candidate_idx]
                            console.print(
                                f"[bold yellow]Provider '{escape(current_prov.name)}' failed ({escape(err_msg)}). "
                                f"Switching to fallback provider '{escape(next_prov.name)}'...[/bold yellow]"
                            )
                            self.active_provider = next_prov
                            messages = sanitize_messages_for_provider_switch(messages)
                            continue
                        else:
                            # All providers in chain failed: report each failed provider and exact fix
                            failure_lines = ["[bold red]All AI providers failed:[/bold red]\n"]
                            for p in chain_candidates:
                                if p.name == current_prov.name and isinstance(prov_err, ProviderQuotaExhaustedError):
                                    p_stat = f"Quota exhausted (429). Quota resets in {prov_err.retry_delay}"
                                    p_fix = f"Wait {prov_err.retry_delay} for quota reset or switch API keys."
                                else:
                                    try:
                                        h_res = p.health_check()
                                        p_stat = h_res[1] if isinstance(h_res, tuple) else "Failed"
                                        p_fix = h_res[2] if isinstance(h_res, tuple) and len(h_res) > 2 else "Check configuration."
                                    except Exception:
                                        p_stat = "Unavailable"
                                        p_fix = "Check configuration."
                                failure_lines.append(f"• [bold cyan]{escape(p.name)}[/bold cyan]: {escape(str(p_stat))}\n  [green]Fix: {escape(str(p_fix))}[/green]")

                            summary_err = "\n".join(failure_lines).strip()
                            spinner.stop()
                            console.print(Panel(summary_err, title="All Providers Failed", border_style="red"))
                            return summary_err

                if not response:
                    if candidate_idx >= len(chain_candidates):
                        failure_lines = ["[bold red]All AI providers failed:[/bold red]\n"]
                        for p in chain_candidates:
                            try:
                                h_res = p.health_check()
                                p_stat = h_res[1] if isinstance(h_res, tuple) else "Failed"
                                p_fix = h_res[2] if isinstance(h_res, tuple) and len(h_res) > 2 else "Check configuration."
                            except Exception:
                                p_stat = "Unavailable"
                                p_fix = "Check configuration."
                            failure_lines.append(f"• [bold cyan]{escape(p.name)}[/bold cyan]: {escape(str(p_stat))}\n  [green]Fix: {escape(str(p_fix))}[/green]")

                        summary_err = "\n".join(failure_lines).strip()
                        spinner.stop()
                        console.print(Panel(summary_err, title="All Providers Failed", border_style="red"))
                        return summary_err
                    break

                # If no function calls, task is complete
                if not response.tool_calls:
                    final_text = response.text or ""
                    break

                # Record model message with tool calls
                messages.append(LLMMessage(
                    role="assistant",
                    content=response.text,
                    tool_calls=response.tool_calls,
                ))

                # Execute all function calls (Parallel / Batched execution)
                executed_tools_this_turn: List[Dict[str, Any]] = []

                for tc in response.tool_calls:
                    if is_emergency_stopped():
                        spinner.stop()
                        console.print("[bold red]Action aborted: Emergency stop (Ctrl+Alt+Q) active.[/bold red]")
                        return "Superlocal execution halted: Emergency stop (Ctrl+Alt+Q) triggered by user."

                    fn_name = tc.name
                    fn_args = tc.arguments
                    tc_id = tc.id

                    spinner.stop()
                    console.print(f"\n[bold blue]Step {step}/{MAX_STEPS}:[/bold blue] Superlocal selected [bold cyan]{fn_name}[/bold cyan]")

                    # Run tool with confirmation
                    tool_res = self.execute_tool(fn_name, fn_args)
                    executed_tools_this_turn.append({"name": fn_name, "args": fn_args, "result": tool_res})

                    if is_emergency_stopped():
                        console.print("[bold red]Action aborted: Emergency stop (Ctrl+Alt+Q) active.[/bold red]")
                        return "Superlocal execution halted: Emergency stop (Ctrl+Alt+Q) triggered by user."

                    # Retry counter check
                    if not tool_res.get("success", True):
                        failed_attempts += 1
                        if failed_attempts >= 3:
                            console.print(f"[bold yellow]Notice:[/bold yellow] Tool failed 3 times. Superlocal will adjust strategy.")
                    else:
                        failed_attempts = 0

                    spinner.start()

                    # Send tool response back in message history
                    messages.append(LLMMessage(
                        role="tool",
                        content=tool_res,
                        tool_call_id=tc_id,
                        name=fn_name,
                    ))

                # BUILD LOCAL SUMMARY: Avoid sending an unnecessary extra API request!
                all_tools_ok = all(t.get("result", {}).get("success", True) for t in executed_tools_this_turn)
                if all_tools_ok:
                    final_text = build_local_summary(executed_tools_this_turn)
                    break

        # Cache response if read-only prompt
        if is_read_only_prompt(user_prompt) and final_text:
            self.memory.cache_response(user_prompt, final_text, ttl_seconds=CACHE_TTL_SECONDS)

        # Save model completion to memory
        if final_text:
            self.memory.add_message(self.session_id, "model", final_text)

        return final_text
