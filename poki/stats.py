"""
SuperLocal Poki Player: Metrics, Stats & Replay Logging
- Tracks per-game metrics: runs, total time, highest score, average score, success rate
- Saves and loads stats from DATA_DIR / "poki_stats.json"
- Action replay logger: saves action traces to logs/poki_replays/<game>_<timestamp>.json
- Optional video recorder: records canvas MP4 using OpenCV VideoWriter if SAVE_VIDEO=True
"""

import os
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import cv2
import numpy as np

from config import POKI_STATS_PATH, POKI_REPLAYS_DIR, POKI_LOG_PATH, SAVE_VIDEO


class PokiStatsManager:
    """
    Persists and computes per-game performance analytics.
    """

    def __init__(self, stats_path: Path = POKI_STATS_PATH):
        self.stats_path = stats_path
        self.stats: Dict[str, Dict[str, Any]] = self._load_stats()

    def _load_stats(self) -> Dict[str, Dict[str, Any]]:
        if self.stats_path.exists():
            try:
                return json.loads(self.stats_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_stats(self):
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        self.stats_path.write_text(json.dumps(self.stats, indent=2), encoding="utf-8")

    def record_run(
        self,
        game_name: str,
        score: float,
        survival_seconds: float,
        goal_reached: bool = False
    ):
        """Records the results of a game run."""
        clean_name = game_name.lower().strip()
        if clean_name not in self.stats:
            self.stats[clean_name] = {
                "runs": 0,
                "high_score": 0.0,
                "total_score": 0.0,
                "average_score": 0.0,
                "total_survival_time": 0.0,
                "successful_runs": 0,
                "success_rate": 0.0,
                "last_played": "",
            }

        entry = self.stats[clean_name]
        entry["runs"] += 1
        entry["total_score"] += score
        entry["average_score"] = round(entry["total_score"] / entry["runs"], 1)
        entry["high_score"] = max(entry["high_score"], score)
        entry["total_survival_time"] += survival_seconds
        if goal_reached:
            entry["successful_runs"] += 1
        entry["success_rate"] = round((entry["successful_runs"] / entry["runs"]) * 100.0, 1)
        entry["last_played"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.save_stats()
        self._log_run_to_file(clean_name, score, survival_seconds, goal_reached)

    def _log_run_to_file(self, game: str, score: float, dur: float, success: bool):
        POKI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{now}] GAME={game} SCORE={score} DURATION={dur:.1f}s GOAL_REACHED={success}\n"
        with open(POKI_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)

    def get_game_stats(self, game_name: str) -> Optional[Dict[str, Any]]:
        return self.stats.get(game_name.lower().strip())

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        return self.stats


class GameReplayRecorder:
    """
    Records action sequences and optional MP4 video of the canvas.
    """

    def __init__(self, game_name: str, save_video: bool = SAVE_VIDEO):
        self.game_name = game_name.lower().replace(" ", "_")
        self.save_video = save_video
        self.start_time = time.time()
        self.actions_log: List[Dict[str, Any]] = []

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.json_path = POKI_REPLAYS_DIR / f"{self.game_name}_{timestamp}.json"
        self.video_path = POKI_REPLAYS_DIR / f"{self.game_name}_{timestamp}.mp4"

        self.video_writer = None
        self.fps = 24

    def log_action(self, action: str, score: float = 0.0, extra: Optional[Dict[str, Any]] = None):
        """Records an action event with relative timestamp."""
        elapsed = round(time.time() - self.start_time, 3)
        self.actions_log.append({
            "t": elapsed,
            "action": action,
            "score": score,
            **(extra or {})
        })

    def record_frame(self, frame: np.ndarray):
        """Appends a video frame if SAVE_VIDEO is enabled."""
        if not self.save_video or frame is None:
            return

        h, w = frame.shape[:2]
        if self.video_writer is None:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(str(self.video_path), fourcc, self.fps, (w, h))

        # Ensure 3-channel BGR
        if len(frame.shape) == 2:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            frame_bgr = frame

        self.video_writer.write(frame_bgr)

    def finalize(self, final_score: float = 0.0) -> Dict[str, Any]:
        """Saves replay JSON and closes video writer."""
        POKI_REPLAYS_DIR.mkdir(parents=True, exist_ok=True)

        replay_data = {
            "game": self.game_name,
            "recorded_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "final_score": final_score,
            "duration": round(time.time() - self.start_time, 2),
            "total_actions": len(self.actions_log),
            "actions": self.actions_log
        }
        self.json_path.write_text(json.dumps(replay_data, indent=2), encoding="utf-8")

        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        return {
            "json_replay": str(self.json_path),
            "video_path": str(self.video_path) if self.save_video else None
        }
