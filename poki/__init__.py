"""
SuperLocal Poki Player: Games Workbench Module
Plays single-player browser games on https://poki.com using a tiered approach:
- Commands: /poki play <game> [--goal ...], /poki list, /poki learn <game>, /poki stats, /poki stop
- Single-player games ONLY: strict refusal for multiplayer / PvP / .io games
- Fast local capture (15-30 FPS) with zero cloud calls in the frame loop
- Solver/rule-based skills for 2048, Sudoku, Match-3, Endless Runner, Snake
- Automatic replay logging & performance statistics
"""

import re
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table

from safety import trigger_emergency_stop
from poki.guards import check_single_player_or_refuse, print_poki_terms_notice_once
from poki.skills import list_available_skills, get_skill_for_game
from poki.stats import PokiStatsManager
from poki.runner import PokiGameRunner
from poki.learner import PokiLearner

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


def handle_poki_command(cmd: str, provider=None) -> str:
    """
    Dispatches Poki commands:
    /poki play <game> [--goal "..."]
    /poki list
    /poki learn <game>
    /poki stats
    /poki stop
    """
    clean_cmd = cmd.strip()
    clean_lower = clean_cmd.lower()

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
            console.print("[yellow]No Poki games played yet. Use '/poki play 2048' to start.[/yellow]")
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

    # 4. /poki learn <game>
    elif sub == "learn":
        game_to_learn = parts[2] if len(parts) > 2 else ""
        if not game_to_learn:
            console.print("[bold red]Please specify a game to learn, e.g.: /poki learn subway-surfers[/bold red]")
            return "Missing game name for learning."

        learner = PokiLearner(game_to_learn, provider=provider)
        res = learner.learn_and_save_skill()
        return res["summary"]

    # 5. /poki play <game> [--goal "..."]
    elif sub == "play":
        rem = clean_cmd[clean_cmd.lower().find("play") + 4:].strip()
        goal_text = ""
        goal_match = re.search(r"--goal\s+[\"']?([^\"']+)[\"']?", rem, re.IGNORECASE)
        if goal_match:
            goal_text = goal_match.group(1).strip()
            game_name = re.sub(r"--goal\s+[\"']?([^\"']+)[\"']?", "", rem, flags=re.IGNORECASE).strip()
        else:
            game_name = rem.strip()

        if not game_name:
            console.print("[bold red]Please specify a game name or URL, e.g.: /poki play 2048 --goal 'reach 2048'[/bold red]")
            return "Missing game name for play."

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
            "  /poki stop                                              - Stop active gameplay"
        )
        console.print(help_text)
        return "Displayed Poki help."


__all__ = [
    "handle_poki_command",
    "list_poki_skills",
    "get_poki_stats",
    "stop_poki_player",
    "PokiGameRunner",
    "PokiLearner",
    "check_single_player_or_refuse",
]
