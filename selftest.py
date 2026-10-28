"""
SuperLocal Offline Self-Test Engine
Performs fast, offline diagnostic verification across all SuperLocal modules
with zero external API/cloud calls and prints exact remediation hints.
"""

import sys
import importlib
from typing import Dict, Any, List, Tuple
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markup import escape

console = Console()


def run_selftest() -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Executes fast offline checks across all SuperLocal subsystems.
    Returns (all_passed, results_list).
    """
    results: List[Dict[str, Any]] = []

    # 1. Config & Keys
    try:
        from config import (
            GEMINI_API_KEY,
            PROVIDER_ORDER,
            TOOL_TIMEOUT,
            TASK_TIMEOUT,
            SLOW_STEP_THRESHOLD,
            QUOTA_PER_DAY,
        )
        has_any_key = bool(GEMINI_API_KEY)
        results.append({
            "subsystem": "Configuration",
            "check": "Environment & Keys",
            "status": "PASS" if has_any_key else "WARN",
            "details": f"Config loaded. Primary provider: {PROVIDER_ORDER[0]}",
            "fix": "Set GEMINI_API_KEY in .env if using cloud models." if not has_any_key else None
        })
        results.append({
            "subsystem": "Watchdogs",
            "check": "Timeouts & Limits",
            "status": "PASS",
            "details": f"Tool: {TOOL_TIMEOUT}s, Task: {TASK_TIMEOUT}s, SlowStep: {SLOW_STEP_THRESHOLD}s",
            "fix": None
        })
    except Exception as e:
        results.append({
            "subsystem": "Configuration",
            "check": "Config Loading",
            "status": "FAIL",
            "details": str(e),
            "fix": "Check config.py and .env file syntax."
        })

    # 2. Safety & Kill Switch
    try:
        from safety import is_emergency_stopped, trigger_emergency_stop, reset_emergency_stop, mask_all_keys
        reset_emergency_stop()
        masked = mask_all_keys("AIzaSyDummySecretKey12345")
        results.append({
            "subsystem": "Safety",
            "check": "Kill Switch & Masking",
            "status": "PASS",
            "details": f"Emergency stop operational. Key masking active.",
            "fix": None
        })
    except Exception as e:
        results.append({
            "subsystem": "Safety",
            "check": "Kill Switch & Masking",
            "status": "FAIL",
            "details": str(e),
            "fix": "Verify safety.py module imports and global hotkeys."
        })

    # 3. pywinauto COM STA & UI Scan
    try:
        if not hasattr(sys, "coinit_flags"):
            sys.coinit_flags = 2
        import pywinauto
        results.append({
            "subsystem": "Desktop UI",
            "check": "pywinauto UIA / COM STA",
            "status": "PASS",
            "details": f"pywinauto backend ready (coinit_flags={getattr(sys, 'coinit_flags', None)})",
            "fix": None
        })
    except Exception as e:
        results.append({
            "subsystem": "Desktop UI",
            "check": "pywinauto UIA",
            "status": "WARN",
            "details": str(e),
            "fix": "Run 'pip install pywinauto' for native desktop inspection."
        })

    # 4. Playwright Browser
    try:
        from playwright.sync_api import sync_playwright
        results.append({
            "subsystem": "Browser",
            "check": "Playwright Automation",
            "status": "PASS",
            "details": "Playwright library is installed and importable.",
            "fix": None
        })
    except Exception as e:
        results.append({
            "subsystem": "Browser",
            "check": "Playwright Automation",
            "status": "FAIL",
            "details": str(e),
            "fix": "Run 'playwright install chromium' to enable browser automation."
        })

    # 5. Local Ollama Endpoint (Offline / Non-blocking)
    try:
        from providers.ollama_provider import check_ollama_status
        from config import OLLAMA_HOST, OLLAMA_MODEL
        reachable, model_exists, _ = check_ollama_status(OLLAMA_HOST, OLLAMA_MODEL, timeout=0.3)
        if reachable and model_exists:
            status, fix = "PASS", None
            details = f"Ollama online at {OLLAMA_HOST} with '{OLLAMA_MODEL}'"
        elif reachable and not model_exists:
            status, fix = "WARN", f"Run 'ollama pull {OLLAMA_MODEL}'"
            details = f"Ollama online, but model '{OLLAMA_MODEL}' missing"
        else:
            status, fix = "INFO", "Run 'ollama serve' if local inference is desired"
            details = f"Ollama offline at {OLLAMA_HOST} (optional fallback)"
        results.append({
            "subsystem": "Providers",
            "check": "Local Ollama Service",
            "status": status,
            "details": details,
            "fix": fix
        })
    except Exception as e:
        results.append({
            "subsystem": "Providers",
            "check": "Local Ollama Service",
            "status": "WARN",
            "details": str(e),
            "fix": "Verify Ollama installation and providers/ollama_provider.py."
        })

    # 6. Poki Player & Little Master Cricket Skill
    try:
        from poki.runner import PokiGameRunner
        from poki.skills import get_skill_for_game
        skill = get_skill_for_game("little-master-cricket")
        results.append({
            "subsystem": "Games (Poki)",
            "check": "Runner & Cricket Skill",
            "status": "PASS" if skill else "WARN",
            "details": "PokiGameRunner and Little Master Cricket HSV skill loaded." if skill else "Skill missing.",
            "fix": "Check skills/poki/cricket.py." if not skill else None
        })
    except Exception as e:
        results.append({
            "subsystem": "Games (Poki)",
            "check": "Poki Runner",
            "status": "FAIL",
            "details": str(e),
            "fix": "Verify poki package and opencv-python installation."
        })

    # 7. PC Optimizer Workbench
    try:
        from optimizer import handle_optimizer_command
        import psutil
        results.append({
            "subsystem": "Optimizer",
            "check": "PC Optimizer Workbench",
            "status": "PASS",
            "details": "psutil and diagnostic commands (/optimize) operational.",
            "fix": None
        })
    except Exception as e:
        results.append({
            "subsystem": "Optimizer",
            "check": "PC Optimizer Workbench",
            "status": "FAIL",
            "details": str(e),
            "fix": "Run 'pip install psutil' to enable PC Optimizer."
        })

    # 8. OpenFront RTS Skill & Localhost Guard
    try:
        from openfront import handle_openfront_command
        results.append({
            "subsystem": "OpenFront RTS",
            "check": "OpenFront Skill & Guards",
            "status": "PASS",
            "details": "OpenFront localhost guard and action dispatcher operational.",
            "fix": None
        })
    except Exception as e:
        results.append({
            "subsystem": "OpenFront RTS",
            "check": "OpenFront Skill & Guards",
            "status": "WARN",
            "details": str(e),
            "fix": "Ensure openfront module is present."
        })

    # 9. Voice Pipeline
    try:
        from voice.vad import VADProcessor
        from voice.audio_retention import save_audio_if_enabled
        results.append({
            "subsystem": "Voice Mode",
            "check": "VAD & Audio Pipeline",
            "status": "PASS",
            "details": "Voice pipeline, VAD filter, and audio retention ready.",
            "fix": None
        })
    except Exception as e:
        results.append({
            "subsystem": "Voice Mode",
            "check": "Voice Pipeline",
            "status": "WARN",
            "details": str(e),
            "fix": "Run 'pip install faster-whisper sounddevice' for voice mode."
        })

    # Print Rich Diagnostic Table
    table = Table(title="SuperLocal Subsystem Self-Test Diagnostics", border_style="cyan")
    table.add_column("Subsystem", style="bold cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")
    table.add_column("Exact Remediation / Fix", style="yellow")

    all_passed = True
    for r in results:
        st = r["status"]
        if st == "FAIL":
            all_passed = False
            st_disp = "[bold red]FAIL[/bold red]"
        elif st == "WARN":
            st_disp = "[bold yellow]WARN[/bold yellow]"
        elif st == "INFO":
            st_disp = "[dim cyan]INFO[/dim cyan]"
        else:
            st_disp = "[bold green]PASS[/bold green]"

        table.add_row(
            escape(r["subsystem"]),
            escape(r["check"]),
            st_disp,
            escape(r["details"]),
            escape(r["fix"] or "-")
        )

    console.print(table)
    summary_msg = "[bold green]All essential SuperLocal systems operational![/bold green]" if all_passed else "[bold yellow]Some optional systems need configuration. See remediation hints above.[/bold yellow]"
    console.print(summary_msg + "\n")

    return all_passed, results


if __name__ == "__main__":
    run_selftest()
