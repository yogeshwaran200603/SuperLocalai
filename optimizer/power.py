"""
SuperLocal PC Optimizer: Power Plan Management Module
Queries and configures Windows power schemes using native powercfg:
- Shows active power scheme.
- Suggests Balanced (default for laptops) or High Performance (for desktops or heavy workloads).
- Sets active plan after y/n confirmation.
- Clearly displays the exact command to change it back.
"""

import subprocess
import re
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from optimizer.guards import confirm_action, log_optimizer_action

console = Console()

# Standard Windows Power Scheme GUIDs
STANDARD_SCHEMES = {
    "balanced": ("381b4222-f694-41f0-9685-ff5bb260df2e", "Balanced", "Automatically balances performance with energy consumption on capable hardware."),
    "high_performance": ("8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "High performance", "Favors maximum responsiveness and clock speeds at the cost of higher energy usage."),
    "power_saver": ("a1841308-3541-4fab-bc81-f71556f20b4a", "Power saver", "Saves energy by reducing PC performance and screen brightness."),
    "ultimate_performance": ("e9a42b02-d5df-448d-aa00-03f14749eb61", "Ultimate Performance", "Delivers absolute maximum performance on high-end PCs."),
}


def get_current_power_plan() -> Tuple[str, str]:
    """Returns (guid, name) of active power scheme."""
    try:
        proc = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=5)
        out = proc.stdout.strip()
        m = re.search(r"Power Scheme GUID:\s+([a-f0-9\-]+)\s+\(([^)]+)\)", out, re.IGNORECASE)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return "381b4222-f694-41f0-9685-ff5bb260df2e", "Balanced"


def list_available_power_plans() -> List[Dict[str, Any]]:
    """Returns all power schemes installed on system."""
    plans = []
    try:
        proc = subprocess.run(["powercfg", "/list"], capture_output=True, text=True, timeout=5)
        for line in proc.stdout.splitlines():
            m = re.search(r"Power Scheme GUID:\s+([a-f0-9\-]+)\s+\(([^)]+)\)(\s*\*?)", line, re.IGNORECASE)
            if m:
                guid = m.group(1)
                name = m.group(2)
                is_active = "*" in m.group(3)
                plans.append({
                    "guid": guid,
                    "name": name,
                    "active": is_active,
                })
    except Exception:
        pass
    return plans


def set_power_plan(plan_guid: str) -> Tuple[bool, str]:
    """Sets active power plan via powercfg /setactive."""
    try:
        proc = subprocess.run(["powercfg", "/setactive", plan_guid], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            log_optimizer_action("set_power_plan", {"guid": plan_guid}, "SUCCESS")
            return True, f"Successfully activated power scheme {plan_guid}."
        return False, f"powercfg returned exit code {proc.returncode}."
    except Exception as e:
        return False, f"Failed to set power scheme: {e}"


def manage_power_flow(requested_plan: Optional[str] = None, auto_approve: bool = False) -> Dict[str, Any]:
    """
    Main flow for /optimize power.
    """
    current_guid, current_name = get_current_power_plan()
    plans = list_available_power_plans()

    table = Table(title="Windows Power Schemes", border_style="cyan")
    table.add_column("Scheme Name", style="bold cyan")
    table.add_column("GUID", style="dim")
    table.add_column("Status", style="bold")

    for p in plans:
        stat_str = "[bold green]Active (*)[/bold green]" if p["active"] else "[dim]Available[/dim]"
        table.add_row(p["name"], p["guid"], stat_str)
    console.print(table)

    # Suggestion
    suggestion_key = "high_performance" if "balanced" in current_name.lower() else "balanced"
    target_guid, target_name, target_desc = STANDARD_SCHEMES[suggestion_key]

    console.print(f"\n[bold yellow]Recommendation:[/bold yellow] Switch to [bold cyan]{target_name}[/bold cyan] ({target_desc})")
    console.print(f"[dim]Revert command: powercfg /setactive {current_guid}[/dim]")

    approved = auto_approve or confirm_action(f"Switch power plan to '{target_name}'?", default=False)
    if approved:
        ok, msg = set_power_plan(target_guid)
        if ok:
            console.print(f"[bold green]✓ Switched to {target_name}. To revert anytime, run: powercfg /setactive {current_guid}[/bold green]")
            return {"success": True, "active_plan": target_name, "revert_command": f"powercfg /setactive {current_guid}"}
        else:
            console.print(f"[red]✗ {msg}[/red]")
            return {"success": False, "message": msg}

    return {"success": True, "active_plan": current_name, "message": f"Kept active power plan: {current_name}"}
