"""
SuperLocal Poki Skills Alias Package
Forwards all skills to poki.skills
"""

import sys
from poki.skills import (
    BaseSkill,
    Game2048Skill,
    SudokuSkill,
    Match3Skill,
    EndlessRunnerSkill,
    SnakeSkill,
    LittleMasterCricketSkill,
    get_skill_for_game,
    list_available_skills,
)
import poki.skills.cricket as cricket

__all__ = [
    "BaseSkill",
    "Game2048Skill",
    "SudokuSkill",
    "Match3Skill",
    "EndlessRunnerSkill",
    "SnakeSkill",
    "LittleMasterCricketSkill",
    "cricket",
    "get_skill_for_game",
    "list_available_skills",
]
