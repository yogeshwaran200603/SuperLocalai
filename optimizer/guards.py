"""
SuperLocal PC Optimizer: Safety Guards & Compliance Module
Enforces:
- Hard prohibition of harmful "tweaks" (registry cleaners, RAM flushers, service disabling, Defender disabling).
- Path boundary restrictions (blocking C:\\Windows, System32, Program Files, user documents).
- System Restore point creation prior to system-wide changes.
- Mandatory interactive previews and confirmations (y/n) for destructive actions.
- Action logging to logs/optimizer.log.
"""

import os
import re
import sys
import datetime
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from config import (
    OPTIMIZER_LOG_PATH,
    OPTIMIZER_QUARANTINE_DIR,
)

console = Console()

# Educational explanations for dangerous / snake-oil tweaks that SuperLocal deliberately refuses
FORBIDDEN_TWEAK_EXPLANATIONS = {
    "registry_cleaner": (
        "Windows Registry cleaners are unnecessary, outdated, and potentially dangerous. "
        "The registry is an indexed database where unused keys occupy negligible disk space (<0.01% of memory) "
        "and have zero impact on CPU or system performance. Automated registry cleaners frequently delete "
        "active COM/CLSID registrations and break applications. SuperLocal safely cleans actual filesystem clutter instead."
    ),
    "ram_booster": (
        "RAM 'boosters' and memory flushers force active working set memory into the Windows pagefile on disk. "
        "When your applications need that memory again, your system suffers severe disk thrashing and stutter. "
        "Modern Windows memory management already caches smartly and frees unused memory on demand. "
        "SuperLocal instead identifies high-memory processes so you can close unnecessary apps safely."
    ),
    "service_disabling": (
        "Disabling core Windows services for 'gaming tweaks' or 'speed' causes subtle application failures, "
        "broken printing, Windows Update breakages, and security vulnerabilities with negligible performance gains. "
        "SuperLocal safely manages startup applications instead of disabling system services."
    ),
    "defender_tampering": (
        "Windows Defender and Firewall provide essential real-time security without meaningful overhead on modern hardware. "
        "Disabling security features exposes your PC to malware and ransomware. "
        "SuperLocal inspects and reports Defender status without modifying it."
    ),
    "debloater_scripts": (
        "Third-party 'debloater' and tweak scripts often break Windows updates, Sysprep, UWP packages, "
        "and Microsoft Store apps unpredictably. SuperLocal uses verified native PowerShell and Windows API methods."
    )
}

# Blocked path patterns that the cleaner or duplicate remover can NEVER delete
BLOCKED_PATH_PATTERNS = [
    r"^[a-zA-Z]:\\Windows(?:\\.*)?$",
    r"^[a-zA-Z]:\\Windows\\System32(?:\\.*)?$",
    r"^[a-zA-Z]:\\Program Files(?:\\.*)?$",
    r"^[a-zA-Z]:\\Program Files \(x86\)(?:\\.*)?$",
    r"^[a-zA-Z]:\\ProgramData\\Microsoft(?:\\.*)?$",
    r"^[a-zA-Z]:\\Users\\[^\\]+\\Documents(?:\\.*)?$",
    r"^[a-zA-Z]:\\Users\\[^\\]+\\Desktop(?:\\.*)?$",
    r"^[a-zA-Z]:\\Recovery(?:\\.*)?$",
    r"^[a-zA-Z]:\\\$Recycle\.Bin(?:\\.*)?$",
    r"^[a-zA-Z]:\\System Volume Information(?:\\.*)?$",
]

# Sensitive startup publishers requiring secondary confirmation
PROTECTED_PUBLISHERS = [
    "microsoft",
    "windows",
    "intel",
    "nvidia",
    "amd",
    "realtek",
    "synaptics",
    "logitech",
    "corsair",
    "dell",
    "hp",
    "lenovo",
    "asus",
]

PROTECTED_STARTUP_KEYWORDS = [
    "antivirus",
    "security",
    "defender",
    "driver",
    "audio",
    "touchpad",
    "display",
    "graphic",
    "network",
    "firewall",
]


def check_forbidden_tweak(query: str) -> Tuple[bool, str]:
    """
    Checks if a user query requests harmful tweaks (registry cleaner, RAM booster, service disabling, etc.).
    Returns: (is_forbidden: bool, educational_explanation: str)
    """
    q = query.lower()

    if re.search(r"\b(?:clean|compact|fix|defrag)\s+(?:the\s+)?registry\b|\bregistry\s+cleaner\b", q):
        return True, FORBIDDEN_TWEAK_EXPLANATIONS["registry_cleaner"]

    if re.search(r"\b(?:boost|flush|free|clean|purge)\s+(?:the\s+)?(?:ram|memory)\b|\bram\s+booster\b|\bemptyworkingset\b", q):
        return True, FORBIDDEN_TWEAK_EXPLANATIONS["ram_booster"]

    if re.search(r"\b(?:disable|stop|tweak|kill)\s+(?:windows\s+)?services?\s+(?:for\s+speed|for\s+gaming)?\b", q):
        return True, FORBIDDEN_TWEAK_EXPLANATIONS["service_disabling"]

    if re.search(r"\b(?:disable|turn\s*off|kill|bypass)\s+(?:windows\s+)?(?:defender|firewall|antivirus)\b", q):
        return True, FORBIDDEN_TWEAK_EXPLANATIONS["defender_tampering"]

    if re.search(r"\b(?:debloat|tweak)\s+script\b|\bradioactive\s+tweak\b|\bunattended\s+debloat\b", q):
        return True, FORBIDDEN_TWEAK_EXPLANATIONS["debloater_scripts"]

    return False, ""


def is_safe_optimizer_path(target_path: Path) -> Tuple[bool, str]:
    """
    Verifies that a target path does not violate system path safety boundaries.
    """
    try:
        resolved = str(target_path.resolve())
    except Exception:
        resolved = str(target_path)

    for pat in BLOCKED_PATH_PATTERNS:
        if re.match(pat, resolved, re.IGNORECASE):
            return False, f"Path '{resolved}' is inside protected system directory."

    return True, "Path is allowed."


def is_protected_startup_item(name: str, publisher: str, command: str) -> bool:
    """
    Identifies whether a startup entry belongs to Microsoft, core drivers, or security software.
    """
    combined = f"{name} {publisher} {command}".lower()
    if any(pub in combined for pub in PROTECTED_PUBLISHERS):
        return True
    if any(kw in combined for kw in PROTECTED_STARTUP_KEYWORDS):
        return True
    return False


def confirm_action(prompt_text: str, default: bool = False) -> bool:
    """
    Prompts the user for interactive confirmation (y/n).
    In non-interactive or testing environments without TTY, respects default or env.
    """
    if os.getenv("TEST_AUTO_APPROVE", "false").lower() in ("true", "1", "yes"):
        return True

    if not sys.stdin.isatty():
        return default

    try:
        return Confirm.ask(f"[bold yellow]{prompt_text}[/bold yellow]", default=default)
    except Exception:
        return default


def confirm_admin_action(action_description: str) -> bool:
    """
    Mandatory explicit confirmation required for administrative actions.
    """
    console.print(Panel(
        f"[bold red]Administrative Action Warning:[/bold red]\n{action_description}\n"
        "[dim]This action modifies system configuration or repair state.[/dim]",
        border_style="red"
    ))
    return confirm_action("Do you explicitly authorize this administrative operation?", default=False)


def create_restore_point_if_enabled(description: str = "SuperLocal PC Optimizer Checkpoint") -> Tuple[bool, str]:
    """
    Attempts to create a Windows System Restore point before system modifications.
    If System Restore is disabled, notifies the user cleanly.
    """
    import subprocess
    cmd = [
        "powershell", "-NoProfile", "-Command",
        f"Checkpoint-Computer -Description '{description}' -RestorePointType 'MODIFY_SETTINGS' -ErrorAction SilentlyContinue"
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            msg = "System Restore point created successfully."
            log_optimizer_action("create_restore_point", {"description": description}, "SUCCESS", msg)
            return True, msg
        else:
            msg = "System Restore is currently disabled on this system or requires elevated permissions. Proceeding with caution."
            log_optimizer_action("create_restore_point", {"description": description}, "WARNING", msg)
            return False, msg
    except Exception as e:
        msg = f"Could not create System Restore point: {e}"
        log_optimizer_action("create_restore_point", {"description": description}, "ERROR", msg)
        return False, msg


def log_optimizer_action(action: str, details: Dict[str, Any], status: str, message: str = ""):
    """
    Appends an entry to logs/optimizer.log.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{action}] STATUS={status} DETAILS={details} MESSAGE={message}\n"
    try:
        OPTIMIZER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OPTIMIZER_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        console.print(f"[dim]Failed to write to optimizer log: {e}[/dim]")
