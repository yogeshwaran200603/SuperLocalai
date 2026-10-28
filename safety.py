"""
Astra-Local Safety Engine
Enforces command blocklists, path boundary constraints, permission checks,
and audit logging to logs/actions.log.
"""

import os
import sys
import re
import datetime
import threading
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import keyboard
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.markup import escape

console = Console()

from config import (
    ACTIONS_LOG_PATH,
    AUTO_APPROVE_SAFE,
    ALLOWED_DIRECTORIES,
    GEMINI_API_KEY,
    ALL_API_KEYS,
)


def mask_all_keys(text: str) -> str:
    """Sanitizes any configured provider API keys from text or log messages."""
    if not text:
        return ""
    sanitized = str(text)
    for key in ALL_API_KEYS:
        if key and key in sanitized:
            sanitized = sanitized.replace(key, "[REDACTED_API_KEY]")
    return sanitized


def log_action(tool_name: str, args: Dict[str, Any], status: str, details: str = ""):
    """Logs tool execution to logs/actions.log, sanitizing any sensitive tokens."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    args_str = mask_all_keys(str(args))
    details_str = mask_all_keys(details)

    log_entry = f"[{timestamp}] [{tool_name}] STATUS={status} ARGS={args_str} DETAILS={details_str}\n"

# Severe Blocklist: Disallowed unconditionally
BLOCKLIST_PATTERNS = [
    r"\bformat\s+[a-zA-Z]:|\bformat\b(?!\s*-(?:Table|List|Custom|Wide))",
    r"\bdiskpart\b",
    r"rm\s+-rf\s+/",
    r"\bdel\s+(/[a-zA-Z0-9_-]+\s+)*[cC]:\\",
    r"\brmdir\s+/[sS]\s+[cC]:\\",
    r"Remove-Item\s+.*[cC]:\\(Windows|System32)",
    r"\breg\s+delete\b",
    r"Remove-ItemProperty\s+.*HKLM:",
    r"\bshutdown\b",
    r"\bstop-computer\b",
    r"[cC]:\\Windows\\System32",
    r"[cC]:\\Windows(?:\\[^\s\"']*)?",
    r"\bvssadmin\s+delete\s+shadows\b",
    r"\bbcdedit\b",
]

# High-Risk Operations: ALWAYS require interactive confirmation, regardless of AUTO_APPROVE_SAFE
HIGH_RISK_COMMAND_PATTERNS = [
    r"Remove-Item\b",
    r"\bdel\b",
    r"\brmdir\b",
    r"\bwinget\s+install\b",
    r"\bchoco\s+install\b",
    r"\bpip\s+install\b",
    r"\bnpm\s+install\b",
    r"\brunas\b",
    r"Start-Process\s+.*-Verb\s+RunAs",
    r"\bSet-ExecutionPolicy\b",
    r"\bnet\s+user\b",
    r"\bnet\s+localgroup\b",
    r"Set-ItemProperty\s+.*HKCU:",
    r"New-ItemProperty\s+.*HKCU:",
    r"\bcurl\b.*\|\s*(?:iex|bash|sh|powershell)",
    r"\biwr\b.*\|\s*(?:iex|powershell)",
]

# Harmless / Safe Tools for AUTO_APPROVE_SAFE
SAFE_TOOLS = {
    "open_url",
    "open_app",
    "file_read",
    "file_list",
    "file_write",
    "file_move",
    "browser_goto",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_read_text",
    "browser_screenshot",
    "browser_wait_for",
    "desktop_screenshot",
    "desktop_click",
    "desktop_type",
    "desktop_hotkey",
    "desktop_focus_window",
    "desktop_locate_element",
    "data_inspect",
    "data_clean",
    "data_chart",
    "data_train_model",
    "doc_create_pptx",
    "doc_create_docx",
    "doc_create_xlsx",
    "doc_create_pdf",
    "scaffold_project",
    "run_python",
    "run_tests",
    "fix_and_rerun",
    "test_website",
}

# Tools that ALWAYS require explicit approval regardless of settings
MANDATORY_CONFIRMATION_TOOLS = {
    "file_delete",
    "whatsapp_send",
}


def log_action(tool_name: str, args: Dict[str, Any], status: str, details: str = ""):
    """Logs tool execution to logs/actions.log, sanitizing any sensitive tokens."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    args_str = str(args)
    if GEMINI_API_KEY and GEMINI_API_KEY in args_str:
        args_str = args_str.replace(GEMINI_API_KEY, "[REDACTED_API_KEY]")
    if GEMINI_API_KEY and GEMINI_API_KEY in details:
        details = details.replace(GEMINI_API_KEY, "[REDACTED_API_KEY]")

    log_entry = f"[{timestamp}] [{tool_name}] STATUS={status} ARGS={args_str} DETAILS={details}\n"
    try:
        with open(ACTIONS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        console.print(f"[red]Failed to write to action log: {e}[/red]")


def is_path_allowed(path_str: str) -> bool:
    """Checks if a file path falls inside permitted directories."""
    try:
        resolved = Path(os.path.expandvars(path_str)).resolve()
        for allowed in ALLOWED_DIRECTORIES:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False


def inspect_powershell_safety(script: str) -> Tuple[bool, str, bool]:
    """
    Inspects PowerShell script.
    Returns:
        is_blocked (bool), reason (str), is_high_risk (bool)
    """
    # 1. Check against critical blocklist
    for pattern in BLOCKLIST_PATTERNS:
        if re.search(pattern, script, re.IGNORECASE):
            return True, f"Blocked dangerous command matching pattern: '{pattern}'", True

    # 2. Check for high risk patterns
    for pattern in HIGH_RISK_COMMAND_PATTERNS:
        if re.search(pattern, script, re.IGNORECASE):
            return False, f"High-risk action detected: '{pattern}'", True

    return False, "Safe", False


def confirm_action(tool_name: str, args: Dict[str, Any], prompt_message: Optional[str] = None) -> bool:
    """
    Evaluates whether an action requires confirmation, prompts the user if needed,
    and returns True if allowed to proceed.
    """
    # Check blocklist for shell commands
    if tool_name == "run_powershell":
        script = args.get("script", "")
        blocked, reason, is_high_risk = inspect_powershell_safety(script)
        if blocked:
            console.print(Panel(f"[bold red]SECURITY BLOCK[/bold red]\n{reason}", title="Action Denied", border_style="red"))
            log_action(tool_name, args, "BLOCKED", reason)
            return False

        # If auto-approve is active and not high risk, proceed
        if AUTO_APPROVE_SAFE and not is_high_risk:
            log_action(tool_name, args, "AUTO_APPROVED", "Safe PowerShell command")
            return True

        # Otherwise prompt user
        display_text = f"[bold cyan]Tool:[/bold cyan] {tool_name}\n[bold yellow]Script:[/bold yellow]\n{script.strip()}"
        console.print(Panel(display_text, title="Action Confirmation", border_style="yellow"))
        approved = Confirm.ask("[bold]Run this PowerShell script?[/bold]", default=False)
        log_action(tool_name, args, "APPROVED" if approved else "USER_DENIED", "Interactive PowerShell approval")
        return approved

    # Check mandatory confirmation tools (whatsapp_send, file_delete)
    if tool_name in MANDATORY_CONFIRMATION_TOOLS:
        if tool_name == "whatsapp_send":
            # whatsapp_send performs its own mandatory interactive verification inside the browser UI before clicking send
            log_action(tool_name, args, "INVOKED", "Proceeding to interactive WhatsApp confirmation")
            return True

        if tool_name == "file_delete":
            target_path = args.get("path", "")
            console.print(Panel(
                f"[bold red]Target Path:[/bold red] {target_path}",
                title="Confirm File Deletion",
                border_style="red"
            ))
            approved = Confirm.ask(f"[bold red]Permanently delete '{target_path}'?[/bold red]", default=False)
            log_action(tool_name, args, "APPROVED" if approved else "USER_DENIED", "File deletion confirmation")
            return approved

    # Check harmless tools with AUTO_APPROVE_SAFE
    if AUTO_APPROVE_SAFE and tool_name in SAFE_TOOLS:
        log_action(tool_name, args, "AUTO_APPROVED", "Whitelisted safe tool")
        return True

    # If voice mode is active and action is dangerous, invoke voice + terminal confirmation (15s timeout)
    try:
        from voice import get_voice_assistant, is_dangerous_voice_action, request_voice_confirmation
        va = get_voice_assistant()
        if va and getattr(va, "is_running", False):
            is_dang, dang_desc = is_dangerous_voice_action(tool_name, args)
            if is_dang:
                approved = request_voice_confirmation(
                    dang_desc,
                    tts=getattr(va, "tts", None),
                    stt=getattr(va, "stt", None),
                    record_func=getattr(va, "_record_pcm_chunk", None),
                    timeout_sec=15.0,
                )
                log_action(tool_name, args, "APPROVED" if approved else "USER_DENIED", "Spoken voice confirmation")
                return approved
    except Exception:
        pass

    # Default prompt for other actions (file_write, desktop_click, etc.)
    summary = prompt_message or f"Execute tool [bold]{tool_name}[/bold] with args:\n{args}"
    console.print(Panel(summary, title="Confirm Action", border_style="cyan"))
    approved = Confirm.ask("[bold]Run? (y/n)[/bold]", default=True)
    log_action(tool_name, args, "APPROVED" if approved else "USER_DENIED", "General tool confirmation")
    return approved


# ==============================================================================
# Desktop Automation Safety Engine & Hotkey Controller
# ==============================================================================

EMERGENCY_STOP_EVENT = threading.Event()
_hotkey_listener_thread: Optional[threading.Thread] = None
_desktop_session_approved: bool = False

SENSITIVE_DESKTOP_KEYWORDS = [
    "password", "passwd", "pin", "credential", "secret", "cvv",
    "send", "pay", "payment", "delete", "remove", "confirm", "confirmation",
    "submit", "checkout", "purchase", "order", "buy", "transfer", "destroy"
]


def trigger_emergency_stop(source: str = "Ctrl+Alt+Q") -> None:
    """
    Immediately stops the agent loop and any running desktop action.
    Triggered via global hotkey (Ctrl+Alt+Q) or PyAutoGUI FailSafe.
    """
    EMERGENCY_STOP_EVENT.set()
    log_action("emergency_stop", {"source": source}, "TRIGGERED", f"Emergency stop initiated from {source}")
    console.print("\n[bold red]===============================================================================[/bold red]")
    console.print(f"[bold red]!!! EMERGENCY STOP TRIGGERED ({source}) !!![/bold red]")
    console.print("[bold red]Stopping agent execution loop and halting all desktop automation actions immediately.[/bold red]")
    console.print("[bold red]===============================================================================[/bold red]\n")


def is_emergency_stopped() -> bool:
    """Returns True if an emergency stop has been requested."""
    return EMERGENCY_STOP_EVENT.is_set()


def reset_emergency_stop() -> None:
    """Resets the emergency stop state to allow new tasks."""
    EMERGENCY_STOP_EVENT.clear()


def _hotkey_worker():
    """Background worker thread registering the global Ctrl+Alt+Q hotkey."""
    try:
        keyboard.add_hotkey("ctrl+alt+q", lambda: trigger_emergency_stop("Ctrl+Alt+Q"), suppress=False)
        keyboard.wait()
    except Exception as e:
        # In headless or non-interactive environments, background hook may fail gracefully
        pass


def start_emergency_stop_listener() -> None:
    """Starts the background thread monitoring global hotkey Ctrl+Alt+Q."""
    global _hotkey_listener_thread
    if _hotkey_listener_thread is None or not _hotkey_listener_thread.is_alive():
        _hotkey_listener_thread = threading.Thread(
            target=_hotkey_worker,
            daemon=True,
            name="EmergencyStopHotkeyListener"
        )
        _hotkey_listener_thread.start()


def is_desktop_session_approved() -> bool:
    """Checks whether desktop control session has been confirmed."""
    return _desktop_session_approved


def set_desktop_session_approved(approved: bool) -> None:
    """Programmatically sets desktop control session approval (useful for tests)."""
    global _desktop_session_approved
    _desktop_session_approved = approved


def reset_desktop_session() -> None:
    """Resets desktop session approval flag for a new run/task."""
    global _desktop_session_approved
    _desktop_session_approved = False


def check_desktop_session_permission() -> bool:
    """
    Before any desktop session, prints:
    'Astra will control your mouse and keyboard. Move the mouse to the top-left corner or press Ctrl+Alt+Q to stop.'
    and asks y/n.
    """
    global _desktop_session_approved
    if _desktop_session_approved:
        return True

    console.print("\n[bold yellow]Astra will control your mouse and keyboard. Move the mouse to the top-left corner or press Ctrl+Alt+Q to stop.[/bold yellow]")
    approved = Confirm.ask("[bold]Allow desktop control? (y/n)[/bold]", default=False)
    if approved:
        _desktop_session_approved = True
        log_action("desktop_session", {}, "APPROVED", "Desktop session approved by user")
        return True
    else:
        _desktop_session_approved = False
        log_action("desktop_session", {}, "DENIED", "Desktop session denied by user")
        return False


def is_sensitive_target_or_text(text: Optional[str]) -> bool:
    """Checks if text or element description matches password fields or send/pay/delete/confirm operations."""
    if not text:
        return False
    t_lower = text.lower().strip()
    for kw in SENSITIVE_DESKTOP_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', t_lower) or kw in t_lower:
            return True
    return False


def confirm_sensitive_desktop_action(action_type: str, details: str, target: str = "") -> bool:
    """
    Prompts mandatory interactive confirmation for password typing or send/pay/delete/confirm actions.
    """
    prompt_str = f"Desktop Action: [bold cyan]{action_type}[/bold cyan]"
    if target:
        prompt_str += f"\nTarget: [bold yellow]{target}[/bold yellow]"
    if details:
        prompt_str += f"\nDetails: [bold]{details}[/bold]"

    console.print(Panel(
        prompt_str,
        title="[bold red]SENSITIVE OPERATION CONFIRMATION[/bold red]",
        border_style="red"
    ))
    approved = Confirm.ask("[bold red]This is a sensitive action (password / payment / deletion / submission). Proceed? (y/n)[/bold red]", default=False)
    log_action(f"desktop_{action_type}", {"target": target, "details": details}, "APPROVED" if approved else "USER_DENIED", "Sensitive desktop operation confirmation")
    return approved


def format_truthful_status(status: str, message: str) -> str:
    """
    Formats a truthful task status. Never prints [OK] Task Completed on failure.
    Allowed statuses: SUCCESS, PARTIAL, FAILED, BLOCKED.
    All error/result text is safely escaped with rich.markup.escape.
    """
    raw_status = (status or "").upper().strip()
    if raw_status in ("SUCCESS", "OK", "COMPLETED"):
        final_status = "SUCCESS"
        color = "bold green"
    elif raw_status in ("PARTIAL", "INCOMPLETE"):
        final_status = "PARTIAL"
        color = "bold yellow"
    elif raw_status in ("BLOCKED", "USER_DENIED", "DENIED", "WAITING"):
        final_status = "BLOCKED"
        color = "bold magenta"
    else:
        final_status = "FAILED"
        color = "bold red"

    escaped_msg = escape(str(message or ""))
    return f"[{color}][{final_status}][/{color}] {escaped_msg}"

