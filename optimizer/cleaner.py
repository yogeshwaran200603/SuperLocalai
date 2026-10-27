"""
SuperLocal PC Optimizer: System Cleaner & Quarantine Module
Handles safe cleanup with 7-day age filtering and reversible quarantine:
- User & Windows Temp files.
- Browser caches (Chrome, Edge, Firefox - strictly cache only, NEVER passwords, cookies, or history).
- Thumbnail cache & icon cache.
- Windows Update downloaded installation leftovers.
- Crash dumps & Recycle Bin.
- Skips locked/in-use files.
- Moves files to data/optimizer_quarantine/<timestamp>/ so /optimize undo can restore them.
- Detailed audit logging to logs/optimizer.log.
"""

import os
import shutil
import time
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import (
    OPTIMIZER_CLEAN_MIN_AGE_DAYS,
    OPTIMIZER_QUARANTINE_DIR,
    OPTIMIZER_LOG_PATH,
)
from optimizer.guards import (
    is_safe_optimizer_path,
    confirm_action,
    log_optimizer_action,
)

console = Console()


def get_file_age_days(file_path: Path) -> float:
    """Returns the age of a file in days based on last modification time."""
    try:
        mtime = file_path.stat().st_mtime
        return (time.time() - mtime) / 86400.0
    except Exception:
        return 0.0


def format_bytes(bytes_count: int) -> str:
    """Formats bytes into human readable KB, MB, or GB."""
    if bytes_count >= 1024**3:
        return f"{bytes_count / (1024**3):.2f} GB"
    elif bytes_count >= 1024**2:
        return f"{bytes_count / (1024**2):.1f} MB"
    elif bytes_count >= 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count} bytes"


def get_target_categories(min_age_days: int = OPTIMIZER_CLEAN_MIN_AGE_DAYS) -> Dict[str, Dict[str, Any]]:
    """
    Identifies cleanable targets across supported categories.
    Ensures browser logins, cookies, and history are NEVER included.
    """
    local_app_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    app_data = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    user_temp = Path(os.environ.get("TEMP", str(local_app_data / "Temp")))
    win_temp = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "Temp"
    win_update_download = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "SoftwareDistribution" / "Download"
    crash_dumps = local_app_data / "CrashDumps"

    categories = {
        "user_temp": {
            "name": "User Temporary Files",
            "paths": [user_temp],
            "description": "Old scratch files left behind by running user applications.",
            "pattern": "*",
            "recursive": True,
        },
        "windows_temp": {
            "name": "Windows System Temp",
            "paths": [win_temp],
            "description": "Temporary setup and service files in Windows Temp.",
            "pattern": "*",
            "recursive": True,
        },
        "browser_cache": {
            "name": "Web Browser Caches (Cache Only)",
            "paths": [
                local_app_data / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                local_app_data / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache",
                local_app_data / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
                local_app_data / "Microsoft" / "Edge" / "User Data" / "Default" / "Code Cache",
            ],
            "description": "Cached web images, fonts, and scripts. (Passwords, cookies, and history are NEVER touched).",
            "pattern": "*",
            "recursive": True,
        },
        "thumbnails": {
            "name": "Thumbnail & Icon Cache",
            "paths": [local_app_data / "Microsoft" / "Windows" / "Explorer"],
            "description": "Explorer image thumbnail database files.",
            "pattern": "thumbcache_*.db",
            "recursive": False,
        },
        "windows_update": {
            "name": "Windows Update Leftovers",
            "paths": [win_update_download],
            "description": "Downloaded installation patch files already applied.",
            "pattern": "*",
            "recursive": True,
        },
        "crash_dumps": {
            "name": "Application Crash Dumps",
            "paths": [crash_dumps],
            "description": "Memory dump files (.dmp) saved during software crashes.",
            "pattern": "*.dmp",
            "recursive": False,
        },
    }

    # Add Firefox profile cache if present
    ff_profiles = local_app_data / "Mozilla" / "Firefox" / "Profiles"
    if ff_profiles.exists():
        try:
            for p_dir in ff_profiles.iterdir():
                c2 = p_dir / "cache2"
                if c2.exists():
                    categories["browser_cache"]["paths"].append(c2)
        except Exception:
            pass

    return categories


def scan_cleanable_category(cat_key: str, cat_info: Dict[str, Any], min_age_days: int) -> Dict[str, Any]:
    """
    Scans a single category and collects files older than min_age_days.
    """
    found_files = []
    total_bytes = 0

    for base_path in cat_info["paths"]:
        if not base_path.exists():
            continue

        try:
            if cat_info.get("recursive", True):
                candidates = base_path.rglob(cat_info.get("pattern", "*"))
            else:
                candidates = base_path.glob(cat_info.get("pattern", "*"))

            for f in candidates:
                if f.is_file():
                    # Filter by age
                    age_days = get_file_age_days(f)
                    if age_days >= min_age_days:
                        try:
                            size = f.stat().st_size
                            found_files.append({
                                "path": str(f),
                                "size": size,
                                "age_days": round(age_days, 1),
                            })
                            total_bytes += size
                        except Exception:
                            continue
        except Exception:
            continue

    return {
        "key": cat_key,
        "name": cat_info["name"],
        "description": cat_info["description"],
        "file_count": len(found_files),
        "total_bytes": total_bytes,
        "files": found_files,
    }


def scan_recycle_bin() -> Dict[str, Any]:
    """
    Queries Windows Recycle Bin size and item count via PowerShell.
    """
    import subprocess
    cmd = [
        "powershell", "-NoProfile", "-Command",
        "$rb = (New-Object -ComObject Shell.Application).NameSpace(0xa); "
        "$count = $rb.Items().Count; "
        "$bytes = 0; foreach ($i in $rb.Items()) { $bytes += $i.Size }; "
        "Write-Output \"$count|$bytes\""
    ]
    count = 0
    total_bytes = 0
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if proc.returncode == 0 and "|" in proc.stdout:
            parts = proc.stdout.strip().split("|")
            count = int(parts[0])
            total_bytes = int(parts[1])
    except Exception:
        pass

    return {
        "key": "recycle_bin",
        "name": "Windows Recycle Bin",
        "description": "Deleted items in the user Recycle Bin.",
        "file_count": count,
        "total_bytes": total_bytes,
        "files": [],
    }


def quarantine_and_delete_file(file_path: Path, quarantine_session_dir: Path) -> Tuple[bool, Optional[str]]:
    """
    Moves a file to the quarantine directory to allow /optimize undo.
    If moving fails (e.g., cross-device or permission), attempts direct safe deletion.
    Returns: (success: bool, quarantined_rel_path: Optional[str])
    """
    try:
        # Create a unique quarantine subpath preserving basename
        ts = int(time.time() * 1000)
        safe_rel_name = f"{ts}_{file_path.name}"
        target_dest = quarantine_session_dir / safe_rel_name

        shutil.move(str(file_path), str(target_dest))
        return True, safe_rel_name
    except Exception:
        # File might be locked or in-use
        return False, None


def clean_categories(
    categories_to_clean: List[Dict[str, Any]],
    min_age_days: int = OPTIMIZER_CLEAN_MIN_AGE_DAYS,
    auto_approve: bool = False
) -> Dict[str, Any]:
    """
    Iterates through scanned categories, presents preview, prompts y/n, and performs quarantine.
    """
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_quarantine = OPTIMIZER_QUARANTINE_DIR / session_id
    session_quarantine.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    total_freed_bytes = 0
    total_cleaned_files = 0
    cleaned_categories_summary = []

    for cat in categories_to_clean:
        if cat["file_count"] == 0:
            continue

        cat_name = cat["name"]
        cat_key = cat["key"]
        cat_size_str = format_bytes(cat["total_bytes"])

        console.print(f"\n[bold cyan]Category:[/bold cyan] {cat_name} ({cat['file_count']} items, {cat_size_str})")
        console.print(f"[dim]{cat['description']}[/dim]")

        # Show preview of first 5 items
        if cat["files"]:
            preview_table = Table(title=f"Preview (First {min(5, len(cat['files']))} items)", border_style="dim")
            preview_table.add_column("File Path", style="dim", max_width=60)
            preview_table.add_column("Size", style="green")
            preview_table.add_column("Age", style="yellow")
            for item in cat["files"][:5]:
                preview_table.add_row(item["path"], format_bytes(item["size"]), f"{item['age_days']} days")
            console.print(preview_table)

        # Confirm per category
        prompt = f"Clean {cat_name} ({cat_size_str})? (Items older than {min_age_days} days)"
        approved = auto_approve or confirm_action(prompt, default=False)
        if not approved:
            console.print(f"[yellow]Skipped {cat_name}.[/yellow]")
            continue

        # Handle Recycle Bin specifically
        if cat_key == "recycle_bin":
            import subprocess
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"], timeout=15)
                total_freed_bytes += cat["total_bytes"]
                total_cleaned_files += cat["file_count"]
                cleaned_categories_summary.append(f"{cat_name}: {cat_size_str}")
                log_optimizer_action("clean_recycle_bin", {"count": cat["file_count"], "bytes": cat["total_bytes"]}, "SUCCESS", "Recycle Bin cleared.")
                console.print(f"[bold green]Cleared Recycle Bin ({cat_size_str}).[/bold green]")
            except Exception as e:
                console.print(f"[red]Failed to clear Recycle Bin: {e}[/red]")
            continue

        # Execute cleaning with quarantine
        cat_freed = 0
        cat_count = 0
        for item in cat["files"]:
            f_path = Path(item["path"])
            if not f_path.exists():
                continue

            # Safety path verification
            is_safe, reason = is_safe_optimizer_path(f_path)
            if not is_safe:
                continue

            ok, q_rel = quarantine_and_delete_file(f_path, session_quarantine)
            if ok:
                cat_freed += item["size"]
                cat_count += 1
                manifest_entries.append({
                    "original_path": str(f_path),
                    "quarantine_rel": q_rel,
                    "size": item["size"],
                    "category": cat_key,
                })
                log_optimizer_action("clean_file", {"path": str(f_path), "size": item["size"]}, "SUCCESS")

        total_freed_bytes += cat_freed
        total_cleaned_files += cat_count
        cleaned_categories_summary.append(f"{cat_name}: {format_bytes(cat_freed)} ({cat_count} files)")
        console.print(f"[bold green]Cleaned {cat_name}: {format_bytes(cat_freed)} freed ({cat_count} files moved to quarantine).[/bold green]")

    # Save manifest for /optimize undo
    if manifest_entries:
        manifest_path = session_quarantine / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": session_id,
                "timestamp": datetime.datetime.now().isoformat(),
                "total_files": total_cleaned_files,
                "total_bytes": total_freed_bytes,
                "entries": manifest_entries,
            }, f, indent=2)

    summary_msg = (
        f"Optimization complete. Freed {format_bytes(total_freed_bytes)} across {total_cleaned_files} files. "
        f"Items quarantined in data/optimizer_quarantine/{session_id}/ (use '/optimize undo' to restore)."
    )
    console.print(Panel(f"[bold green]{summary_msg}[/bold green]", title="Clean Summary", border_style="green"))

    return {
        "success": True,
        "session_id": session_id,
        "total_freed_bytes": total_freed_bytes,
        "total_freed_str": format_bytes(total_freed_bytes),
        "total_cleaned_files": total_cleaned_files,
        "categories_summary": cleaned_categories_summary,
        "summary": summary_msg,
    }


def undo_clean(session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Restores quarantined files from a specific session (or latest session) back to original paths.
    """
    if not OPTIMIZER_QUARANTINE_DIR.exists():
        return {"success": False, "message": "No quarantine directory found."}

    sessions = sorted([d for d in OPTIMIZER_QUARANTINE_DIR.iterdir() if d.is_dir() and (d / "manifest.json").exists()], reverse=True)
    if not sessions:
        return {"success": False, "message": "No previous clean sessions found in quarantine to undo."}

    target_session = None
    if session_id:
        target_session = OPTIMIZER_QUARANTINE_DIR / session_id
        if not target_session.exists() or not (target_session / "manifest.json").exists():
            return {"success": False, "message": f"Quarantine session '{session_id}' not found."}
    else:
        target_session = sessions[0]

    manifest_file = target_session / "manifest.json"
    with open(manifest_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    restored_count = 0
    restored_bytes = 0
    for entry in data.get("entries", []):
        orig_p = Path(entry["original_path"])
        q_rel = entry["quarantine_rel"]
        q_file = target_session / q_rel

        if q_file.exists():
            try:
                orig_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(q_file), str(orig_p))
                restored_count += 1
                restored_bytes += entry.get("size", 0)
                log_optimizer_action("undo_clean_file", {"path": str(orig_p)}, "SUCCESS")
            except Exception as e:
                log_optimizer_action("undo_clean_file", {"path": str(orig_p), "error": str(e)}, "ERROR")

    summary = f"Restored {restored_count} files ({format_bytes(restored_bytes)}) from clean session '{target_session.name}'."
    console.print(Panel(f"[bold green]{summary}[/bold green]", title="Undo Clean Complete", border_style="green"))

    return {
        "success": True,
        "session_id": target_session.name,
        "restored_count": restored_count,
        "restored_bytes": restored_bytes,
        "message": summary,
    }
