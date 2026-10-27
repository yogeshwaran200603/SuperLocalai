"""
SuperLocal Voice Assistant: Spoken & Terminal Confirmation Module
Requires spoken confirmation ("yes, confirm") AND a visible console prompt for
dangerous operations (send, delete, pay, install, admin) with a 15-second timeout.
Pressing 'y' in the terminal also approves.
"""

import re
import time
import threading
from typing import Dict, Any, Tuple, Optional
from rich.console import Console
from rich.panel import Panel

try:
    import keyboard
except ImportError:
    keyboard = None

console = Console()

DANGEROUS_ACTION_KEYWORDS = [
    "send", "delete", "pay", "payment", "buy", "purchase",
    "install", "uninstall", "admin", "remove", "drop", "destroy", "format",
]


def is_dangerous_voice_action(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Evaluates whether an action falls into dangerous categories requiring
    spoken + visual two-factor confirmation.
    """
    args_str = str(args).lower()
    t_lower = tool_name.lower()

    if t_lower in ("file_delete", "whatsapp_send"):
        return True, f"High-risk action '{tool_name}' ({args})"

    if t_lower == "run_powershell":
        script = str(args.get("script", "")).lower()
        for kw in ("install", "del", "rmdir", "remove-item", "runas", "net user", "shutdown", "stop-computer"):
            if kw in script:
                return True, f"PowerShell command modifying system or software: {script[:80]}"

    for kw in DANGEROUS_ACTION_KEYWORDS:
        if kw in t_lower or kw in args_str:
            return True, f"Action containing sensitive keyword '{kw}': {tool_name}"

    return False, ""


def request_voice_confirmation(
    action_desc: str,
    tts=None,
    stt=None,
    record_func=None,
    timeout_sec: float = 15.0,
) -> bool:
    """
    Displays a visible prompt and prompts the user by voice.
    Accepts spoken 'yes, confirm' or pressing 'y' in the terminal.
    15-second timeout automatically cancels (counts as No).
    """
    console.print(Panel(
        f"[bold red]CONFIRMATION REQUIRED[/bold red]\n"
        f"{action_desc}\n\n"
        f"[yellow]Say [bold]'yes, confirm'[/bold] or press [bold]'y'[/bold] in terminal within 15 seconds.[/yellow]",
        title="Voice Safety Gate",
        border_style="red"
    ))

    if tts:
        tts.speak_now("Please say 'yes, confirm' or press y to proceed.")

    start_time = time.time()
    approved = False
    rejected = False

    while (time.time() - start_time) < timeout_sec:
        # 1. Check keyboard 'y' or 'n'
        if keyboard:
            try:
                if keyboard.is_pressed("y"):
                    approved = True
                    break
                if keyboard.is_pressed("n") or keyboard.is_pressed("esc"):
                    rejected = True
                    break
            except Exception:
                pass

        # 2. Check microphone input if record_func and stt are available
        if record_func and stt:
            audio_data = record_func(duration_sec=2.0)
            if audio_data:
                transcript, _, _ = stt.transcribe_pcm(audio_data)
                clean_t = transcript.lower().strip()
                if clean_t:
                    console.print(f"[dim]Heard confirmation candidate:[/dim] '{clean_t}'")
                    # Check for explicit approval
                    if any(phrase in clean_t for phrase in ("yes, confirm", "yes confirm", "confirm", "yes please", "proceed")):
                        approved = True
                        break
                    # Check for explicit refusal
                    if any(phrase in clean_t for phrase in ("no", "cancel", "stop", "quiet", "abort", "don't")):
                        rejected = True
                        break

        time.sleep(0.2)

    if approved:
        console.print("[bold green]Action confirmed.[/bold green]")
        if tts:
            tts.speak("Confirmed. Proceeding.")
        return True
    else:
        reason = "User rejected" if rejected else "Confirmation timed out (15s)"
        console.print(f"[bold red]Action cancelled ({reason}).[/bold red]")
        if tts:
            tts.speak("Action cancelled.")
        return False
