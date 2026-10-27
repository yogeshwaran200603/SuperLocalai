"""
SuperLocal Computer Mode: Permissions & Sandbox Controller
Enforces:
- Session sandbox directory (all file reads, writes, downloads restricted to sandbox)
- System directory blocking (C:\\Windows, Program Files, system roots)
- Per-session app allowlist with toast notifications and terminal confirmations
- Strict double-confirmation for banking apps, password managers, and system settings
- Untrusted text tagging and prompt-injection defense
"""

import os
import sys
import re
import datetime
import subprocess
from pathlib import Path
from typing import Set, Dict, Any, Optional, Tuple, List, Union

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from config import JOBS_DIR, WORKSPACE_DIR, ALLOWED_DIRECTORIES

console = Console()

# Severe Blocked Folders
SYSTEM_BLOCKED_DIRECTORIES = [
    Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve(),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")).resolve(),
    Path(r"C:\ProgramData").resolve(),
    Path(r"C:\\").resolve(),
]

# Sensitive App Categories requiring task naming + double confirmation
RESTRICTED_APP_KEYWORDS = {
    "banking": [
        "bank", "chase", "wells fargo", "bankofamerica", "citi",
        "hdfc", "icici", "sbi", "paypal", "venmo", "revolut", "fidelity", "vanguard"
    ],
    "password_managers": [
        "1password", "bitwarden", "keepass", "lastpass", "dashlane", "enpass", "authenticator"
    ],
    "system_settings": [
        "systemsettings", "control panel", "regedit", "msconfig", "gpedit", "device manager"
    ]
}


def send_windows_toast(title: str, message: str):
    """
    Displays a native Windows toast notification using PowerShell.
    Non-blocking and gracefully falls back if notifications are disabled.
    """
    if sys.platform != "win32":
        return

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null
    $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("SuperLocal Computer Mode").Show($toast)
    """
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


class ComputerSessionSandbox:
    """
    Manages the session sandbox directory and enforces path boundaries.
    """

    def __init__(self, sandbox_dir: Optional[Union[str, Path]] = None, task_slug: str = "computer_task"):
        if sandbox_dir:
            self.sandbox_path = Path(sandbox_dir).resolve()
        else:
            date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", task_slug)[:30]
            self.sandbox_path = (JOBS_DIR / f"{date_str}_{clean_slug}").resolve()

        self.sandbox_path.mkdir(parents=True, exist_ok=True)

    def is_path_safe(self, target: Union[str, Path]) -> Tuple[bool, str]:
        """
        Ensures target path is strictly within the session sandbox
        and never inside a blocked system folder.
        """
        try:
            resolved = Path(os.path.expandvars(str(target))).resolve()
        except Exception as e:
            return False, f"Invalid path specification: {e}"

        # 1. System blocklist check
        c_root = Path(r"C:\\").resolve()
        for sys_dir in SYSTEM_BLOCKED_DIRECTORIES:
            try:
                if resolved == sys_dir or (sys_dir != c_root and sys_dir in resolved.parents):
                    return False, f"Access blocked: '{resolved}' is a critical system directory."
            except Exception:
                pass

        # 2. Strict sandbox containment
        try:
            # Must be inside sandbox_path
            resolved.relative_to(self.sandbox_path)
            return True, "Path is within session sandbox."
        except ValueError:
            return False, f"Access denied: Path '{resolved}' is outside session sandbox '{self.sandbox_path}'."


class ComputerPermissionManager:
    """
    Tracks per-session app allowlists, prompts for application control,
    guards sensitive categories with double confirmation, and defends against untrusted screen text.
    """

    def __init__(self, sandbox: ComputerSessionSandbox, task_goal: str = ""):
        self.sandbox = sandbox
        self.task_goal = task_goal.lower()
        self.allowed_apps: Set[str] = set()
        self.session_always_allow: Set[str] = set()
        self.untrusted_injection_alerts: List[str] = []

    def normalize_app_name(self, app_name: str) -> str:
        """Strips executable extensions and paths to get standard base app name."""
        base = Path(app_name).name.lower()
        for ext in (".exe", ".bat", ".cmd", ".lnk"):
            if base.endswith(ext):
                base = base[:-len(ext)]
        return base

    def is_restricted_app(self, app_name: str) -> Tuple[bool, str]:
        """Checks if app is in banking, password manager, or system settings category."""
        norm = self.normalize_app_name(app_name)
        for cat, kw_list in RESTRICTED_APP_KEYWORDS.items():
            for kw in kw_list:
                if kw in norm:
                    return True, cat
        return False, ""

    def request_app_control(self, app_name: str) -> Tuple[bool, str]:
        """
        Ensures the app is on the session allowlist.
        If not, prompts the user via Toast notification + terminal confirmation.
        """
        norm = self.normalize_app_name(app_name)

        if norm in self.session_always_allow:
            return True, "Allowed (already approved for this session)"

        # Check restricted categories
        is_restr, category = self.is_restricted_app(norm)
        if is_restr:
            # Check if explicitly named in the task goal
            if not any(kw in self.task_goal for kw in RESTRICTED_APP_KEYWORDS[category]):
                return False, (
                    f"Blocked: '{app_name}' belongs to protected category '{category}'. "
                    f"Restricted apps cannot be controlled unless explicitly named in the task."
                )

            # Double confirmation mandatory
            console.print(Panel(
                f"[bold red]WARNING: Control requested for sensitive {category} application:[/bold red] '{app_name}'\n"
                f"Controlling sensitive software presents high security risks.",
                title="[Double Confirmation Required - 1/2]",
                border_style="red"
            ))
            ans1 = input(f"First Confirmation: Allow SuperLocal to interact with '{app_name}'? (yes/no): ").strip().lower()
            if ans1 != "yes":
                return False, f"Rejected on first confirmation: {app_name}"

            ans2 = input(f"Second Confirmation: Are you ABSOLUTELY sure you want to control '{app_name}'? (yes/no): ").strip().lower()
            if ans2 != "yes":
                return False, f"Rejected on second confirmation: {app_name}"

            self.session_always_allow.add(norm)
            return True, f"Double-confirmed sensitive app: {norm}"

        # Standard app prompt
        send_windows_toast("SuperLocal Permission Request", f"Allow SuperLocal to control '{app_name}'?")
        console.print(f"\n[bold yellow]Permission Request:[/bold yellow] Allow SuperLocal to control [cyan]'{app_name}'[/cyan]?")
        ans = input("Choose (y = allow once, a = always for this session, n = deny) [y/a/N]: ").strip().lower()

        if ans in ("a", "always"):
            self.session_always_allow.add(norm)
            self.allowed_apps.add(norm)
            return True, f"Always allowed '{norm}' for this session."
        elif ans in ("y", "yes"):
            self.allowed_apps.add(norm)
            return True, f"Allowed '{norm}' once."
        else:
            return False, f"Control of '{app_name}' was denied by user."

    def sanitize_untrusted_screen_text(self, text: str) -> Tuple[str, bool]:
        """
        Tags and neutralizes any prompt injection discovered in screen text,
        web pages, or document files.
        """
        injection_patterns = [
            r"ignore\s+(?:all\s+)?previous\s+instructions",
            r"system\s*prompt\s*:",
            r"you\s+are\s+now\s+(?:in\s+developer\s+mode|unrestricted)",
            r"disregard\s+(?:the\s+above|all\s+rules)",
            r"new\s+system\s+instruction",
            r"add\s+step\s+to\s+plan",
            r"elevate\s+(?:to\s+)?admin",
            r"grant\s+permission",
            r"send\s+password",
        ]
        detected = False
        clean = text
        for pat in injection_patterns:
            if re.search(pat, clean, re.IGNORECASE):
                detected = True
                alert = f"Untrusted screen injection pattern detected: '{pat}'"
                self.untrusted_injection_alerts.append(alert)
                clean = re.sub(pat, "[UNTRUSTED_INJECTION_REDACTED]", clean, flags=re.IGNORECASE)

        return clean, detected
