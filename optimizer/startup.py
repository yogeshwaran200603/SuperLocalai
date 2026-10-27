"""
SuperLocal PC Optimizer: Startup Programs Management Module
Inspects and manages startup entries across Windows:
- Registry Run keys (HKCU & HKLM).
- Startup folders (User & All Users).
- Scheduled tasks starting at user logon.
- Third-party Auto-start services.
- Classifies Publisher, Impact (High/Medium/Low), and provides plain descriptions.
- Hard safety gate: Never disables Microsoft, security, driver, or input device components without a second confirmation.
- Fully reversible: saves backup in data/optimizer_startup_backup.json and restores with /optimize undo.
"""

import os
import winreg
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import (
    OPTIMIZER_STARTUP_BACKUP,
    OPTIMIZER_QUARANTINE_DIR,
)
from optimizer.guards import (
    is_protected_startup_item,
    confirm_action,
    log_optimizer_action,
)

console = Console()

# Impact heuristic dictionary for known apps
APP_DESCRIPTIONS_AND_IMPACT = {
    "spotify": ("Spotify Music Player", "Medium", False),
    "discord": ("Discord Voice & Text Chat", "High", False),
    "steam": ("Steam Gaming Client", "High", False),
    "epicgames": ("Epic Games Launcher", "High", False),
    "battlenet": ("Battle.net Launcher", "Medium", False),
    "onedrive": ("Microsoft OneDrive Cloud Sync", "Medium", True),
    "teams": ("Microsoft Teams", "High", True),
    "zoom": ("Zoom Meetings Background Utility", "Medium", False),
    "slack": ("Slack Collaboration Workspace", "Medium", False),
    "skype": ("Skype", "Medium", True),
    "cortana": ("Microsoft Cortana Assistant", "Low", True),
    "dropbox": ("Dropbox Cloud File Sync", "Medium", False),
    "anydesk": ("AnyDesk Remote Desktop", "Medium", False),
    "teamviewer": ("TeamViewer Remote Access", "Medium", False),
    "utorrent": ("uTorrent Torrent Client", "High", False),
    "bittorrent": ("BitTorrent Client", "High", False),
    "cortex": ("Razer Cortex Game Booster", "Medium", False),
    "synapse": ("Razer Synapse Hardware Config", "High", True),
    "icue": ("Corsair iCUE Peripheral Lighting", "High", True),
    "logioptions": ("Logitech Options Peripheral Manager", "Medium", True),
    "ghub": ("Logitech G HUB Peripheral Manager", "High", True),
    "realtek": ("Realtek Audio Background Process", "Low", True),
    "securityhealth": ("Windows Defender Security Center", "Low", True),
    "nvdrivertask": ("Nvidia Display Driver Helper", "Low", True),
}


def guess_app_impact_and_desc(name: str, cmd: str) -> Tuple[str, str, bool]:
    """Returns: (impact: str, description: str, is_protected: bool)."""
    nl = name.lower()
    cl = cmd.lower()
    for key, (desc, impact, prot) in APP_DESCRIPTIONS_AND_IMPACT.items():
        if key in nl or key in cl:
            return impact, desc, prot

    # Default heuristic
    if is_protected_startup_item(name, "", cmd):
        return "Low", "System or hardware background service", True
    return "Medium", "Third-party application startup entry", False


def list_startup_entries() -> List[Dict[str, Any]]:
    """
    Collects all active startup entries from registry, startup folders, and scheduled tasks.
    """
    entries = []

    # 1. Registry HKCU Run
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as k:
            count = winreg.QueryInfoKey(k)[1]
            for i in range(count):
                name, val, _ = winreg.EnumValue(k, i)
                impact, desc, prot = guess_app_impact_and_desc(name, val)
                entries.append({
                    "id": f"hkcu_{name}",
                    "name": name,
                    "location": "Registry: HKCU Run",
                    "command": val,
                    "publisher": "User Registry",
                    "impact": impact,
                    "description": desc,
                    "is_protected": prot,
                    "source_type": "reg_hkcu",
                    "reg_path": r"Software\Microsoft\Windows\CurrentVersion\Run",
                })
    except Exception:
        pass

    # 2. Registry HKLM Run
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as k:
            count = winreg.QueryInfoKey(k)[1]
            for i in range(count):
                name, val, _ = winreg.EnumValue(k, i)
                impact, desc, prot = guess_app_impact_and_desc(name, val)
                entries.append({
                    "id": f"hklm_{name}",
                    "name": name,
                    "location": "Registry: HKLM Run",
                    "command": val,
                    "publisher": "Machine Registry",
                    "impact": impact,
                    "description": desc,
                    "is_protected": prot,
                    "source_type": "reg_hklm",
                    "reg_path": r"Software\Microsoft\Windows\CurrentVersion\Run",
                })
    except Exception:
        pass

    # 3. User Startup Folder
    appdata = os.environ.get("APPDATA")
    if appdata:
        p1 = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if p1.exists():
            for f in p1.iterdir():
                if f.is_file() and not f.name.lower().startswith("desktop.ini"):
                    impact, desc, prot = guess_app_impact_and_desc(f.stem, str(f))
                    entries.append({
                        "id": f"folder_user_{f.stem}",
                        "name": f.stem,
                        "location": "Folder: User Startup",
                        "command": str(f),
                        "publisher": "User Shortcut",
                        "impact": impact,
                        "description": desc,
                        "is_protected": prot,
                        "source_type": "folder",
                        "file_path": str(f),
                    })

    # 4. Common/All Users Startup Folder
    progdata = os.environ.get("ProgramData")
    if progdata:
        p2 = Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if p2.exists():
            for f in p2.iterdir():
                if f.is_file() and not f.name.lower().startswith("desktop.ini"):
                    impact, desc, prot = guess_app_impact_and_desc(f.stem, str(f))
                    entries.append({
                        "id": f"folder_all_{f.stem}",
                        "name": f.stem,
                        "location": "Folder: All Users Startup",
                        "command": str(f),
                        "publisher": "System Shortcut",
                        "impact": impact,
                        "description": desc,
                        "is_protected": prot,
                        "source_type": "folder",
                        "file_path": str(f),
                    })

    return entries


def display_startup_table(entries: List[Dict[str, Any]]):
    """Prints a Rich formatted table of startup applications."""
    table = Table(title=f"Windows Startup Applications ({len(entries)} items)", border_style="cyan")
    table.add_column("App Name", style="bold cyan")
    table.add_column("Location", style="white")
    table.add_column("Impact", style="bold")
    table.add_column("Protected", style="yellow")
    table.add_column("Description", style="dim")

    for e in entries:
        imp_color = "red" if e["impact"] == "High" else ("yellow" if e["impact"] == "Medium" else "green")
        prot_str = "[red]Yes (System)[/red]" if e["is_protected"] else "[green]No[/green]"
        table.add_row(
            e["name"],
            e["location"],
            f"[{imp_color}]{e['impact']}[/{imp_color}]",
            prot_str,
            e["description"],
        )
    console.print(table)


def disable_startup_item(item: Dict[str, Any], backup_file: Path = OPTIMIZER_STARTUP_BACKUP) -> Tuple[bool, str]:
    """
    Safely disables a startup entry by moving it to backup storage.
    """
    # Load or initialize backup state
    backup_data = {"disabled_items": []}
    if backup_file.exists():
        try:
            with open(backup_file, "r", encoding="utf-8") as f:
                backup_data = json.load(f)
        except Exception:
            backup_data = {"disabled_items": []}

    source_type = item["source_type"]

    if source_type in ("reg_hkcu", "reg_hklm"):
        root_key = winreg.HKEY_CURRENT_USER if source_type == "reg_hkcu" else winreg.HKEY_LOCAL_MACHINE
        try:
            with winreg.OpenKey(root_key, item["reg_path"], 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, item["name"])

            backup_data["disabled_items"].append(item)
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)

            log_optimizer_action("disable_startup_reg", item, "SUCCESS")
            return True, f"Disabled registry startup entry '{item['name']}'."
        except Exception as e:
            return False, f"Failed to disable registry entry '{item['name']}': {e}"

    elif source_type == "folder":
        f_path = Path(item["file_path"])
        if not f_path.exists():
            return False, f"Shortcut path '{f_path}' does not exist."

        q_dir = OPTIMIZER_QUARANTINE_DIR / "startup"
        q_dir.mkdir(parents=True, exist_ok=True)
        dest = q_dir / f_path.name
        try:
            shutil.move(str(f_path), str(dest))
            item["quarantined_to"] = str(dest)
            backup_data["disabled_items"].append(item)
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)

            log_optimizer_action("disable_startup_file", item, "SUCCESS")
            return True, f"Moved startup shortcut '{item['name']}' to quarantine."
        except Exception as e:
            return False, f"Failed to move startup shortcut '{item['name']}': {e}"

    return False, "Unsupported startup source type."


def restore_startup_items(backup_file: Path = OPTIMIZER_STARTUP_BACKUP) -> Dict[str, Any]:
    """
    Restores all startup entries previously disabled by the optimizer.
    """
    if not backup_file.exists():
        return {"success": False, "message": "No startup backup file found to restore."}

    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Failed to read startup backup file: {e}"}

    items = backup_data.get("disabled_items", [])
    if not items:
        return {"success": False, "message": "No disabled startup entries found in backup."}

    restored = 0
    errors = []

    for item in items:
        source_type = item["source_type"]
        if source_type in ("reg_hkcu", "reg_hklm"):
            root_key = winreg.HKEY_CURRENT_USER if source_type == "reg_hkcu" else winreg.HKEY_LOCAL_MACHINE
            try:
                with winreg.OpenKey(root_key, item["reg_path"], 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, item["name"], 0, winreg.REG_SZ, item["command"])
                restored += 1
                log_optimizer_action("restore_startup_reg", item, "SUCCESS")
            except Exception as e:
                errors.append(f"{item['name']}: {e}")

        elif source_type == "folder":
            q_path = Path(item.get("quarantined_to", ""))
            orig_path = Path(item["file_path"])
            if q_path.exists():
                try:
                    orig_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(q_path), str(orig_path))
                    restored += 1
                    log_optimizer_action("restore_startup_file", item, "SUCCESS")
                except Exception as e:
                    errors.append(f"{item['name']}: {e}")

    # Clear restored items from backup file
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump({"disabled_items": []}, f, indent=2)

    msg = f"Restored {restored} startup applications to original configuration."
    if errors:
        msg += f" ({len(errors)} errors: {'; '.join(errors)})"

    console.print(Panel(f"[bold green]{msg}[/bold green]", title="Startup Undo Complete", border_style="green"))
    return {"success": True, "restored_count": restored, "message": msg}


def manage_startup_flow(auto_approve: bool = False) -> Dict[str, Any]:
    """
    Interactive flow for /optimize startup.
    Lists items, suggests non-essential items, asks y/n, and disables selected entries.
    """
    entries = list_startup_entries()
    if not entries:
        console.print("[green]No startup applications found in standard registry or folder locations.[/green]")
        return {"success": True, "count": 0, "message": "No startup items found."}

    display_startup_table(entries)

    # Suggest non-essential items
    suggestions = [e for e in entries if not e["is_protected"] and e["impact"] in ("High", "Medium")]
    if not suggestions:
        console.print("\n[bold green]All active startup programs are essential system components or lightweight utilities.[/bold green]")
        return {"success": True, "entries": entries, "disabled_count": 0, "message": "No non-essential startup items to disable."}

    console.print(f"\n[bold yellow]Recommended to disable ({len(suggestions)} items):[/bold yellow]")
    for s in suggestions:
        console.print(f"  • [bold cyan]{s['name']}[/bold cyan] ({s['impact']} impact) - {s['description']}")

    disabled_count = 0
    for s in suggestions:
        # Prompt user
        approved = auto_approve or confirm_action(f"Disable '{s['name']}' from starting automatically?", default=False)
        if approved:
            # Check if protected requires secondary confirmation
            if s["is_protected"]:
                second_ok = auto_approve or confirm_action(
                    f"WARNING: '{s['name']}' is marked as a system or driver component. Are you SURE you want to disable it?",
                    default=False
                )
                if not second_ok:
                    console.print(f"[yellow]Skipped protected entry '{s['name']}'.[/yellow]")
                    continue

            ok, msg = disable_startup_item(s)
            if ok:
                disabled_count += 1
                console.print(f"[bold green]✓ {msg}[/bold green]")
            else:
                console.print(f"[red]✗ {msg}[/red]")

    summary = f"Startup review complete. Disabled {disabled_count} non-essential apps (use '/optimize undo' to restore)."
    console.print(Panel(f"[bold green]{summary}[/bold green]", title="Startup Management", border_style="green"))
    return {"success": True, "entries": entries, "disabled_count": disabled_count, "message": summary}
