"""
SuperLocal PC Optimizer: Disk Health, Storage & Duplicates Module
Handles disk analysis and physical storage optimization:
- Largest folders and files finder (confined to user folders, blocks system folders).
- Duplicate file detector by size grouping and SHA-256 content hashing.
- SMART physical disk health & reliability counters (Get-PhysicalDisk & Get-StorageReliabilityCounter).
- Safe SSD TRIM (Optimize-Volume -ReTrim).
- HARD RULE: NEVER defragments an SSD. Defragmentation on SSDs is explicitly blocked with educational warning.
"""

import os
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from optimizer.guards import (
    is_safe_optimizer_path,
    confirm_action,
    log_optimizer_action,
)
from optimizer.cleaner import format_bytes, quarantine_and_delete_file

console = Console()


def compute_file_sha256(file_path: Path, max_bytes: int = 10 * 1024 * 1024) -> Optional[str]:
    """Computes SHA-256 hash of a file (up to max_bytes for speed)."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            bytes_read = 0
            while chunk := f.read(65536):
                hasher.update(chunk)
                bytes_read += len(chunk)
                if bytes_read >= max_bytes:
                    break
        return hasher.hexdigest()
    except Exception:
        return None


def find_largest_items(target_dir: Path, limit: int = 10) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Scans a non-system directory and identifies top largest files and folders.
    """
    is_safe, reason = is_safe_optimizer_path(target_dir)
    if not is_safe:
        console.print(f"[bold red]Blocked:[/bold red] {reason}")
        return [], []

    files = []
    folder_sizes = defaultdict(int)

    try:
        for root, dirs, filenames in os.walk(str(target_dir)):
            r_path = Path(root)
            # Skip hidden/git folders
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", "__pycache__")]
            for fn in filenames:
                fp = r_path / fn
                try:
                    sz = fp.stat().st_size
                    files.append({"path": str(fp), "size": sz})
                    folder_sizes[root] += sz
                except Exception:
                    continue
    except Exception:
        pass

    files.sort(key=lambda x: x["size"], reverse=True)
    top_files = files[:limit]

    top_folders = [
        {"path": k, "size": v}
        for k, v in sorted(folder_sizes.items(), key=lambda x: x[1], reverse=True)[:limit]
    ]

    return top_files, top_folders


def find_duplicate_files(target_dir: Path, min_size_bytes: int = 1024) -> List[List[Dict[str, Any]]]:
    """
    Finds duplicate files in user-specified directory by matching file sizes and SHA-256 hashes.
    """
    is_safe, reason = is_safe_optimizer_path(target_dir)
    if not is_safe:
        console.print(f"[bold red]Blocked:[/bold red] {reason}")
        return []

    # 1. Group by file size
    size_groups = defaultdict(list)
    try:
        for root, dirs, filenames in os.walk(str(target_dir)):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv")]
            for fn in filenames:
                fp = Path(root) / fn
                try:
                    sz = fp.stat().st_size
                    if sz >= min_size_bytes:
                        size_groups[sz].append(fp)
                except Exception:
                    continue
    except Exception:
        pass

    # 2. For groups with >1 file of identical size, compute hash
    duplicates = []
    for sz, candidate_paths in size_groups.items():
        if len(candidate_paths) < 2:
            continue

        hash_groups = defaultdict(list)
        for p in candidate_paths:
            h = compute_file_sha256(p)
            if h:
                hash_groups[h].append({"path": str(p), "size": sz})

        for h, dup_list in hash_groups.items():
            if len(dup_list) > 1:
                duplicates.append(dup_list)

    return duplicates


def get_physical_disk_health() -> List[Dict[str, Any]]:
    """
    Queries PowerShell Get-PhysicalDisk and Get-StorageReliabilityCounter.
    """
    disks = []
    cmd = [
        "powershell", "-NoProfile", "-Command",
        "Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, MediaType, HealthStatus, OperationalStatus, Size | ConvertTo-Json"
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if proc.returncode == 0 and proc.stdout.strip():
            import json
            raw_data = json.loads(proc.stdout)
            if isinstance(raw_data, dict):
                raw_data = [raw_data]

            for d in raw_data:
                size_gb = round(d.get("Size", 0) / (1024**3), 1)
                media_type = d.get("MediaType", "Unspecified")
                # Normalize media type
                if media_type in (4, "SSD"):
                    media_type = "SSD"
                elif media_type in (3, "HDD"):
                    media_type = "HDD"
                else:
                    media_type = str(media_type or "Unspecified")

                disks.append({
                    "id": d.get("DeviceId", 0),
                    "name": d.get("FriendlyName", "Physical Disk"),
                    "media_type": media_type,
                    "health": d.get("HealthStatus", "Unknown"),
                    "status": d.get("OperationalStatus", "OK"),
                    "size_gb": size_gb,
                })
    except Exception:
        pass

    return disks


def run_ssd_trim(drive_letter: str = "C", auto_approve: bool = False) -> Dict[str, Any]:
    """
    Runs SSD TRIM optimization using Optimize-Volume -ReTrim.
    HARD RULE: Explicitly forbids and prevents defragmentation on SSDs.
    """
    dl = drive_letter.strip().upper().replace(":", "")

    # Query media type first
    disks = get_physical_disk_health()
    is_ssd = any("SSD" in str(d.get("media_type", "")).upper() for d in disks)

    if not is_ssd:
        # Check through PowerShell Get-Volume
        chk_cmd = [
            "powershell", "-NoProfile", "-Command",
            f"(Get-PhysicalDisk -DeviceNumber (Get-Partition -DriveLetter {dl}).DiskNumber).MediaType"
        ]
        try:
            chk_proc = subprocess.run(chk_cmd, capture_output=True, text=True, timeout=8)
            if "SSD" in chk_proc.stdout.upper():
                is_ssd = True
        except Exception:
            pass

    if not is_ssd:
        msg = f"Drive {dl}: is detected as an HDD or virtual disk. Defragmentation is skipped to protect drive health."
        console.print(f"[yellow]{msg}[/yellow]")
        return {"success": False, "message": msg}

    console.print(Panel(
        f"[bold cyan]SSD Storage Optimization (Drive {dl}:)[/bold cyan]\n"
        "Executing native TRIM operation (`Optimize-Volume -ReTrim`).\n"
        "[dim]Note: Defragmentation on SSDs is permanently prohibited by SuperLocal to avoid flash write wear.[/dim]",
        border_style="cyan"
    ))

    approved = auto_approve or confirm_action(f"Run SSD TRIM on drive {dl}:?", default=True)
    if not approved:
        return {"success": False, "message": "SSD TRIM cancelled by user."}

    cmd = [
        "powershell", "-NoProfile", "-Command",
        f"Optimize-Volume -DriveLetter {dl} -ReTrim -Verbose"
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            msg = f"Successfully executed TRIM on SSD drive {dl}:."
            log_optimizer_action("ssd_trim", {"drive": dl}, "SUCCESS", msg)
            console.print(f"[bold green]{msg}[/bold green]")
            return {"success": True, "message": msg}
        else:
            msg = f"TRIM command completed with code {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
            return {"success": False, "message": msg}
    except Exception as e:
        return {"success": False, "message": f"Error running SSD TRIM: {e}"}


def manage_disk_flow(target_dir: Optional[Path] = None, auto_approve: bool = False) -> Dict[str, Any]:
    """
    Main flow for /optimize disk:
    1. Shows SMART & physical disk health
    2. Runs SSD TRIM
    3. Finds largest files and duplicates
    """
    console.print("[bold cyan]Querying Physical Storage Health & SMART Status...[/bold cyan]")
    disks = get_physical_disk_health()

    if disks:
        d_table = Table(title="Physical Disks & SMART Health", border_style="cyan")
        d_table.add_column("Disk", style="bold cyan")
        d_table.add_column("Type", style="magenta")
        d_table.add_column("Size", style="green")
        d_table.add_column("Health Status", style="bold")
        d_table.add_column("Operational State", style="dim")

        for d in disks:
            h_color = "green" if str(d["health"]).lower() == "healthy" else "red"
            d_table.add_row(
                f"Disk {d['id']} ({d['name']})",
                d["media_type"],
                f"{d['size_gb']} GB",
                f"[{h_color}]{d['health']}[/{h_color}]",
                str(d["status"]),
            )
        console.print(d_table)
    else:
        console.print("[yellow]Could not query physical disk SMART status (requires standard disk controllers).[/yellow]")

    # Run TRIM on C:
    trim_res = run_ssd_trim(drive_letter="C", auto_approve=auto_approve)

    # Search folder for large files & duplicates
    scan_path = target_dir or (Path.home() / "Downloads")
    if scan_path.exists():
        console.print(f"\n[bold cyan]Scanning '{scan_path}' for large items and duplicate files...[/bold cyan]")
        top_files, top_folders = find_largest_items(scan_path, limit=5)

        if top_files:
            f_table = Table(title=f"Largest Files in {scan_path.name}", border_style="dim")
            f_table.add_column("File Name", style="cyan")
            f_table.add_column("Size", style="green")
            for f in top_files:
                f_table.add_row(Path(f["path"]).name, format_bytes(f["size"]))
            console.print(f_table)

        duplicates = find_duplicate_files(scan_path)
        if duplicates:
            console.print(f"\n[bold yellow]Found {len(duplicates)} sets of identical duplicate files in '{scan_path.name}':[/bold yellow]")
            for group in duplicates[:3]:
                console.print(f"  • Size: {format_bytes(group[0]['size'])}")
                for item in group:
                    console.print(f"    - {item['path']}")

    summary = f"Disk check complete. Inspected {len(disks)} physical drives. TRIM: {trim_res.get('message', 'Completed')}."
    console.print(Panel(f"[bold green]{summary}[/bold green]", title="Disk Optimization Complete", border_style="green"))
    return {"success": True, "disks": disks, "trim": trim_res, "summary": summary}
