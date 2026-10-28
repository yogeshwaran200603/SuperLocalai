"""
Astra-Local Shell & OS Automation Tools
Provides run_powershell, open_url, and open_app with shortcuts lookup.
"""

import subprocess
import webbrowser
import os
import time
from typing import Dict, Any
from config import POWERSHELL_TIMEOUT, load_shortcuts
from safety import is_emergency_stopped


def run_powershell(script: str) -> Dict[str, Any]:
    """
    Executes a PowerShell script with powershell -NoProfile -ExecutionPolicy Bypass -Command.
    Enforces a configurable timeout (default 60s) and captures stdout, stderr, and exit code.
    Interrupts immediately if emergency stop (Ctrl+Alt+Q) is triggered.
    """
    if is_emergency_stopped():
        return {
            "stdout": "",
            "stderr": "Execution cancelled: Emergency stop (Ctrl+Alt+Q) active.",
            "exit_code": -1,
            "success": False,
        }

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        script
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        start_time = time.time()
        while proc.poll() is None:
            if is_emergency_stopped():
                proc.kill()
                return {
                    "stdout": "",
                    "stderr": "Execution cancelled: Emergency stop (Ctrl+Alt+Q) triggered.",
                    "exit_code": -1,
                    "success": False,
                }
            if time.time() - start_time > POWERSHELL_TIMEOUT:
                proc.kill()
                return {
                    "stdout": "",
                    "stderr": f"Execution timed out after {POWERSHELL_TIMEOUT} seconds.",
                    "exit_code": -1,
                    "success": False,
                }
            time.sleep(0.05)

        stdout, stderr = proc.communicate()
        return {
            "stdout": (stdout or "").strip(),
            "stderr": (stderr or "").strip(),
            "exit_code": proc.returncode,
            "success": proc.returncode == 0,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Failed to execute PowerShell: {str(e)}",
            "exit_code": -1,
            "success": False,
        }


def open_url(url: str) -> Dict[str, Any]:
    """
    Opens a website URL in the default Windows web browser.
    Checks shortcuts.json for shortcut aliases (e.g., 'youtube').
    """
    shortcuts = load_shortcuts()
    websites = shortcuts.get("websites", {})

    target_url = websites.get(url.lower(), url)
    if not (target_url.startswith("http://") or target_url.startswith("https://") or target_url.startswith("discord://")):
        if "." in target_url:
            target_url = "https://" + target_url

    try:
        if target_url.startswith("discord://"):
            # Deep links are best launched via PowerShell Start-Process
            ps_script = f'Start-Process "{target_url}"'
            return run_powershell(ps_script)

        success = webbrowser.open(target_url)
        return {
            "success": success,
            "opened_url": target_url,
            "message": f"Opened {target_url} in browser."
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "opened_url": target_url
        }


def open_app(name: str) -> Dict[str, Any]:
    """
    Launches an application or deep link.
    Checks shortcuts.json for apps, discord_servers, and folders.
    """
    shortcuts = load_shortcuts()
    name_clean = name.strip()
    name_lower = name_clean.lower()

    # Normalize common aliases for command prompt, terminals, and system tools
    app_aliases = {
        "cmd prompt": "cmd",
        "command prompt": "cmd",
        "cmd.exe": "cmd",
        "terminal": "cmd",
        "windows terminal": "wt",
        "wt": "wt",
        "powershell": "powershell",
        "file explorer": "explorer",
        "vs code": "code",
        "vscode": "code",
        "calculator": "calc",
        "task manager": "taskmgr",
        "taskmgr": "taskmgr",
    }
    if name_lower in app_aliases:
        name_clean = app_aliases[name_lower]
        name_lower = name_clean.lower()

    # 1. Check discord_servers shortcuts (e.g., "my server")
    discord_servers = shortcuts.get("discord_servers", {})
    for server_name, deep_link in discord_servers.items():
        if server_name.lower() in name_lower or name_lower in server_name.lower():
            ps_script = f'Start-Process "{deep_link}"'
            result = run_powershell(ps_script)
            result["shortcut"] = server_name
            result["deep_link"] = deep_link
            return result

    # 2. Check apps shortcuts
    apps = shortcuts.get("apps", {})
    if name_lower in apps:
        app_cmd = apps[name_lower]
        ps_script = f'Start-Process "{app_cmd}"'
        return run_powershell(ps_script)

    # 3. Check folders shortcuts
    folders = shortcuts.get("folders", {})
    if name_lower in folders:
        folder_path = os.path.expandvars(folders[name_lower])
        ps_script = f'explorer.exe "{folder_path}"'
        return run_powershell(ps_script)

    # 4. Fallback: try direct Start-Process
    ps_script = f'Start-Process "{name_clean}"'
    return run_powershell(ps_script)
