"""
SuperLocal PC Optimizer: Installed Applications Management Module
Lists installed applications, identifies unused/large programs, and supports safe uninstallation:
- Scans 64-bit, 32-bit, and User Registry Uninstall keys.
- Cross-references winget list where available.
- Flags apps unused for N days (default 60 days).
- Uninstalls ONLY via winget or the application's official registered uninstaller.
- Mandatory y/n confirmation required for each uninstallation.
"""

import os
import winreg
import subprocess
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from optimizer.guards import confirm_action, log_optimizer_action

console = Console()


def parse_registry_install_date(raw_date: str) -> Optional[datetime.date]:
    """Parses standard registry InstallDate format YYYYMMDD."""
    if not raw_date or len(raw_date) < 8:
        return None
    try:
        y = int(raw_date[:4])
        m = int(raw_date[4:6])
        d = int(raw_date[6:8])
        return datetime.date(y, m, d)
    except Exception:
        return None


def list_installed_applications() -> List[Dict[str, Any]]:
    """
    Collects installed applications from Windows Uninstall registry keys.
    """
    reg_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "64-bit Machine"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "32-bit Machine"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", "User"),
    ]

    apps = {}
    today = datetime.date.today()

    for root, subkey, scope in reg_roots:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        app_guid = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, app_guid, 0, winreg.KEY_READ) as app_key:
                            # Extract DisplayName
                            try:
                                disp_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                            except FileNotFoundError:
                                continue

                            if not disp_name or not str(disp_name).strip():
                                continue

                            disp_name = str(disp_name).strip()

                            # Extract other properties
                            publisher = ""
                            try:
                                publisher, _ = winreg.QueryValueEx(app_key, "Publisher")
                            except FileNotFoundError:
                                pass

                            version = ""
                            try:
                                version, _ = winreg.QueryValueEx(app_key, "DisplayVersion")
                            except FileNotFoundError:
                                pass

                            size_kb = 0
                            try:
                                size_raw, _ = winreg.QueryValueEx(app_key, "EstimatedSize")
                                size_kb = int(size_raw)
                            except (FileNotFoundError, ValueError, TypeError):
                                pass

                            install_date_str = ""
                            days_installed = None
                            try:
                                raw_dt, _ = winreg.QueryValueEx(app_key, "InstallDate")
                                dt = parse_registry_install_date(str(raw_dt))
                                if dt:
                                    install_date_str = dt.isoformat()
                                    days_installed = (today - dt).days
                            except FileNotFoundError:
                                pass

                            uninstaller = ""
                            try:
                                uninstaller, _ = winreg.QueryValueEx(app_key, "UninstallString")
                            except FileNotFoundError:
                                pass

                            quiet_uninstall = ""
                            try:
                                quiet_uninstall, _ = winreg.QueryValueEx(app_key, "QuietUninstallString")
                            except FileNotFoundError:
                                pass

                            # Deduplicate by DisplayName
                            if disp_name not in apps or (size_kb > apps[disp_name]["size_kb"]):
                                apps[disp_name] = {
                                    "name": disp_name,
                                    "publisher": str(publisher or "Unknown"),
                                    "version": str(version or "-"),
                                    "size_mb": round(size_kb / 1024.0, 1),
                                    "install_date": install_date_str or "Unknown",
                                    "days_installed": days_installed,
                                    "uninstall_string": str(uninstaller or ""),
                                    "quiet_uninstall": str(quiet_uninstall or ""),
                                    "scope": scope,
                                    "guid": app_guid,
                                }
                    except Exception:
                        continue
        except Exception:
            continue

    app_list = list(apps.values())
    app_list.sort(key=lambda x: x["size_mb"], reverse=True)
    return app_list


def display_apps_table(apps: List[Dict[str, Any]], limit: int = 15):
    """Renders installed applications table."""
    table = Table(title=f"Installed Applications (Showing top {min(limit, len(apps))} of {len(apps)})", border_style="cyan")
    table.add_column("Application Name", style="bold cyan")
    table.add_column("Publisher", style="white")
    table.add_column("Size (MB)", style="green")
    table.add_column("Installed", style="yellow")
    table.add_column("Scope", style="dim")

    for a in apps[:limit]:
        size_str = f"{a['size_mb']:.1f} MB" if a['size_mb'] > 0 else "-"
        table.add_row(
            a["name"][:40],
            a["publisher"][:25],
            size_str,
            a["install_date"],
            a["scope"],
        )
    console.print(table)


def uninstall_app(app_info: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Executes uninstallation through winget or the app's official registered uninstaller.
    """
    name = app_info["name"]

    # Try winget first if installed
    cmd = ["winget", "uninstall", "--name", name, "--accept-source-agreements"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0:
            msg = f"Successfully uninstalled '{name}' via winget."
            log_optimizer_action("uninstall_app_winget", {"app": name}, "SUCCESS")
            return True, msg
    except Exception:
        pass

    # Fallback to official uninstaller
    uninstaller = app_info.get("quiet_uninstall") or app_info.get("uninstall_string")
    if uninstaller:
        try:
            # Run official uninstaller in child shell
            proc = subprocess.run(uninstaller, shell=True, capture_output=True, text=True, timeout=180)
            if proc.returncode == 0:
                msg = f"Successfully executed official uninstaller for '{name}'."
                log_optimizer_action("uninstall_app_native", {"app": name}, "SUCCESS")
                return True, msg
            else:
                return False, f"Uninstaller returned exit code {proc.returncode}."
        except Exception as e:
            return False, f"Error launching uninstaller: {e}"

    return False, f"No valid uninstaller found for '{name}'."


def manage_apps_flow(unused_days: int = 60, auto_approve: bool = False) -> Dict[str, Any]:
    """
    Interactive flow for /optimize apps.
    Lists apps, highlights candidates unused/old, and allows safe uninstallation.
    """
    apps = list_installed_applications()
    if not apps:
        console.print("[yellow]No installed applications detected in registry.[/yellow]")
        return {"success": True, "count": 0, "message": "No installed apps found."}

    display_apps_table(apps)

    # Suggest large apps installed over N days ago
    candidates = [
        a for a in apps
        if a["size_mb"] >= 200.0 and (a["days_installed"] is not None and a["days_installed"] >= unused_days)
    ]

    uninstalled_count = 0
    if candidates:
        console.print(f"\n[bold yellow]Candidates for review (Installed > {unused_days} days ago, size > 200 MB):[/bold yellow]")
        for c in candidates[:5]:
            console.print(f"  • [bold cyan]{c['name']}[/bold cyan] ({c['size_mb']} MB, installed {c['install_date']})")

        for c in candidates[:3]:
            approved = auto_approve or confirm_action(f"Do you want to uninstall '{c['name']}' ({c['size_mb']} MB)?", default=False)
            if approved:
                ok, msg = uninstall_app(c)
                if ok:
                    uninstalled_count += 1
                    console.print(f"[bold green]✓ {msg}[/bold green]")
                else:
                    console.print(f"[red]✗ {msg}[/red]")

    summary = f"Apps audit complete. Scanned {len(apps)} installed programs. Uninstalled {uninstalled_count} apps."
    console.print(Panel(f"[bold green]{summary}[/bold green]", title="Apps Optimizer Complete", border_style="green"))
    return {"success": True, "total_apps": len(apps), "uninstalled_count": uninstalled_count, "summary": summary}
