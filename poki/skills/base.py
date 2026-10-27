"""
SuperLocal Poki Player: Base Skill Interface
All game skills inherit from BaseSkill:
- State detection
- Score extraction
- Autonomous policy/solver decision logic
- Action execution
"""

import time
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np

from poki.state_detector import GameState, StateDetector


class BaseSkill:
    """
    Abstract interface for a Poki game skill.
    """
    name: str = "Base Skill"
    slug: str = "base"
    supported_games: List[str] = []
    controls: List[str] = ["arrows"]
    average_score: float = 0.0

    def __init__(self):
        self.state_detector = StateDetector()
        self.current_score: float = 0.0
        self.step_count: int = 0

    def reset(self):
        """Resets internal game state between runs."""
        self.current_score = 0.0
        self.step_count = 0

    def detect_state(self, frame: np.ndarray, page=None) -> GameState:
        """Classifies game state (Menu, Playing, Game Over, etc.)."""
        return self.state_detector.detect_state_from_frame(frame)

    def get_score(self, frame: np.ndarray, page=None) -> float:
        """Extracts current score from DOM or visual state."""
        return self.current_score

    def decide_action(self, frame: np.ndarray, page=None) -> Optional[Dict[str, Any]]:
        """
        Calculates the next optimal control action.
        Returns dict like: {"action": "press", "key": "ArrowUp"} or {"action": "click", "x": 100, "y": 200}
        """
        raise NotImplementedError("Subclasses must implement decide_action.")

    def execute_action(self, action: Optional[Dict[str, Any]], page=None):
        """Dispatches action via Playwright page or local input."""
        if not action:
            return

        act_type = action.get("action", "").lower()

        if act_type == "press" and page:
            key = action.get("key", "")
            try:
                page.keyboard.press(key)
            except Exception:
                pass

        elif act_type == "click" and page:
            x, y = action.get("x", 0), action.get("y", 0)
            try:
                page.mouse.click(x, y)
            except Exception:
                pass

        elif act_type == "drag" and page:
            from_x, from_y = action.get("from", (0, 0))
            to_x, to_y = action.get("to", (0, 0))
            try:
                page.mouse.move(from_x, from_y)
                page.mouse.down()
                page.mouse.move(to_x, to_y, steps=5)
                page.mouse.up()
            except Exception:
                pass
