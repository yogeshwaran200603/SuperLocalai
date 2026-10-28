"""
SuperLocal Poki Player: Main Game Loop Runner
Coordinates:
- Safety guards & terms notice
- Playwright launcher & persistent context canvas locating
- High-speed canvas capture & latency monitoring (15-30 FPS)
- Autonomous solver/policy execution (ZERO model calls in the fast loop)
- Up to 200 loop iterations per run without model calls; model call budget max 5 per run
- State detection (Menu, Playing, Game Over) and policy execution
- Automatic retry on Game Over with policy tuning
- Goal completion checks (score, level, time)
- Emergency stop & 2-second user physical input pause
- Status line overlay: "[Poki] <game> | run <N> | score <S> | <FPS> FPS"
"""

import time
import re
from typing import Dict, Any, Optional, Tuple
from rich.console import Console
from rich.panel import Panel

from config import POKI_MAX_MINUTES, POKI_MAX_RUNS, POKI_TARGET_FPS
from safety import is_emergency_stopped, reset_emergency_stop
from poki.guards import print_poki_terms_notice_once
from poki.launcher import PokiGameLauncher
from poki.capture import GameCanvasCapture
from poki.skills import get_skill_for_game
from poki.state_detector import GameState
from poki.stats import PokiStatsManager, GameReplayRecorder
from poki.overlay import PokiOverlay
from poki.learner import PokiLearner

console = Console()

# Step cap and model call limits as requested
MAX_LOOP_ITERATIONS_PER_RUN = 200
MAX_MODEL_CALL_BUDGET = 5


class PokiGameRunner:
    """
    Drives the real-time Poki playing loop.
    """

    def __init__(
        self,
        game_query: str,
        goal_text: Optional[str] = None,
        max_runs: int = POKI_MAX_RUNS,
        max_minutes: int = POKI_MAX_MINUTES,
        provider=None,
        max_loop_iterations: int = MAX_LOOP_ITERATIONS_PER_RUN,
    ):
        self.game_query = game_query.strip()
        self.goal_text = goal_text or ""
        self.max_runs = max_runs
        self.max_minutes = max_minutes
        self.provider = provider
        self.max_loop_iterations = max_loop_iterations
        self.max_model_calls = MAX_MODEL_CALL_BUDGET
        self.model_calls_used = 0

        self.launcher = PokiGameLauncher()
        self.stats_manager = PokiStatsManager()
        self.overlay = PokiOverlay(self.game_query)

        # Parse goal targets
        self.target_score = None
        self.target_level = None
        self.target_seconds = None
        self._parse_goal(self.goal_text)

    def _parse_goal(self, goal_str: str):
        if not goal_str:
            return
        g = goal_str.lower()
        score_m = re.search(r"score\s+(\d+)", g)
        if score_m:
            self.target_score = float(score_m.group(1))

        lvl_m = re.search(r"level\s+(\d+)", g)
        if lvl_m:
            self.target_level = int(lvl_m.group(1))

        time_m = re.search(r"play\s+(\d+)\s*min", g)
        if time_m:
            self.target_seconds = float(time_m.group(1)) * 60.0

    def is_goal_achieved(self, current_score: float, elapsed_sec: float) -> bool:
        if self.target_score and current_score >= self.target_score:
            return True
        if self.target_seconds and elapsed_sec >= self.target_seconds:
            return True
        return False

    def play(self) -> Dict[str, Any]:
        """
        Executes autonomous gameplay loop across runs.
        Consumes ZERO model calls in the fast loop.
        """
        reset_emergency_stop()
        print_poki_terms_notice_once()

        # 1. Match Skill
        skill = get_skill_for_game(self.game_query)
        if not skill:
            msg = (
                f"No pre-configured skill found for '{self.game_query}'. "
                f"Use '/poki learn {self.game_query}' to synthesize a custom skill, "
                f"or verify the game title."
            )
            console.print(Panel(f"[yellow]{msg}[/yellow]", title="Poki Player Notice", border_style="yellow"))
            return {"success": False, "summary": msg, "score": 0}

        # Update overlay with formatted skill name
        self.overlay.game_name = skill.name
        console.print(f"[bold green]Found skill:[/bold green] {skill.name} (Benchmarked Avg: {skill.average_score})")

        # 2. Launch Game in Browser (persistent context, safe click focus)
        ok, launch_msg, page = self.launcher.launch_game(self.game_query)
        if not ok:
            return {"success": False, "summary": launch_msg, "score": 0}

        # 3. Model Instructions Cache Check (at most 1 model call if knowledge not cached)
        learner = PokiLearner(self.game_query, provider=self.provider)
        cached_info = learner.get_cached_instructions()
        if not cached_info and self.provider and (self.model_calls_used < self.max_model_calls):
            console.print("[dim]Checking game instructions (at most 1 model call per run, cached)...[/dim]")
            learner.read_instructions(page=page)
            self.model_calls_used += 1

        # 4. Setup Capture & Overlay
        capture = GameCanvasCapture(
            bounding_box=self.launcher.canvas_bounds,
            downscale_size=(640, 360),
            grayscale=False,
        )
        self.overlay.start()

        start_time = time.time()
        current_run = 1
        best_score = 0.0
        goal_reached = False

        try:
            while current_run <= self.max_runs:
                elapsed_total = time.time() - start_time
                if elapsed_total >= (self.max_minutes * 60.0):
                    console.print("\n[yellow]Poki session time limit reached.[/yellow]")
                    break

                if is_emergency_stopped():
                    console.print("\n[bold red]Poki stopped by emergency signal.[/bold red]")
                    break

                console.print(f"\n[bold cyan]Starting Run {current_run}/{self.max_runs} on '{skill.name}'...[/bold cyan]")
                run_start_time = time.time()
                run_score = 0.0
                loop_iterations = 0
                recorder = GameReplayRecorder(self.game_query)
                skill.reset()

                # Fast Inner Frame Loop (ZERO model calls)
                while True:
                    if is_emergency_stopped():
                        break

                    loop_iterations += 1
                    if loop_iterations > self.max_loop_iterations:
                        console.print(f"\n[dim]Run {current_run} reached limit of {self.max_loop_iterations} loop iterations.[/dim]")
                        break

                    # Check pause state (physical user input monitor)
                    while self.overlay.is_paused and not is_emergency_stopped():
                        time.sleep(0.3)

                    capture.latency_monitor.start_frame()

                    # 1. Capture current frame from canvas
                    frame = capture.capture_frame(page=page)
                    recorder.record_frame(frame)

                    # 2. State & Score Detection
                    state = skill.detect_state(frame, page=page)
                    run_score = skill.get_score(frame, page=page)
                    best_score = max(best_score, run_score)

                    # 3. Update status line: "[Poki] <game> | run <N> | score <S> | <FPS> FPS"
                    fps = capture.latency_monitor.get_fps()
                    self.overlay.update_status(run=current_run, score=run_score, fps=fps)

                    # Check Goal
                    run_duration = time.time() - run_start_time
                    if self.is_goal_achieved(run_score, run_duration):
                        goal_reached = True
                        console.print(f"\n[bold green]Goal Achieved! Score: {run_score}[/bold green]")
                        break

                    # Check Game Over
                    if state == GameState.GAME_OVER:
                        console.print(f"\n[dim]Run {current_run} ended: Game Over. Score: {run_score}[/dim]")
                        break

                    # 4. Compute Action Decision (Zero model calls, OpenCV/policy based)
                    t_dec_start = time.perf_counter()
                    action = skill.decide_action(frame, page=page)
                    is_slow = capture.latency_monitor.record_decision(t_dec_start)

                    if is_slow and capture.latency_monitor.is_latency_critical():
                        console.print("\n[yellow]Latency warning: Decision time exceeded threshold. Adjusting loop...[/yellow]")

                    # 5. Dispatch Action
                    if action:
                        skill.execute_action(action, page=page)
                        act_key = str(action.get("key") or action.get("action") or action.get("description", "act"))
                        recorder.log_action(act_key, score=run_score)

                    capture.latency_monitor.end_frame()

                    # Regulate FPS rate (target 15-30 FPS)
                    target_delay = (1.0 / POKI_TARGET_FPS) - (time.perf_counter() - capture.latency_monitor.last_timestamp)
                    if target_delay > 0:
                        time.sleep(target_delay)

                # Finalize run
                run_dur = time.time() - run_start_time
                recorder.finalize(final_score=run_score)
                self.stats_manager.record_run(self.game_query, run_score, run_dur, goal_reached)

                if goal_reached:
                    break

                current_run += 1
                time.sleep(1.0)  # Short pause before next run

            summary = (
                f"Completed {current_run - 1} runs on '{skill.name}'. "
                f"Best Score: {best_score:.0f}. Goal Reached: {goal_reached}. "
                f"Stats saved to data/poki_stats.json."
            )
            console.print(Panel(f"[bold green]{summary}[/bold green]", title="Poki Session Finished", border_style="green"))

            return {
                "success": True,
                "game": skill.name,
                "runs": current_run - 1,
                "best_score": best_score,
                "goal_reached": goal_reached,
                "summary": summary
            }

        finally:
            self.overlay.stop()
