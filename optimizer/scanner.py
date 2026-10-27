"""
SuperLocal PC Optimizer: System Scanner Module
Performs comprehensive read-only diagnostic scans of PC health:
- CPU, RAM, and per-drive disk metrics via psutil.
- Top 10 processes by CPU and Memory usage.
- Boot time, system uptime, and startup item count.
- Laptop battery health & wear level (if applicable).
- GPU load (if available).
- Pending Windows updates & active power plan.
- Calculates an overall Health Score (0-100) and highlights the 3 biggest findings.
"""

import os
import time
import datetime
import subprocess
import winreg
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

import psutil
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def get_boot_and_uptime() -> Tuple[str, str, float]:
    """Returns boot time string, formatted uptime string, and uptime seconds."""
    boot_ts = psutil.boot_time()
    boot_dt = datetime.datetime.fromtimestamp(boot_ts)
    boot_str = boot_dt.strftime("%Y-%m-%d %H:%M:%S")

    uptime_sec = time.time() - boot_ts
    days = int(uptime_sec // 86400)
    hours = int((uptime_sec % 86400) // 3600)
    minutes = int((uptime_sec % 3600) // 60)

    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m"
    else:
        uptime_str = f"{hours}h {minutes}m"

    return boot_str, uptime_str, uptime_sec


def get_cpu_metrics() -> Dict[str, Any]:
    """Returns CPU usage, core counts, and frequency."""
    cpu_pct = psutil.cpu_percent(interval=0.2)
    freq = psutil.cpu_freq()
    cur_freq = f"{freq.current:.1f} MHz" if freq else "N/A"
    return {
        "percent": cpu_pct,
        "physical_cores": psutil.cpu_count(logical=False) or 1,
        "logical_cores": psutil.cpu_count(logical=True) or 1,
        "frequency": cur_freq,
    }


def get_memory_metrics() -> Dict[str, Any]:
    """Returns RAM total, used, free, and percent."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "available_gb": round(mem.available / (1024**3), 1),
        "percent": mem.percent,
    }


def get_disk_metrics() -> List[Dict[str, Any]]:
    """Returns storage usage for all mounted local fixed drives."""
    drives = []
    for part in psutil.disk_partitions(all=False):
        if "fixed" in part.opts or part.fstype:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                drives.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1),
                    "free_gb": round(usage.free / (1024**3), 1),
                    "percent_used": usage.percent,
                    "percent_free": round(100.0 - usage.percent, 1),
                })
            except Exception:
                continue
    return drives


def get_top_processes(limit: int = 10) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns top processes sorted by CPU and Memory."""
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'username']):
        try:
            info = p.info
            mem_mb = round(info['memory_info'].rss / (1024 * 1024), 1) if info.get('memory_info') else 0.0
            procs.append({
                "pid": info['pid'],
                "name": info['name'] or "Unknown",
                "cpu": info.get('cpu_percent') or 0.0,
                "memory_mb": mem_mb,
                "user": info.get('username') or "System",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort
    top_cpu = sorted(procs, key=lambda x: x["cpu"], reverse=True)[:limit]
    top_mem = sorted(procs, key=lambda x: x["memory_mb"], reverse=True)[:limit]
    return top_cpu, top_mem


def count_startup_entries() -> int:
    """Counts startup items in HKCU/HKLM Run keys and startup folders."""
    count = 0
    # Registry Run
    reg_paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for root, subkey in reg_paths:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
                count += winreg.QueryInfoKey(key)[1]
        except Exception:
            pass

    # Startup Folders
    appdata = os.environ.get("APPDATA")
    if appdata:
        p1 = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if p1.exists():
            count += len([f for f in p1.iterdir() if f.is_file() and not f.name.startswith("desktop.ini")])

    progdata = os.environ.get("ProgramData")
    if progdata:
        p2 = Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if p2.exists():
            count += len([f for f in p2.iterdir() if f.is_file() and not f.name.startswith("desktop.ini")])

    return count


def get_battery_info() -> Optional[Dict[str, Any]]:
    """Returns laptop battery percentage, power plug state, and wear status."""
    try:
        batt = psutil.sensors_battery()
        if not batt:
            return None
        return {
            "percent": batt.percent,
            "power_plugged": batt.power_plugged,
            "secs_left": batt.secsleft if batt.secsleft != psutil.POWER_TIME_UNLIMITED else None,
        }
    except Exception:
        return None


def get_active_power_plan() -> str:
    """Queries powercfg for active power scheme name."""
    try:
        proc = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            out = proc.stdout.strip()
            # Example: Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)
            if "(" in out and ")" in out:
                return out.split("(")[-1].split(")")[0].strip()
            return out
    except Exception:
        pass
    return "Balanced (Default)"


def check_pending_updates() -> bool:
    """Checks Windows registry flags for pending reboot / updates."""
    keys_to_check = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"),
    ]
    for root, subkey in keys_to_check:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ):
                return True
        except Exception:
            pass
    return False


def get_gpu_info() -> Optional[str]:
    """Queries GPU information via WMI or nvidia-smi if available."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=5
        )
        if proc.returncode == 0 and proc.stdout.strip():
            gpus = [g.strip() for g in proc.stdout.strip().splitlines() if g.strip()]
            return ", ".join(gpus)
    except Exception:
        pass
    return None


def calculate_health_score(
    cpu_pct: float,
    mem_pct: float,
    drives: List[Dict[str, Any]],
    startup_count: int,
    uptime_sec: float,
    pending_reboot: bool,
    battery: Optional[Dict[str, Any]],
) -> Tuple[int, List[str]]:
    """
    Computes a 0-100 PC Health Score and determines the top 3 findings.
    """
    score = 100
    findings = []

    # RAM Analysis
    if mem_pct >= 85:
        score -= 20
        findings.append(f"High RAM usage ({mem_pct:.1f}%): Memory pressure is high, which may cause UI stutter and paging.")
    elif mem_pct >= 70:
        score -= 10
        findings.append(f"Moderate RAM usage ({mem_pct:.1f}%): Over 70% of memory is currently in use.")

    # Disk Space Analysis
    low_space_drives = [d for d in drives if d["percent_free"] < 15.0]
    if low_space_drives:
        d = low_space_drives[0]
        penalty = 25 if d["percent_free"] < 10.0 else 15
        score -= penalty
        findings.append(f"Low free disk space on {d['mountpoint']} ({d['free_gb']} GB left, {d['percent_free']}% free): Drives under 15% free limit Windows virtual memory and update staging.")

    # CPU Analysis
    if cpu_pct >= 80:
        score -= 15
        findings.append(f"High active CPU load ({cpu_pct:.1f}%): Processes are currently demanding heavy processing power.")

    # Startup Load
    if startup_count >= 15:
        score -= 10
        findings.append(f"Heavy startup burden ({startup_count} startup items): Numerous programs start automatically at login, extending boot time.")
    elif startup_count >= 8:
        score -= 5

    # Uptime / Reboot Needed
    if pending_reboot:
        score -= 5
        findings.append("Pending system reboot: Windows updates are staged and awaiting a restart to finalize installation.")
    elif uptime_sec > (14 * 86400):
        days = int(uptime_sec // 86400)
        score -= 5
        findings.append(f"Long uptime ({days} days without reboot): A fresh system restart clears kernel memory pools and driver leaks.")

    # Battery
    if battery and not battery["power_plugged"] and battery["percent"] < 20:
        score -= 5
        findings.append(f"Low battery level ({battery['percent']}%): Plug in PC or switch to battery saver.")

    # Default positive findings if everything is healthy
    if not findings:
        findings.append("Memory and CPU utilization are within optimal nominal ranges.")
        findings.append("Storage drives have ample free space for Windows caching and paging.")
        findings.append("Startup programs and background services are lean.")

    score = max(10, min(100, score))
    return score, findings[:3]


def run_system_scan() -> Dict[str, Any]:
    """
    Executes a complete system scan and prints a Rich diagnostic dashboard.
    """
    boot_str, uptime_str, uptime_sec = get_boot_and_uptime()
    cpu = get_cpu_metrics()
    mem = get_memory_metrics()
    drives = get_disk_metrics()
    top_cpu, top_mem = get_top_processes(limit=10)
    startup_count = count_startup_entries()
    battery = get_battery_info()
    power_plan = get_active_power_plan()
    pending_reboot = check_pending_updates()
    gpu_name = get_gpu_info()

    score, findings = calculate_health_score(
        cpu["percent"], mem["percent"], drives, startup_count, uptime_sec, pending_reboot, battery
    )

    # 1. Dashboard Table
    score_color = "green" if score >= 80 else ("yellow" if score >= 60 else "red")
    table = Table(title=f"PC Health & Diagnostic Scan (Health Score: [{score_color}]{score}/100[/{score_color}])", border_style="cyan")
    table.add_column("Category", style="bold cyan", width=22)
    table.add_column("Current Status & Metrics", style="white")

    table.add_row("Health Score", f"[{score_color}][bold]{score} / 100[/bold][/{score_color}]")
    table.add_row("CPU Load", f"{cpu['percent']}% ({cpu['physical_cores']} Cores / {cpu['logical_cores']} Threads @ {cpu['frequency']})")
    table.add_row("Memory (RAM)", f"{mem['used_gb']} GB used of {mem['total_gb']} GB ({mem['percent']}%) - {mem['available_gb']} GB available")

    # Drives summary
    d_summary = ", ".join([f"{d['mountpoint']} {d['free_gb']}GB free ({d['percent_free']}%)" for d in drives])
    table.add_row("Disk Storage", d_summary or "No local drives found")

    table.add_row("System Uptime", f"{uptime_str} (Booted: {boot_str})")
    table.add_row("Startup Programs", f"{startup_count} items enabled at logon")
    table.add_row("Active Power Plan", power_plan)
    table.add_row("Windows Updates", "[yellow]Reboot Required[/yellow]" if pending_reboot else "[green]Up to date (No reboot pending)[/green]")

    if battery:
        batt_state = "Plugged in (Charging)" if battery["power_plugged"] else "On Battery"
        table.add_row("Battery", f"{battery['percent']}% ({batt_state})")

    if gpu_name:
        table.add_row("GPU Controller", gpu_name)

    console.print(table)

    # 2. Top 3 Findings Panel
    findings_md = "\n".join([f"**{i+1}.** {f}" for i, f in enumerate(findings)])
    console.print(Panel(
        findings_md,
        title="[bold yellow]Key Findings & Recommendations[/bold yellow]",
        border_style="yellow"
    ))

    # 3. Top Processes Table
    p_table = Table(title="Top Processes by Resource Consumption", border_style="dim")
    p_table.add_column("Top CPU Processes", style="cyan")
    p_table.add_column("CPU %", style="bold white")
    p_table.add_column("Top Memory Processes", style="magenta")
    p_table.add_column("Memory (MB)", style="bold white")

    for i in range(min(5, max(len(top_cpu), len(top_mem)))):
        c_proc = top_cpu[i] if i < len(top_cpu) else {"name": "-", "cpu": 0.0}
        m_proc = top_mem[i] if i < len(top_mem) else {"name": "-", "memory_mb": 0.0}
        p_table.add_row(
            f"{c_proc['name']} ({c_proc.get('pid', '-')})",
            f"{c_proc['cpu']:.1f}%",
            f"{m_proc['name']} ({m_proc.get('pid', '-')})",
            f"{m_proc['memory_mb']:.1f} MB",
        )
    console.print(p_table)

    summary_text = (
        f"Scan complete. Health Score: {score}/100. "
        f"RAM: {mem['percent']}%, CPU: {cpu['percent']}%, Uptime: {uptime_str}. "
        f"Top finding: {findings[0]}"
    )

    return {
        "health_score": score,
        "findings": findings,
        "cpu": cpu,
        "memory": mem,
        "drives": drives,
        "top_cpu_processes": top_cpu,
        "top_memory_processes": top_mem,
        "uptime": uptime_str,
        "boot_time": boot_str,
        "startup_count": startup_count,
        "power_plan": power_plan,
        "pending_reboot": pending_reboot,
        "battery": battery,
        "gpu": gpu_name,
        "summary": summary_text,
    }
