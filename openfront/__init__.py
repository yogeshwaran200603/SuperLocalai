"""
SuperLocal OpenFront RTS Skill
Autonomous browser RTS agent for OpenFront.io.

Hard Safety Rules:
- Enforces strict origin guard: Only allows instances on http://localhost:* or http://127.0.0.1:*.
  Refuses public / external .io multiplayer servers.
- Single-player / local practice only.
"""

import re
from urllib.parse import urlparse
from typing import Dict, Any, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.markup import escape

console = Console()

ALLOWED_OPENFRONT_HOSTS = ("localhost", "127.0.0.1")


def validate_openfront_url(url: str) -> Tuple[bool, str]:
    """
    Validates that OpenFront URL is strictly on localhost / 127.0.0.1.
    Refuses multiplayer, public .io, or remote domains.
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname not in ALLOWED_OPENFRONT_HOSTS:
            return False, (
                f"Security Guard: Target URL '{url}' is not a local host. "
                f"SuperLocal plays OpenFront ONLY on localhost (http://localhost:* or http://127.0.0.1:*). "
                f"Connecting to public multiplayer servers is prohibited."
            )
        return True, "Valid localhost origin."
    except Exception as e:
        return False, f"Invalid URL format: {e}"


def handle_openfront_command(command: str) -> str:
    """
    Dispatches /openfront commands:
    /openfront launch [url]
    /openfront play [url]
    /openfront status
    /openfront stop
    """
    from openfront.runner import OpenFrontRunner

    cmd_clean = command.strip()
    parts = cmd_clean.split(maxsplit=2)
    sub = parts[1].lower() if len(parts) > 1 else "play"

    runner = OpenFrontRunner()

    if sub in ("launch", "play"):
        url = parts[2].strip() if len(parts) > 2 else "http://localhost:8080"
        valid, reason = validate_openfront_url(url)
        if not valid:
            console.print(f"[bold red]{reason}[/bold red]")
            return reason

        console.print(f"[bold cyan]Launching OpenFront RTS agent on {url}...[/bold cyan]")
        return runner.play(url=url)

    elif sub == "status":
        return runner.get_status()

    elif sub == "stop":
        return runner.stop()

    else:
        return "Usage: /openfront play [http://localhost:8080] | /openfront status | /openfront stop"
