"""
SuperLocal Poki Player: State Detector
Detects game states (Menu, Playing, Game Over, Level Complete, Paused):
- OpenCV template matching (cv2.matchTemplate)
- Color histogram and dominant color thresholding
- DOM and text heuristics
"""

import cv2
import numpy as np
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List


class GameState(Enum):
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"
    LEVEL_COMPLETE = "level_complete"
    UNKNOWN = "unknown"


class StateDetector:
    """
    Computer vision state detector using template matching and color checks.
    """

    def __init__(self, templates: Optional[Dict[str, np.ndarray]] = None):
        """
        templates: dict of state_name -> template_image_array
        """
        self.templates: Dict[str, np.ndarray] = templates or {}
        self.match_threshold: float = 0.70

    def add_template(self, state_name: str, template_img: np.ndarray):
        """Registers a template image for a specific state (e.g. 'game_over', 'play_btn')."""
        if len(template_img.shape) == 3:
            gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = template_img
        self.templates[state_name] = gray

    def match_template(self, frame: np.ndarray, template: np.ndarray) -> Tuple[bool, float, Tuple[int, int]]:
        """
        Runs cv2.matchTemplate and returns (found, max_val, max_loc).
        """
        if frame is None or template is None:
            return False, 0.0, (0, 0)

        # Convert to grayscale if needed
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if len(template.shape) == 3 else template

        if frame_gray.shape[0] < tmpl_gray.shape[0] or frame_gray.shape[1] < tmpl_gray.shape[1]:
            return False, 0.0, (0, 0)

        res = cv2.matchTemplate(frame_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        found = max_val >= self.match_threshold
        return found, float(max_val), max_loc

    def detect_state_from_frame(self, frame: np.ndarray) -> GameState:
        """
        Evaluates registered templates and image properties to classify current state.
        """
        if frame is None or frame.size == 0:
            return GameState.UNKNOWN

        # 1. Check game over templates
        for name, tmpl in self.templates.items():
            if "game_over" in name or "restart" in name or "retry" in name:
                matched, score, _ = self.match_template(frame, tmpl)
                if matched:
                    return GameState.GAME_OVER

        # 2. Check level complete templates
        for name, tmpl in self.templates.items():
            if "complete" in name or "victory" in name or "win" in name:
                matched, score, _ = self.match_template(frame, tmpl)
                if matched:
                    return GameState.LEVEL_COMPLETE

        # 3. Check menu / play button templates
        for name, tmpl in self.templates.items():
            if "play" in name or "menu" in name or "start" in name:
                matched, score, _ = self.match_template(frame, tmpl)
                if matched:
                    return GameState.MENU

        # 4. Color variance heuristic: completely black or static single color is not playing
        if len(frame.shape) == 3:
            std_dev = np.std(frame)
            if std_dev < 5.0:
                return GameState.PAUSED

        # Default assumption if screen is dynamic
        return GameState.PLAYING

    def detect_color_presence(
        self,
        frame: np.ndarray,
        lower_bgr: Tuple[int, int, int],
        upper_bgr: Tuple[int, int, int],
        min_pixel_ratio: float = 0.02
    ) -> bool:
        """
        Checks if a specified color range covers at least min_pixel_ratio of the frame.
        Useful for detecting Game Over overlays (e.g. red/dark translucent overlay).
        """
        if frame is None or frame.size == 0:
            return False

        mask = cv2.inRange(frame, np.array(lower_bgr), np.array(upper_bgr))
        ratio = np.count_nonzero(mask) / float(frame.shape[0] * frame.shape[1])
        return ratio >= min_pixel_ratio
