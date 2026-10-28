"""
SuperLocal Poki Player: Skills Registry & Loader
Provides access to built-in and dynamically learned game skills:
1. 2048 (Expectimax / Corner-Stack Solver)
2. Sudoku (MRV Backtracking Solver)
3. Match-3 / Mahjong (Cascade Best-Swap Solver)
4. Endless Runner (Obstacle Threshold Policy)
5. Snake (Safe BFS Pathfinding Policy)
6. Little Master Cricket (HSV Ball Tracking & Bat Swing Policy)
"""

from typing import Dict, Any, List, Optional
from poki.skills.base import BaseSkill
from poki.skills.game_2048 import Game2048Skill
from poki.skills.sudoku import SudokuSkill
from poki.skills.match3 import Match3Skill
from poki.skills.runner import EndlessRunnerSkill
from poki.skills.snake import SnakeSkill
from poki.skills.cricket import LittleMasterCricketSkill

_BUILTIN_SKILLS: List[BaseSkill] = [
    Game2048Skill(),
    SudokuSkill(),
    Match3Skill(),
    EndlessRunnerSkill(),
    SnakeSkill(),
    LittleMasterCricketSkill(),
]


def list_available_skills() -> List[Dict[str, Any]]:
    """Returns metadata for all available Poki game skills."""
    skills_info = []
    for s in _BUILTIN_SKILLS:
        skills_info.append({
            "name": s.name,
            "slug": s.slug,
            "supported_games": s.supported_games,
            "controls": s.controls,
            "average_score": s.average_score,
            "status": "Ready",
        })
    return skills_info


def get_skill_for_game(game_query: str) -> Optional[BaseSkill]:
    """
    Matches game name or URL to the best skill instance.
    """
    clean = game_query.lower().strip()
    # Strip URL prefix if provided
    if "poki.com" in clean:
        clean = clean.split("/")[-1]

    clean = clean.replace(".html", "").replace("_", "-")

    for s in _BUILTIN_SKILLS:
        if clean in s.slug or clean in s.supported_games:
            return s
        if any(clean in g or g in clean for g in s.supported_games):
            return s

    return None


__all__ = [
    "BaseSkill",
    "Game2048Skill",
    "SudokuSkill",
    "Match3Skill",
    "EndlessRunnerSkill",
    "SnakeSkill",
    "LittleMasterCricketSkill",
    "get_skill_for_game",
    "list_available_skills",
]
