"""
Astra-Local: An AI Assistant for Windows running in CMD and PowerShell.
Entry point and interactive Rich TUI.
"""

import sys
import os
import re

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.markup import escape

from config import (
    MODEL_NAME,
    THINKING_LEVEL,
    AUTO_APPROVE_SAFE,
    WORKSPACE_DIR,
    SHORTCUTS_PATH,
    QUOTA_PER_DAY,
    QUOTA_WARN_THRESHOLD,
    PROVIDER_ORDER,
    load_shortcuts,
    GEMINI_API_KEY,
)
from agent import AstraAgent
from memory import MemoryManager
from providers import get_provider, OllamaProvider
from safety import start_emergency_stop_listener
from tools.browser import close_browser
from takeover import run_takeover_mode, setup_takeover_hotkey
from autopilot import (
    run_autopilot,
    undo_last_step,
    list_jobs_summary,
    get_active_job_status,
    get_autopilot_engine,
    JobStatus,
)
from computer import run_computer_mode
from poki import handle_poki_command
from optimizer import handle_optimizer_command
from voice import (
    get_voice_assistant,
    list_audio_devices,
    voice_test,
    set_audio_mic,
    show_audio_level,
)

console = Console()


def print_banner(active_provider_name: Optional[str] = None):
    banner_text = (
        "[bold cyan]"
        " ____  _   _ ____  _____ ____  _     ___   ____    _    _     \n"
        "/ ___|| | | |  _ \\| ____|  _ \\| |   / _ \\ / ___|  / \\  | |    \n"
        "\\___ \\| | | | |_) |  _| | |_) | |  | | | | |     / _ \\ | |    \n"
        " ___) | |_| |  __/| |___|  _ <| |__| |_| | |___ / ___ \\| |___ \n"
        "|____/ \\___/|_|   |_____|_| \\_\\_____\\___/ \\____/_/   \\_\\_____|\n"
        "[/bold cyan]"
        "[bold white]Superlocal: Windows AI Assistant • Created by Yogeshwaran[/bold white]"
    )
    console.print(Panel(banner_text, border_style="cyan", subtitle="version 1.0"))

    # Config overview table
    shortcuts = load_shortcuts()
    sc_count = sum(len(v) for v in shortcuts.values() if isinstance(v, dict))
    calls_today = MemoryManager().get_daily_api_calls()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold cyan]System:[/bold cyan]", "Superlocal v1.0")
    table.add_row("[bold cyan]Author:[/bold cyan]", "Yogeshwaran")
    table.add_row("[bold cyan]Thinking Level:[/bold cyan]", THINKING_LEVEL)
    table.add_row("[bold cyan]Auto-Approve Safe:[/bold cyan]", "[green]Enabled[/green]" if AUTO_APPROVE_SAFE else "[yellow]Disabled (Prompt All)[/yellow]")
    table.add_row("[bold cyan]Workspace:[/bold cyan]", str(WORKSPACE_DIR))
    table.add_row("[bold cyan]Shortcuts Active:[/bold cyan]", f"{sc_count} configured in shortcuts.json")
    prov_display = active_provider_name or PROVIDER_ORDER[0]
    table.add_row("[bold cyan]Active Provider:[/bold cyan]", f"[green]{prov_display}[/green] (Fallback: {' -> '.join(PROVIDER_ORDER)})")
    table.add_row("[bold cyan]Requests Today:[/bold cyan]", f"{calls_today}/{QUOTA_PER_DAY} daily calls used")
    table.add_row("[bold cyan]AI Engine:[/bold cyan]", "[green]Connected & Ready[/green]" if GEMINI_API_KEY else "[red]Missing (set in .env)[/red]")

    console.print(table)
    console.print("[dim]Type your command in natural language, or use /provider, /models, /help, /exit.[/dim]\n")


def show_help():
    help_md = """
### Superlocal Commands & Capabilities

**@computer Mode (Advanced PC Operator Agent):**
- `@computer <task>` or `/computer <task>`: Run PC operator agent with strict sandbox and permissions.
  - Effort levels: `--low` (a11y/keyboard only, max 10 actions), `--medium` (default, a11y + OCR, max 30 actions), `--high` (vision allowed, max 80 actions, 60 mins).
  - Safety: Sandboxed to session folder, per-session app allowlist with toast notifications, banking & password protection.
  - Hotkeys: `Ctrl+Alt+Q` (stop), `Ctrl+Alt+P` (pause/resume), `Ctrl+Alt+H` (hand back control).
- Voice trigger: `"Hey SuperLocal, computer, <task>"`.

**Poki Player (Games Workbench):**
- `/poki play <game> [--goal "score 2000" | "finish level 5" | "play 10 min"]`: Play single-player browser games on Poki.
- `/poki list`: Show available game skills, status, and benchmark scores.
- `/poki learn <game>`: Autonomously explore and learn a skill for a new game.
- `/poki stats`: Show performance analytics, high scores, and success rates.
- `/poki stop`: Stop active gameplay (also `Ctrl+Alt+Q` or voice `"stop"`).

**PC Optimizer Workbench:**
- `/optimize scan`: Full diagnostic scan (CPU, RAM, disk, boot time, health score & top 3 findings).
- `/optimize clean`: Safe 7-day temp, browser cache & junk clean with quarantine and undo.
- `/optimize startup`: Inspect and safely disable non-essential startup apps with backup.
- `/optimize apps`: Review installed programs and safely uninstall via winget.
- `/optimize disk`: SMART physical disk health, largest files & duplicates finder, SSD TRIM.
- `/optimize health`: Read-only SFC, DISM component store, driver age & Defender check.
- `/optimize power`: View and configure Windows power schemes (Balanced / High Performance).
- `/optimize network`: Active connections, DNS latency, and ping connectivity check.
- `/optimize report`: Export before/after PDF & Markdown optimization report.
- `/optimize undo`: Roll back cleaned files from quarantine and restore startup items.

**Autopilot Mode (End-to-End Autonomous Worker):**
- `/auto <goal>`: Complete a whole job end-to-end (e.g. `/auto build a portfolio website with dark mode`).
- `/auto --dry <goal>`: Preview the planned steps without executing.
- `/auto status`: Show current job, step, time and request count.
- `/auto pause | resume | stop`: Pause, resume, or abort active job execution.
- `/auto undo`: Roll back the last step using git reset and SQLite checkpoint.
- `/jobs`: List past jobs with their workspaces and logs.

**Special Commands:**
- `/voice on`: Enable Voice Assistant in background (Wake word: 'hey superlocal', Push-to-Talk: F9).
- `/voice off`: Disable Voice Assistant.
- `/voice live`: Toggle Gemini Live bidirectional streaming voice mode.
- `/voice test`: Run microphone and speaker/TTS diagnostic check.
- `/voice devices`: List and select input/output audio devices.
- `/voice mic <num>`: Switch active microphone to device index and save choice.
- `/voice level`: Display live 5-second microphone volume meter.
- `/health`: Test each configured AI provider with a tiny request (shows provider | model | status | last error | exact fix).
- `/quota`: View daily request counts per model and limits.
- `/quota reset`: Reset daily usage tracking counters in SQLite memory.
- `/provider`: Show current active provider and configured fallback order.
- `/provider <name>`: Switch active provider (e.g. `/provider groq`, `/provider openrouter`, `/provider gemini`, `/provider ollama_local`).
- `/models`: List available models for active or configured providers.
- `/takeover <task>`: Launch Takeover Mode to control mouse and keyboard like a remote user (Hotkey: `Ctrl+Alt+T`).
- `/help`: Display this help menu.
- `/shortcuts`: View shortcuts from `shortcuts.json`.
- `/sessions`: View previous conversation sessions.
- `/new`: Start a fresh conversation session.
- `/clear` or `cls`: Clear terminal screen.
- `/exit` or `quit`: Exit Superlocal.

**Voice Assistant Hotkeys & Triggers:**
- **Wake Words:** `hey superlocal`, `hey astra`, or custom
- **Push-to-Talk:** `F9` (hold to speak immediately without wake word)
- **Stop Speech/Actions:** Say `"stop"`, `"cancel"`, `"quiet"` or press `Ctrl+Alt+Q`

**Natural Language Examples:**
1. *Autopilot Web:* `/auto build a portfolio website with dark mode and a contact form`
2. *Voice Autopilot:* `"Hey SuperLocal, auto build a todo app"`
3. *Voice & Discord:* `"Hey SuperLocal, open discord and go to my server"`
4. *System & Shortcuts:* `"open discord and go to my server"`
5. *Browser & WhatsApp:* `"open whatsapp in browser, search amma and send hi"`
6. *Files & Folders:* `"create a folder called test on Desktop and open it in VS Code"`
7. *Data Analysis:* `"analyze sales.csv, find missing values, clean it and make a bar chart"`
8. *Presentations:* `"make a 5-slide presentation about AI and save it on Desktop"`
9. *Development:* `"create a Flask app with a login page and run it"`
10. *Web Testing:* `"test my website at localhost:3000 and list UI bugs"`
"""
    console.print(Markdown(help_md))


def handle_autopilot_command(cmd: str, agent: Optional[AstraAgent] = None):
    """
    Dispatches Autopilot commands:
    /auto <goal>, /auto --dry <goal>, /auto status, /auto pause, /auto resume, /auto stop, /auto undo
    """
    parts = cmd.strip().split(maxsplit=2)
    sub = parts[1].lower() if len(parts) > 1 else ""

    engine = get_autopilot_engine()

    if sub == "status":
        info = get_active_job_status()
        if not info:
            console.print("[yellow]No active or recent autopilot job found.[/yellow]")
            return
        table = Table(title="Autopilot Job Status", border_style="cyan")
        table.add_column("Property", style="bold cyan")
        table.add_column("Value", style="white")
        table.add_row("Job ID", info["id"])
        table.add_row("Goal", info["goal"])
        table.add_row("Status", info["status"].upper())
        table.add_row("Progress", f"Step {info['current_step']} of {info['total_steps']}")
        table.add_row("Elapsed Time", info["elapsed"])
        table.add_row("Model Calls", str(info["model_calls"]))
        table.add_row("Desktop Actions", str(info["desktop_actions"]))
        table.add_row("Workspace", info["workspace"])
        console.print(table)
        return

    if sub == "undo":
        msg = undo_last_step()
        console.print(f"[bold cyan][Autopilot Undo][/bold cyan] {msg}")
        return

    if sub == "pause":
        job = engine._active_job or engine.store.get_latest_active_job()
        if job and job.status == JobStatus.RUNNING:
            job.status = JobStatus.PAUSED
            engine.store.save_job(job)
            console.print(f"[bold yellow]Autopilot job '{job.id}' paused.[/bold yellow]")
        else:
            console.print("[yellow]No running autopilot job to pause.[/yellow]")
        return

    if sub == "resume":
        job = engine._active_job or engine.store.get_latest_active_job()
        if job and job.status == JobStatus.PAUSED:
            job.status = JobStatus.RUNNING
            engine.store.save_job(job)
            console.print(f"[bold green]Autopilot job '{job.id}' resumed.[/bold green]")
        else:
            console.print("[yellow]No paused autopilot job to resume.[/yellow]")
        return

    if sub == "stop":
        job = engine._active_job or engine.store.get_latest_active_job()
        if job:
            job.status = JobStatus.STOPPED
            engine.store.save_job(job)
            console.print(f"[bold red]Autopilot job '{job.id}' stopped.[/bold red]")
        else:
            console.print("[yellow]No active autopilot job to stop.[/yellow]")
        return

    # Check for dry run: /auto --dry <goal>
    dry_run = False
    goal_text = ""
    if sub in ("--dry", "-d"):
        dry_run = True
        goal_text = parts[2].strip() if len(parts) > 2 else ""
    else:
        # /auto <goal>
        goal_text = cmd[len("/auto"):].strip()

    if not goal_text:
        console.print("[bold red]Please specify a goal for Autopilot, e.g.: /auto build a portfolio website[/bold red]")
        console.print("[dim]Use /auto --dry <goal> to inspect the plan without executing.[/dim]")
        return

    prov = agent.active_provider if agent else None
    run_autopilot(goal_text, dry_run=dry_run, provider=prov)


def show_jobs(limit: int = 10):
    """Displays a list of past autopilot jobs."""
    jobs = list_jobs_summary(limit=limit)
    if not jobs:
        console.print("[yellow]No past autopilot jobs recorded yet.[/yellow]")
        return

    table = Table(title=f"Past Autopilot Jobs (Last {len(jobs)})", border_style="cyan")
    table.add_column("Job ID", style="bold cyan")
    table.add_column("Goal", style="white")
    table.add_column("Category", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Steps", style="dim")
    table.add_column("Workspace", style="dim")
    table.add_column("Updated", style="dim")

    for j in jobs:
        stat_color = "green" if j["status"] == "completed" else ("yellow" if j["status"] in ("running", "dry_run") else "red")
        table.add_row(
            j["id"],
            j["goal"][:45] + ("..." if len(j["goal"]) > 45 else ""),
            j["category"],
            f"[{stat_color}]{j['status'].upper()}[/{stat_color}]",
            f"{j['current_step_id']}/{j['total_steps']}",
            j["workspace_dir"],
            str(j.get("updated_at", "")),
        )

    console.print(table)


def handle_computer_command(cmd: str, agent: Optional[AstraAgent] = None):
    """Dispatches @computer or /computer task to Computer Mode."""
    prov = agent.active_provider if agent else None
    run_computer_mode(cmd, provider=prov)


def show_shortcuts():
    shortcuts = load_shortcuts()
    table = Table(title="Configured Shortcuts (shortcuts.json)", border_style="cyan")
    table.add_column("Category", style="bold magenta")
    table.add_column("Name / Trigger", style="cyan")
    table.add_column("Target Value", style="white")

    for cat, items in shortcuts.items():
        if isinstance(items, dict):
            for k, v in items.items():
                table.add_row(cat, k, str(v))
    console.print(table)


def show_health(agent: Optional[AstraAgent] = None):
    """
    Tests each configured provider with a tiny request and prints:
    provider | model | status | last error | exact fix.
    """
    agent_inst = agent or AstraAgent()
    table = Table(title="AI Provider Health Checks", border_style="cyan")
    table.add_column("Provider", style="bold cyan")
    table.add_column("Model", style="bold magenta")
    table.add_column("Status", style="bold")
    table.add_column("Last Error", style="red")
    table.add_column("Exact Fix", style="yellow")

    for prov in agent_inst.provider_chain:
        model_name = getattr(prov, "model", getattr(prov, "active_model", "default"))
        try:
            h_res = prov.health_check()
            is_h = h_res[0] if isinstance(h_res, tuple) else False
            details = h_res[1] if isinstance(h_res, tuple) else str(h_res)
            fix = h_res[2] if isinstance(h_res, tuple) and len(h_res) > 2 else None
        except Exception as e:
            is_h, details, fix = False, str(e), "Check logs and configuration."

        status_disp = "[green]Healthy[/green]" if is_h else "[red]Unhealthy[/red]"
        last_error = "-" if is_h else escape(details)
        exact_fix = escape(fix) if fix else ("Operational" if is_h else "Check configuration")
        table.add_row(escape(prov.name), escape(str(model_name)), status_disp, last_error, exact_fix)

    console.print(table)


def handle_quota_command(cmd: str, memory: Optional[MemoryManager] = None):
    """Handles /quota (show daily usage per model) and /quota reset."""
    mem = memory or MemoryManager()
    parts = cmd.strip().split()
    if len(parts) > 1 and parts[1].lower() == "reset":
        mem.reset_daily_usage()
        console.print("[bold green]Daily quota usage counter has been reset in SQLite memory.[/bold green]")
        return

    usage = mem.get_daily_usage_summary()
    total_calls = mem.get_daily_api_calls()

    table = Table(title="Daily Model Request Tracking", border_style="cyan")
    table.add_column("Model / Provider", style="bold cyan")
    table.add_column("Requests Today", style="bold green")
    table.add_column("Daily Limit", style="white")
    table.add_column("Status / Warning", style="yellow")

    if usage:
        for m_name, count in usage.items():
            stat = "[yellow]Warning: High Usage[/yellow]" if count >= QUOTA_WARN_THRESHOLD else "[green]OK[/green]"
            table.add_row(escape(m_name), str(count), f"{QUOTA_PER_DAY} (warns at {QUOTA_WARN_THRESHOLD})", stat)
    else:
        table.add_row("All Models", "0", f"{QUOTA_PER_DAY}", "[green]OK (0 requests logged today)[/green]")

    console.print(table)
    console.print(f"[dim]Total requests logged today: {total_calls}. Note: Local counter only warns and never blocks providers.[/dim]")
    console.print("[dim]To reset usage tracking: /quota reset[/dim]\n")


def check_startup_providers(agent: AstraAgent):
    """
    Checks configured providers at startup.
    If Ollama is local, tries auto-starting 'ollama serve' in background (up to 10s).
    If unreachable or model not found, prints exact fix ('ollama serve', 'ollama pull <model>').
    """
    for prov in agent.provider_chain:
        if isinstance(prov, OllamaProvider) and any(h in prov.host for h in ("localhost", "127.0.0.1", "0.0.0.0")):
            is_h, details, fix = prov.health_check(auto_start=True)
            if not is_h:
                if "not found" in details.lower():
                    console.print(f"[bold yellow]Notice: Model '{prov.model}' not found in Ollama. Run: 'ollama pull {prov.model}'[/bold yellow]")
                else:
                    console.print(f"[bold yellow]Notice: Ollama server is offline at {prov.host}. Run 'ollama serve' and 'ollama pull {prov.model}'[/bold yellow]")


def handle_voice_command(cmd: str, agent: Optional[AstraAgent] = None):
    """Handles /voice on, /voice off, /voice live, /voice test, /voice devices, /voice mic <num>, /voice level."""
    parts = cmd.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else ""
    va = get_voice_assistant(agent)

    if subcmd == "on":
        va.start(live=False)
    elif subcmd == "off":
        va.stop()
    elif subcmd == "live":
        va.start(live=True)
    elif subcmd == "test":
        voice_test()
    elif subcmd in ("devices", "device"):
        list_audio_devices()
    elif subcmd in ("mic", "microphone"):
        if len(parts) > 2 and parts[2].isdigit():
            set_audio_mic(int(parts[2]))
        else:
            console.print("[yellow]Usage: /voice mic <device_index>. Run /voice devices to see device indices.[/yellow]")
    elif subcmd in ("level", "levels", "meter"):
        show_audio_level(duration_sec=5.0)
    else:
        status_md = (
            f"**SuperLocal Voice Assistant Status:**\n\n"
            f"- **State:** `{'Running' if va.is_running else 'Stopped'}`\n"
            f"- **Mode:** `{'Gemini Live' if va.is_live_mode else 'Local Pipeline (faster-whisper + VAD)'}`\n"
            f"- **Conversation Mode:** `{'Active (no wake word needed)' if va.in_conversation_mode() else 'Inactive'}`\n"
            f"- **Wake Word:** `{' / '.join(va.wake_detector.wake_words)}`\n"
            f"- **Push-to-Talk:** `{va.wake_detector.ptt_key.upper()}`\n"
            f"- **Input Device:** `{va.input_device or 'System Default'}`\n"
            f"- **Output Device:** `{va.output_device or 'System Default'}`\n\n"
            f"Commands: `/voice on`, `/voice off`, `/voice live`, `/voice test`, `/voice devices`, `/voice mic <num>`, `/voice level`"
        )
        console.print(Panel(Markdown(status_md), title="Voice Assistant", border_style="cyan"))


def main():
    start_emergency_stop_listener()
    setup_takeover_hotkey()

    # Check for launcher option `superlocal --voice` or `python main.py --voice`
    launch_voice = "--voice" in sys.argv
    if launch_voice:
        sys.argv = [a for a in sys.argv if a != "--voice"]

    # If run with a prompt directly from CLI argument
    if len(sys.argv) > 1:
        raw_prompt = " ".join(sys.argv[1:]).strip()
        single_prompt = re.sub(r'^[\\\'"\s]+|[\\\'"\s]+$', '', raw_prompt).strip()
        if not single_prompt:
            single_prompt = raw_prompt

        if single_prompt.lower() in ("/help", "--help", "-h", "help"):
            print_banner()
            show_help()
            return
        if single_prompt.lower() in ("/shortcuts", "--shortcuts", "shortcuts"):
            show_shortcuts()
            return
        if single_prompt.lower() in ("/health", "health"):
            show_health()
            return
        if single_prompt.lower().startswith("/quota"):
            handle_quota_command(single_prompt)
            return
        if single_prompt.lower().startswith("/voice"):
            handle_voice_command(single_prompt)
            return
        if single_prompt.lower().startswith("/takeover"):
            task = single_prompt[len("/takeover"):].strip()
            task = re.sub(r'^[\\\'"\s]+|[\\\'"\s]+$', '', task).strip()
            if not task:
                console.print("[bold red]Please specify a task for Takeover Mode, e.g.: /takeover open notepad[/bold red]")
                return
            summary = run_takeover_mode(task)
            if summary:
                console.print(Panel(summary, title="Takeover Summary", border_style="green"))
            return
        if single_prompt.lower().startswith("/auto"):
            handle_autopilot_command(single_prompt)
            return
        if single_prompt.lower() in ("/jobs", "jobs") or single_prompt.lower().startswith("/jobs"):
            show_jobs()
            return
        if single_prompt.lower().startswith("@computer") or single_prompt.lower().startswith("/computer"):
            handle_computer_command(single_prompt)
            return
        if single_prompt.lower().startswith("/poki") or single_prompt.lower().startswith("@poki"):
            handle_poki_command(single_prompt)
            return
        if single_prompt.lower().startswith("/optimize"):
            handle_optimizer_command(single_prompt)
            return
        if single_prompt.lower() in ("/selftest", "selftest"):
            from selftest import run_selftest
            run_selftest()
            return
        if single_prompt.lower() in ("/health", "health"):
            show_health()
            return
        if single_prompt.lower().startswith("/openfront") or single_prompt.lower().startswith("@openfront"):
            from openfront import handle_openfront_command
            handle_openfront_command(single_prompt)
            return

        agent = AstraAgent()
        if launch_voice:
            va = get_voice_assistant(agent)
            va.start(live=False)

        console.print(f"[bold cyan]Input:[/bold cyan] {single_prompt}")
        result = agent.run(single_prompt)
        if result:
            console.print(Panel(result, title="Superlocal Summary", border_style="green"))
        close_browser()
        return

    # Interactive REPL Loop
    agent = AstraAgent()
    print_banner(agent.active_provider.name)
    check_startup_providers(agent)

    if launch_voice:
        va = get_voice_assistant(agent)
        va.start(live=False)

    try:
        while True:
            calls_today = agent.memory.get_daily_api_calls()
            if calls_today >= int(QUOTA_PER_DAY * 0.8):
                console.print(f"[bold yellow]Warning: You have used {calls_today}/{QUOTA_PER_DAY} (80%+) of your daily free-tier quota.[/bold yellow]")

            prompt_label = f"[bold green]Superlocal (Requests today: {calls_today}/{QUOTA_PER_DAY}) > [/bold green]"
            try:
                user_input = console.input(prompt_label).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Exiting Superlocal. Goodbye![/dim]")
                break

            if not user_input:
                continue

            # If user pasted/typed `python main.py "..."` inside the interactive prompt
            clean_input = user_input
            for prefix in ("python main.py", "python3 main.py", "py main.py", "python", "py"):
                if clean_input.lower().startswith(prefix):
                    candidate = clean_input[len(prefix):].strip()
                    if candidate:
                        clean_input = candidate
                    break

            clean_input = re.sub(r'^[\\\'"\s]+|[\\\'"\s]+$', '', clean_input).strip()
            if not clean_input:
                clean_input = user_input.strip()

            cmd_lower = clean_input.lower()
            if cmd_lower in ("/exit", "exit", "quit", ":q"):
                console.print("[dim]Shutting down Superlocal...[/dim]")
                break

            if cmd_lower in ("/clear", "cls", "clear"):
                os.system("cls" if os.name == "nt" else "clear")
                print_banner(agent.active_provider.name)
                continue

            if cmd_lower == "/health":
                show_health(agent)
                continue

            if cmd_lower in ("/selftest", "selftest"):
                from selftest import run_selftest
                run_selftest()
                continue

            if cmd_lower in ("/stop", "stop"):
                from safety import trigger_emergency_stop
                trigger_emergency_stop("Interactive /stop command")
                console.print("[bold red]Emergency stop signal triggered.[/bold red]")
                continue

            if cmd_lower.startswith("/openfront") or cmd_lower.startswith("@openfront"):
                from openfront import handle_openfront_command
                handle_openfront_command(clean_input)
                continue

            if cmd_lower.startswith("/quota"):
                handle_quota_command(clean_input, agent.memory)
                continue

            if cmd_lower.startswith("/provider"):
                parts = clean_input.split(maxsplit=1)
                if len(parts) == 1:
                    prov_info = (
                        f"**Current Active Provider:** `{agent.active_provider.name}`\n\n"
                        f"- **Model:** `{agent.active_model}`\n"
                        f"- **Configured Order:** `{' -> '.join(PROVIDER_ORDER)}`\n"
                        f"- **Status:** `{'Online' if agent.active_provider.is_available() else 'Offline / Unreachable'}`\n\n"
                        "To switch provider: `/provider <name>` (e.g. `/provider gemini`, `/provider ollama_local`, `/provider ollama_cloud`)"
                    )
                    console.print(Panel(Markdown(prov_info), title="AI Provider Status", border_style="cyan"))
                else:
                    target_name = parts[1].strip()
                    try:
                        agent.set_provider(target_name)
                        console.print(f"[bold green]Switched active provider to: '{agent.active_provider.name}' (Model: {agent.active_model})[/bold green]")
                    except Exception as e:
                        console.print(f"[bold red]Failed to switch provider:[/bold red] {e}")
                continue

            if cmd_lower == "/models":
                table = Table(title="Ollama Models (Local / Available)", border_style="cyan")
                table.add_column("Model Name", style="bold green")
                table.add_column("Provider / Endpoint", style="dim")
                
                models_found = []
                try:
                    if hasattr(agent.active_provider, "list_models"):
                        models_found = agent.active_provider.list_models()
                    if not models_found:
                        models_found = get_provider("ollama_local").list_models()
                except Exception:
                    pass

                if models_found:
                    for m in models_found:
                        table.add_row(m, "Ollama Local (http://localhost:11434)")
                    console.print(table)
                else:
                    console.print("[bold yellow]No local models found or Ollama is offline at http://localhost:11434.[/bold yellow]")
                    console.print("[dim]To start Ollama: run 'ollama serve' in terminal.[/dim]")
                    console.print("[dim]To pull a model: run 'ollama pull qwen3:8b' or 'ollama pull llama3.1:8b'[/dim]")
                continue

            if cmd_lower.startswith("/voice"):
                handle_voice_command(clean_input, agent)
                continue

            if cmd_lower == "/help":
                show_help()
                continue

            if cmd_lower == "/shortcuts":
                show_shortcuts()
                continue

            if cmd_lower.startswith("/takeover"):
                task = clean_input[len("/takeover"):].strip()
                if not task:
                    task = console.input("[bold cyan]Enter Takeover task:[/bold cyan] ").strip()
                if task:
                    summary = run_takeover_mode(task)
                    if summary:
                        console.print(Panel(summary, title="Takeover Summary", border_style="green"))
                continue

            if cmd_lower.startswith("/auto"):
                handle_autopilot_command(clean_input, agent)
                continue

            if cmd_lower in ("/jobs", "jobs") or cmd_lower.startswith("/jobs"):
                show_jobs()
                continue

            if cmd_lower.startswith("@computer") or cmd_lower.startswith("/computer"):
                handle_computer_command(clean_input, agent)
                continue

            if cmd_lower.startswith("/poki") or cmd_lower.startswith("@poki"):
                handle_poki_command(clean_input, agent.active_provider if agent else None)
                continue

            if cmd_lower.startswith("/optimize"):
                handle_optimizer_command(clean_input)
                continue

            if cmd_lower == "/new":
                agent = AstraAgent()
                console.print(f"[green]Started new session: {agent.session_id}[/green]")
                continue

            if cmd_lower == "/sessions":
                sessions = MemoryManager().list_recent_sessions(limit=5)
                table = Table(title="Recent Sessions", border_style="blue")
                table.add_column("Session ID", style="dim")
                table.add_column("Title", style="bold")
                table.add_column("Last Updated", style="cyan")
                for s in sessions:
                    table.add_row(s["id"], s["title"], str(s["updated_at"]))
                console.print(table)
                continue

            # Send prompt to agent
            summary = agent.run(clean_input)
            if summary:
                console.print(Panel(Markdown(summary), title="Superlocal Summary", border_style="green"))
            console.print("")

    finally:
        try:
            va = get_voice_assistant()
            if va and getattr(va, "is_running", False):
                va.stop()
        except Exception:
            pass
        close_browser()


if __name__ == "__main__":
    main()
