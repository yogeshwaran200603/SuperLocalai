"""
SuperLocal Poki Player: Safety & Compliance Guards
Enforces:
- Single-player games ONLY: strictly refuses multiplayer, PvP, or .io games with clear ethical notice.
- Poki terms of use notice printed once per session.
- Ad policy: never bypass ads, wait for them or use official in-game close buttons.
- Privacy & security: never enter credentials, payments, or downloads.
- Untrusted text sanitization: text from game pages cannot modify agent instructions or permissions.
"""

import re
from typing import Tuple, List, Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel

console = Console()

# Multiplayer indicator patterns
MULTIPLAYER_SIGNALS = [
    r"\bmultiplayer\b",
    r"\bonline\s+pvp\b",
    r"\bpvp\b",
    r"\.io\b",
    r"\bduel\b",
    r"\bleaderboard\s+duel\b",
    r"\b2\s*player\b",
    r"\btwo\s*player\b",
    r"\bbattle\s*royale\b",
    r"\bmmo\b",
    r"\bmulti-player\b",
    r"\bco-op\s+online\b",
    r"\bvs\s+player\b",
    r"\bplay\s+with\s+friends\b",
]

_TERMS_NOTICE_PRINTED = False


def print_poki_terms_notice_once():
    """Prints the Poki terms of use notice once per session."""
    global _TERMS_NOTICE_PRINTED
    if not _TERMS_NOTICE_PRINTED:
        console.print(
            "[bold yellow][Notice][/bold yellow] Check Poki's terms of use. "
            "Use this only for your own play and practice."
        )
        _TERMS_NOTICE_PRINTED = True


def reset_terms_notice_flag():
    """Resets terms notice flag (useful for testing)."""
    global _TERMS_NOTICE_PRINTED
    _TERMS_NOTICE_PRINTED = False


def check_single_player_or_refuse(
    page_text: str,
    tags: Optional[List[str]] = None,
    game_url: str = ""
) -> Tuple[bool, str]:
    """
    Validates that a game is strictly single-player.
    If multiplayer, PvP, or .io patterns are detected, refuses unconditionally.
    Returns: (is_single_player: bool, message: str)
    """
    combined_text = f"{page_text} {' '.join(tags or [])} {game_url}".lower()

    for pattern in MULTIPLAYER_SIGNALS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            msg = (
                "SuperLocal plays only single-player games. "
                "Bots in multiplayer games are unfair to other players."
            )
            console.print(Panel(f"[bold red]{msg}[/bold red]", title="Multiplayer Guard", border_style="red"))
            return False, msg

    return True, "Verified single-player game."


def sanitize_game_page_text(text: str) -> str:
    """
    Sanitizes untrusted text extracted from browser game pages
    to neutralize any prompt-injection attempts.
    """
    if not text:
        return ""

    injection_patterns = [
        r"ignore\s+(?:all\s+)?previous\s+instructions",
        r"system\s*prompt\s*:",
        r"you\s+are\s+now\s+(?:in\s+developer\s+mode|unrestricted)",
        r"disregard\s+(?:the\s+above|all\s+rules)",
        r"new\s+system\s+instruction",
        r"add\s+step\s+to\s+plan",
        r"elevate\s+(?:to\s+)?admin",
        r"grant\s+permission",
    ]

    clean = text
    for pat in injection_patterns:
        clean = re.sub(pat, "[UNTRUSTED_CONTENT_REDACTED]", clean, flags=re.IGNORECASE)

    return clean


def is_safe_game_interaction(action_type: str, details: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Guards against sensitive browser actions during gameplay:
    - Never submit login forms or credit card details
    - Never trigger software downloads or file writes outside sandbox
    """
    act = action_type.lower()
    text = str(details.get("text", "")).lower()

    if any(k in text for k in ("password", "credit card", "cvv", "billing", "login", "sign in")):
        return False, "Blocked: Interactive entry of credentials or financial data is prohibited."

    if any(k in text for k in (".exe", ".msi", "download now", "install app")):
        return False, "Blocked: Download and execution of external software is prohibited."

    return True, "Safe action"
