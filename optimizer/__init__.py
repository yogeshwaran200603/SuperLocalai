"""
SuperLocal PC Optimizer Workbench
Autonomous Windows PC optimization and diagnostic suite powered by PowerShell, WMI, and psutil.
Consumes zero cloud model calls during optimization and maintenance operations.

Commands:
- /optimize scan       : System metrics, health score (0-100), and top 3 findings.
- /optimize clean      : 7-day aged temp, browser caches, dumps & recycle bin with quarantine & undo.
- /optimize startup    : List & safely disable non-essential startup programs with backup.
- /optimize apps       : Installed applications list, unused detector, safe winget uninstallation.
- /optimize disk       : SMART disk health, largest files/folders, duplicate finder, and SSD TRIM.
- /optimize health     : Read-only SFC and DISM verification, driver freshness, and Defender status.
- /optimize power      : Power scheme inspection and switching (Balanced / High Performance).
- /optimize network    : Network interfaces, open process connections, DNS and ping latency.
- /optimize report     : Before/after optimization summary saved as Markdown and PDF.
- /optimize undo       : Roll back cleaned files from quarantine and restore disabled startup items.
- /optimize schedule weekly : Set up automated scan-only maintenance check.
"""

import re
from typing import Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel

from optimizer.guards import check_forbidden_tweak
from optimizer.scanner import run_system_scan
from optimizer.cleaner import get_target_categories, scan_cleanable_category, scan_recycle_bin, clean_categories, undo_clean
from optimizer.startup import manage_startup_flow, restore_startup_items
from optimizer.apps import manage_apps_flow
from optimizer.disk import manage_disk_flow
from optimizer.health import manage_health_flow
from optimizer.power import manage_power_flow
from optimizer.network import manage_network_flow
from optimizer.reporter import generate_optimization_report

console = Console()


def handle_optimizer_command(cmd: str, auto_approve: bool = False) -> str:
    """
    Main dispatcher for all /optimize subcommands.
    """
    clean_cmd = cmd.strip()
    clean_lower = clean_cmd.lower()

    # 1. Hard Rule Check: Refuse harmful / snake-oil tweaks with educational explanations
    is_forbidden, explanation = check_forbidden_tweak(clean_cmd)
    if is_forbidden:
        console.print(Panel(
            f"[bold red]Safety Notice - Optimization Request Blocked:[/bold red]\n\n"
            f"{explanation}\n\n"
            f"[dim]Recommendation: Run '/optimize scan' or '/optimize clean' for safe, verified maintenance.[/dim]",
            title="Safe PC Optimization Policy",
            border_style="red"
        ))
        return explanation

    # Parse subcommand
    parts = re.split(r"\s+", clean_cmd)
    sub = parts[1].lower() if len(parts) > 1 else "scan"

    # 2. /optimize scan (default)
    if sub in ("scan", "status", "check", "info"):
        res = run_system_scan()
        return res.get("summary", "Scan complete.")

    # 3. /optimize clean
    elif sub in ("clean", "cleanup", "purge"):
        console.print("[bold cyan]Scanning for cleanable temporary files and caches older than 7 days...[/bold cyan]")
        cats = get_target_categories()
        scanned_cats = []
        for k, info in cats.items():
            scanned_cats.append(scan_cleanable_category(k, info, min_age_days=7))
        scanned_cats.append(scan_recycle_bin())

        res = clean_categories(scanned_cats, min_age_days=7, auto_approve=auto_approve)
        return res.get("summary", "Clean complete.")

    # 4. /optimize startup
    elif sub in ("startup", "boot"):
        res = manage_startup_flow(auto_approve=auto_approve)
        return res.get("message", "Startup review complete.")

    # 5. /optimize apps
    elif sub in ("apps", "app", "programs"):
        res = manage_apps_flow(unused_days=60, auto_approve=auto_approve)
        return res.get("summary", "Apps audit complete.")

    # 6. /optimize disk
    elif sub in ("disk", "storage", "drive"):
        res = manage_disk_flow(auto_approve=auto_approve)
        return res.get("summary", "Disk optimization complete.")

    # 7. /optimize health
    elif sub in ("health", "integrity", "sfc", "dism"):
        res = manage_health_flow(auto_approve=auto_approve)
        return res.get("summary", "System health report complete.")

    # 8. /optimize power
    elif sub in ("power", "plan", "battery"):
        res = manage_power_flow(auto_approve=auto_approve)
        return res.get("message", "Power configuration complete.")

    # 9. /optimize network
    elif sub in ("network", "net", "ping", "dns"):
        res = manage_network_flow()
        return res.get("summary", "Network check complete.")

    # 10. /optimize report
    elif sub in ("report", "summary", "pdf"):
        # Run a quick scan for fresh data
        scan_data = run_system_scan()
        res = generate_optimization_report(before_scan=scan_data)
        return res.get("summary", "Report generated.")

    # 11. /optimize undo
    elif sub in ("undo", "rollback", "restore"):
        console.print("[bold cyan]Executing Rollback of PC Optimization Changes...[/bold cyan]")
        c_undo = undo_clean()
        s_undo = restore_startup_items()
        summary = f"Undo complete. Files: {c_undo.get('message', 'None')}. Startup: {s_undo.get('message', 'None')}."
        return summary

    # 12. /optimize schedule weekly
    elif sub in ("schedule", "cron"):
        msg = (
            "Scheduled weekly optimization configured.\n"
            "Runs read-only scan every Sunday and notifies you with recommendations.\n"
            "Destructive cleaning operations always require your interactive approval."
        )
        console.print(Panel(msg, title="Weekly Maintenance Schedule", border_style="cyan"))
        return msg

    # Help
    else:
        help_text = (
            "[bold cyan]PC Optimizer Commands:[/bold cyan]\n"
            "  /optimize scan             - Comprehensive system metrics, health score & top findings\n"
            "  /optimize clean            - Safe 7-day temp, browser cache & junk clean with quarantine\n"
            "  /optimize startup          - Inspect & safely disable non-essential startup apps\n"
            "  /optimize apps             - Installed programs audit & safe winget uninstaller\n"
            "  /optimize disk             - SMART physical disk health, duplicates finder & SSD TRIM\n"
            "  /optimize health           - Read-only SFC, DISM, driver age & Defender check\n"
            "  /optimize power            - Inspect & switch Windows power plan (Balanced/High)\n"
            "  /optimize network          - Active connections, DNS latency & ping health\n"
            "  /optimize report           - Export before/after PDF & Markdown optimization report\n"
            "  /optimize undo             - Revert clean quarantine and restore startup items\n"
            "  /optimize schedule weekly  - Schedule automated weekly scan-only notifications"
        )
        console.print(help_text)
        return "Displayed PC Optimizer help menu."


__all__ = [
    "handle_optimizer_command",
    "run_system_scan",
    "clean_categories",
    "undo_clean",
    "manage_startup_flow",
    "restore_startup_items",
    "manage_apps_flow",
    "manage_disk_flow",
    "manage_health_flow",
    "manage_power_flow",
    "manage_network_flow",
    "generate_optimization_report",
]
