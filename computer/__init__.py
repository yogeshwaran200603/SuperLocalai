"""
SuperLocal Computer Mode Package
Advanced PC Operator Agent operating with strict permission boundaries:
- Tiered Screen State Engine: A11y Tree -> RapidOCR -> Vision
- Session Sandboxing & App Allowlists
- Web Friction Handling (popups, license audits, dangerous action blocking)
- Always-On-Top Overlay & 2-Second User Activity Interruption Monitor
- Action Dispatcher with 0.3s pauses and batch verification
"""

from pathlib import Path
from typing import Optional, Dict, Any, Union

from computer.permissions import ComputerSessionSandbox, ComputerPermissionManager
from computer.state_engine import ComputerStateEngine, ScreenState, UIElement
from computer.dispatcher import ActionDispatcher
from computer.friction import WebFrictionHandler
from computer.overlay import ComputerOverlayWindow, UserActivityMonitor
from computer.agent import ComputerModeAgent


def run_computer_mode(
    task: str,
    effort: Optional[str] = None,
    sandbox_dir: Optional[Union[str, Path]] = None,
    provider: Optional[Any] = None,
) -> Dict[str, Any]:
    """Runs a task in Computer Mode."""
    agent = ComputerModeAgent(task=task, effort=effort, sandbox_dir=sandbox_dir, provider=provider)
    return agent.execute()


__all__ = [
    "run_computer_mode",
    "ComputerModeAgent",
    "ComputerSessionSandbox",
    "ComputerPermissionManager",
    "ComputerStateEngine",
    "ScreenState",
    "UIElement",
    "ActionDispatcher",
    "WebFrictionHandler",
    "ComputerOverlayWindow",
    "UserActivityMonitor",
]
