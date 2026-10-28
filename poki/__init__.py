"""
SuperLocal Poki Player: Games Workbench Module
Plays single-player browser games on https://poki.com using a tiered approach:
- Commands: /poki play <game> [--goal ...], /poki list, /poki learn <game>, /poki stats, /poki stop, /poki debug
- Single-player games ONLY: strict refusal for multiplayer / PvP / .io games
- Fast local capture (15-30 FPS) with zero cloud calls in the frame loop
- Built-in skills for 2048, Sudoku, Match-3, Endless Runner, Snake, Little Master Cricket
- Automatic replay logging & performance statistics
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import cv2
from rich.console import Console
from rich.table import Table

from config import LOGS_DIR
from safety import trigger_emergency_stop
from poki.guards import check_single_player_or_refuse, print_poki_terms_notice_once
from poki.skills import list_available_skills, get_skill_for_game
from poki.stats import PokiStatsManager
from poki.runner import PokiGameRunner
from poki.learner import PokiLearner
from poki.launcher import PokiGameLauncher, normalize_poki_url
from poki.state_detector import StateDetector
from poki.capture import GameCanvasCapture
from tools.browser import get_active_game_page, get_browser_page, get_active_tab_url

console = Console()


def list_poki_skills() -> List[Dict[str, Any]]:
    """Returns available skills list."""
    return list_available_skills()


def get_poki_stats() -> Dict[str, Any]:
    """Returns all recorded stats."""
    return PokiStatsManager().get_all_stats()


def stop_poki_player():
    """Triggers emergency stop for active Poki sessions."""
    trigger_emergency_stop("Poki session stopped via /poki stop")
    console.print("[bold red][Poki] Stopped active game loop.[/bold red]")


def run_poki_debug(game_query: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes /poki debug:
    - Prints active page URL and title
    - Finds canvas, shows size (w, h) and bounding box
    - Saves one canvas image to logs/poki_debug_canvas.png
    - Reports detected state (MENU, PLAYING, GAME_OVER)
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    debug_snapshot_path = LOGS_DIR / "poki_debug_canvas.png"

    launcher = PokiGameLauncher()
    page = None

    # If game_query given, launch it or ensure it's loaded
    if game_query and game_query.strip():
        ok, msg, p = launcher.launch_game(game_query.strip())
        if ok and p:
            page = p

    if page is None:
        try:
            page = get_active_game_page()
        except Exception:
            page = None

    if page is None or page.is_closed():
        try:
            page = get_browser_page()
        except Exception:
            pass

    active_url = "No active browser tab"
    active_title = "Unknown"
    if page and not page.is_closed():
        try:
            active_url = page.url
            active_title = page.title()
        except Exception:
            pass

    console.print(f"[bold cyan][Poki Debug][/bold cyan] Active Page URL: [yellow]{active_url}[/yellow]")
    console.print(f"[bold cyan][Poki Debug][/bold cyan] Active Page Title: [yellow]{active_title}[/yellow]")

    # Find canvas
    bounds = launcher.detect_game_canvas_bounds(page) if page else None
    if not bounds and launcher.canvas_bounds and launcher.canvas_bounds[2] > 50 and launcher.canvas_bounds[3] > 50:
        bounds = launcher.canvas_bounds
    if bounds:
        x, y, w, h = bounds
        console.print(f"[bold green][Poki Debug][/bold green] Canvas Bounding Box: ({x}, {y}, {w}, {h}) | Size: {w}x{h}")
    else:
        bounds = (0, 0, 1280, 800)
        x, y, w, h = bounds
        console.print(f"[yellow][Poki Debug] Canvas element not detected directly; using viewport bounds: {bounds}[/yellow]")

    # Capture one frame
    capture = GameCanvasCapture(bounding_box=bounds, downscale_size=(640, 360))
    frame = capture.capture_frame(page=page)

    # If frame is None or empty (e.g. mock or headless without window), create a placeholder
    if frame is None or frame.size == 0:
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            f"Poki Debug: {active_title[:30]}",
            (20, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )

    # Save to logs/poki_debug_canvas.png
    try:
        cv2.imwrite(str(debug_snapshot_path), frame)
        console.print(f"[bold green][Poki Debug][/bold green] Saved canvas debug snapshot to: [underline]{debug_snapshot_path}[/underline]")
    except Exception as e:
        console.print(f"[yellow][Poki Debug] Snapshot save notice: {e}[/yellow]")

    # Run state detector
    detector = StateDetector()
    detected_state = detector.detect_state_from_frame(frame)
    console.print(f"[bold cyan][Poki Debug][/bold cyan] Detected Game State: [bold yellow]{detected_state.value}[/bold yellow]")

    summary = (
        f"Poki Debug: URL={active_url} | "
        f"Canvas={w}x{h} at ({x}, {y}) | "
        f"State={detected_state.value} | "
        f"Snapshot={debug_snapshot_path.name}"
    )

    return {
        "url": active_url,
        "title": active_title,
        "bounds": bounds,
        "size": (w, h),
        "state": detected_state.value,
        "snapshot_path": str(debug_snapshot_path),
        "summary": summary,
    }


def handle_poki_command(cmd: str, provider=None) -> str:
    """
    Dispatches Poki commands:
    /poki play <game> [--goal "..."]
    /poki list
    /poki learn <game>
    /poki stats
    /poki stop
    /poki debug [<game>]
    """
    clean_cmd = cmd.strip()

    # Strip /poki or @poki prefix
    parts = re.split(r"\s+", clean_cmd)
    sub = parts[1].lower() if len(parts) > 1 else "help"

    # 1. /poki list
    if sub in ("list", "skills"):
        skills = list_available_skills()
        table = Table(title="Poki Player: Available Game Skills", border_style="cyan")
        table.add_column("Skill Name", style="bold cyan")
        table.add_column("Slug", style="magenta")
        table.add_column("Supported Games", style="white")
        table.add_column("Avg Benchmark Score", style="green")
        table.add_column("Status", style="yellow")

        for s in skills:
            table.add_row(
                s["name"],
                s["slug"],
                ", ".join(s["supported_games"][:3]),
                f"{s['average_score']:.1f}",
                s["status"]
            )
        console.print(table)
        return f"Loaded {len(skills)} ready game skills."

    # 2. /poki stats
    elif sub in ("stats", "metrics", "history"):
        stats = get_poki_stats()
        if not stats:
            console.print("[yellow]No Poki games played yet. Use '/poki play cricket' to start.[/yellow]")
            return "No Poki stats recorded yet."

        table = Table(title="Poki Player: Game Performance Stats", border_style="cyan")
        table.add_column("Game", style="bold cyan")
        table.add_column("Runs", style="white")
        table.add_column("High Score", style="bold green")
        table.add_column("Avg Score", style="green")
        table.add_column("Success Rate", style="yellow")
        table.add_column("Total Playtime", style="dim")
        table.add_column("Last Played", style="dim")

        for game, data in stats.items():
            table.add_row(
                game.title(),
                str(data.get("runs", 0)),
                str(int(data.get("high_score", 0))),
                str(data.get("average_score", 0)),
                f"{data.get('success_rate', 0)}%",
                f"{data.get('total_survival_time', 0):.1f}s",
                str(data.get("last_played", ""))
            )
        console.print(table)
        return f"Displayed performance stats for {len(stats)} games."

    # 3. /poki stop
    elif sub == "stop":
        stop_poki_player()
        return "Poki game loop stopped."

    # 4. /poki debug [<game>]
    elif sub == "debug":
        game_arg = " ".join(parts[2:]).strip() if len(parts) > 2 else ""
        res = run_poki_debug(game_arg if game_arg else None)
        return res["summary"]

    # 5. /poki learn <game>
    elif sub == "learn":
        game_to_learn = parts[2] if len(parts) > 2 else ""
        if not game_to_learn:
            console.print("[bold red]Please specify a game to learn, e.g.: /poki learn subway-surfers[/bold red]")
            return "Missing game name for learning."

        learner = PokiLearner(game_to_learn, provider=provider)
        res = learner.learn_and_save_skill()
        return res["summary"]

    # 6. /poki play <game> [--goal "..."]
    elif sub == "play":
        rem = clean_cmd[clean_cmd.lower().find("play") + 4:].strip()
        goal_text = ""
        goal_match = re.search(r"--goal\s+[\"']?([^\"']+)[\"']?", rem, re.IGNORECASE)
        if goal_match:
            goal_text = goal_match.group(1).strip()
            game_name = re.sub(r"--goal\s+[\"']?([^\"']+)[\"']?", "", rem, flags=re.IGNORECASE).strip()
        else:
            game_name = rem.strip()

        # If game name is empty, check active Playwright tab
        if not game_name:
            active_url = get_active_tab_url()
            if active_url and "poki.com/en/g/" in active_url:
                slug_match = re.search(r"poki\.com/en/g/([a-zA-Z0-9_\-]+)", active_url)
                if slug_match:
                    game_name = slug_match.group(1)
                    console.print(f"[dim]Detected active Poki game from browser tab: {game_name}[/dim]")

        if not game_name:
            # Fallback to cricket as default single-player skill
            game_name = "little-master-cricket"
            console.print(f"[dim]No game specified; defaulting to: {game_name}[/dim]")

        runner = PokiGameRunner(game_name, goal_text=goal_text, provider=provider)
        res = runner.play()
        return res.get("summary", "Session complete.")

    else:
        # Help text
        help_text = (
            "[bold cyan]Poki Player Commands:[/bold cyan]\n"
            "  /poki play <game> [--goal 'score 2000' | 'play 10 min'] - Play single-player game\n"
            "  /poki list                                              - Show supported game skills\n"
            "  /poki learn <game>                                      - Synthesize skill for new game\n"
            "  /poki stats                                             - View scores & performance history\n"
            "  /poki debug [<game>]                                    - Inspect canvas & save debug snapshot\n"
            "  /poki stop                                              - Stop active gameplay"
        )
        console.print(help_text)
        return "Displayed Poki help."


__all__ = [
    "handle_poki_command",
    "run_poki_debug",
    "list_poki_skills",
    "get_poki_stats",
    "stop_poki_player",
    "PokiGameRunner",
    "PokiLearner",
    "check_single_player_or_refuse",
]
