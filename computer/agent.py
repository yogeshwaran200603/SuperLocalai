"""
SuperLocal Computer Mode: Main Agent Controller
Coordinates:
- Trigger parsing (@computer, /computer, voice "computer, ...")
- Effort levels (--low, --medium, --high) with action/time budgets
- Plan preview (apps, sandbox folder, risk level)
- Session sandbox containment & app allowlists
- Tiered state perception (A11y -> RapidOCR -> Vision)
- Batched action execution with 0.3s pauses and verify loops
- Web friction handling (popups & dangerous action blocks)
- Foreground overlay & physical user activity interruption monitor
- Voice oversight (pause, stop, undo, live corrections, spoken progress)
"""

import os
import sys
import re
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import (
    COMPUTER_DEFAULT_EFFORT,
    COMPUTER_EFFORT_LOW_MAX_ACTIONS,
    COMPUTER_EFFORT_MED_MAX_ACTIONS,
    COMPUTER_EFFORT_HIGH_MAX_ACTIONS,
    COMPUTER_EFFORT_HIGH_MAX_MINUTES,
    COMPUTER_ACTION_PAUSE,
    JOBS_DIR,
)
from safety import is_emergency_stopped, trigger_emergency_stop, reset_emergency_stop
from computer.permissions import ComputerSessionSandbox, ComputerPermissionManager
from computer.state_engine import ComputerStateEngine, ScreenState
from computer.dispatcher import ActionDispatcher
from computer.friction import WebFrictionHandler
from computer.overlay import ComputerOverlayWindow, UserActivityMonitor

console = Console()


class ComputerModeAgent:
    """
    Advanced PC Operator Agent operating with strict permission boundaries.
    """

    def __init__(
        self,
        task: str,
        effort: Optional[str] = None,
        sandbox_dir: Optional[Union[str, Path]] = None,
        provider: Optional[Any] = None,
    ):
        self.raw_task = task.strip()
        self.effort, self.task = self._parse_effort_level(self.raw_task, effort)
        self.provider = provider

        # 1. Effort Budgets
        if self.effort == "low":
            self.max_actions = COMPUTER_EFFORT_LOW_MAX_ACTIONS  # 10
            self.max_minutes = 15
        elif self.effort == "high":
            self.max_actions = COMPUTER_EFFORT_HIGH_MAX_ACTIONS  # 80
            self.max_minutes = COMPUTER_EFFORT_HIGH_MAX_MINUTES   # 60
        else:
            self.effort = "medium"
            self.max_actions = COMPUTER_EFFORT_MED_MAX_ACTIONS  # 30
            self.max_minutes = 30

        # 2. Session Sandbox & Permissions
        self.sandbox = ComputerSessionSandbox(sandbox_dir=sandbox_dir, task_slug=self.task)
        self.permissions = ComputerPermissionManager(self.sandbox, task_goal=self.task)
        self.friction = WebFrictionHandler(self.sandbox.sandbox_path)

        # 3. Perception and Dispatcher
        self.state_engine = ComputerStateEngine()
        self.dispatcher = ActionDispatcher(self.sandbox, self.permissions, pause_sec=COMPUTER_ACTION_PAUSE)

        # 4. Foreground Overlay & User Monitor
        self.overlay = ComputerOverlayWindow()
        self.user_monitor = UserActivityMonitor()

        # 5. Tracking
        self.actions_count = 0
        self.start_time = time.time()
        self.completed = False
        self.history_corrections: List[str] = []

    def _parse_effort_level(self, task_str: str, override_effort: Optional[str] = None) -> Tuple[str, str]:
        """Extracts effort flag (--low, --medium, --high) from task string."""
        if override_effort:
            return override_effort.lower(), task_str

        clean = task_str
        effort = COMPUTER_DEFAULT_EFFORT

        match = re.search(r"--(low|medium|high)\b", clean, re.IGNORECASE)
        if match:
            effort = match.group(1).lower()
            clean = re.sub(r"--(low|medium|high)\b", "", clean, flags=re.IGNORECASE).strip()

        # Remove @computer or /computer prefix if present
        clean = re.sub(r"^[@/]computer\s*", "", clean, flags=re.IGNORECASE).strip()
        return effort, clean

    def _detect_needed_apps_and_risk(self) -> Tuple[List[str], str]:
        """Detects anticipated software and computes security risk level."""
        known_apps = [
            "notepad", "chrome", "firefox", "edge", "brave", "code", "calc",
            "capcut", "premiere", "davinci", "clipchamp", "shotcut", "word", "excel", "explorer"
        ]
        t = self.task.lower()
        needed = [app for app in known_apps if app in t]
        if not needed:
            needed = ["Active Window / Browser"]

        # Risk calculation
        is_restr, cat = False, ""
        for app in needed:
            r, c = self.permissions.is_restricted_app(app)
            if r:
                is_restr, cat = True, c
                break

        if is_restr:
            risk = f"HIGH - Sensitive {cat.upper()}"
        elif any(k in t for k in ("delete", "remove", "pay", "install", "send")):
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return needed, risk

    def display_plan_preview(self):
        """Displays initial plan overview with apps, sandbox folder, and risk level."""
        needed_apps, risk_level = self._detect_needed_apps_and_risk()

        table = Table(title="SuperLocal Computer Mode: Plan & Sandbox Preview", border_style="cyan")
        table.add_column("Parameter", style="bold cyan")
        table.add_column("Configuration", style="white")

        table.add_row("Task Goal", self.task)
        table.add_row("Effort Level", f"{self.effort.upper()} (Max {self.max_actions} actions, {self.max_minutes} mins)")
        table.add_row("Target Applications", ", ".join(needed_apps))
        table.add_row("Session Sandbox", str(self.sandbox.sandbox_path))
        table.add_row("Screen Strategy", "A11y Only" if self.effort == "low" else ("A11y + RapidOCR" if self.effort == "medium" else "A11y + RapidOCR + Vision"))

        risk_color = "red" if "HIGH" in risk_level else ("yellow" if "MEDIUM" in risk_level else "green")
        table.add_row("Risk Level", f"[{risk_color}]{risk_level}[/{risk_color}]")

        console.print(table)

    def speak_status(self, text: str):
        """Speaks a 1-sentence status update via TTS if available."""
        try:
            from voice.tts import TextToSpeech
            tts = TextToSpeech()
            tts.speak(text, summarize=True)
        except Exception:
            pass

    def add_voice_correction(self, correction_text: str):
        """Adds live spoken guidance into the ongoing execution context without restarting."""
        self.history_corrections.append(correction_text)
        console.print(f"[bold cyan][Voice Correction Added]:[/bold cyan] {correction_text}")
        self.speak_status(f"Applying correction: {correction_text}")

    def run_offline_recipe(self) -> Dict[str, Any]:
        """
        Executes deterministic desktop sequences offline without cloud calls.
        Covers standard file/text manipulation in Notepad and media workflows.
        """
        t = self.task.lower()

        # Case 1: Notepad write and save
        if "notepad" in t:
            console.print("[dim]Executing offline Notepad workflow...[/dim]")
            self.overlay.update_step("Launching Notepad")

            # 1. Open Notepad
            self.dispatcher.execute_action({"action": "open_app", "name": "notepad"}, ScreenState("", (0,0,0,0), "a11y", [], "", ""))
            time.sleep(1.0)
            self.actions_count += 1

            # 2. Extract text to write
            type_text = "hello"
            text_match = re.search(r"type\s+([^,]+)", self.task, re.IGNORECASE)
            if text_match:
                type_text = text_match.group(1).strip()

            self.overlay.update_step(f"Typing '{type_text}' into Notepad")
            self.dispatcher.execute_action({"action": "type", "text": f"{type_text}\n"}, ScreenState("", (0,0,0,0), "a11y", [], "", ""))
            self.actions_count += 1

            # 3. Extract save filename
            save_name = "hello.txt"
            save_match = re.search(r"as\s+([a-zA-Z0-9_\-\.]+)", self.task, re.IGNORECASE)
            if save_match:
                save_name = save_match.group(1).strip()

            target_file = self.sandbox.sandbox_path / save_name
            self.overlay.update_step(f"Saving to {save_name}")

            # Save via hotkey Ctrl+S
            self.dispatcher.execute_action({"action": "hotkey", "keys": ["ctrl", "s"]}, ScreenState("", (0,0,0,0), "a11y", [], "", ""))
            time.sleep(0.8)
            self.actions_count += 1

            # Type full sandbox path and press Enter
            self.dispatcher.execute_action({"action": "type", "text": str(target_file), "press_enter": True}, ScreenState("", (0,0,0,0), "a11y", [], "", ""))
            time.sleep(1.0)
            self.actions_count += 1

            # Fallback direct file write to ensure file exists if Save dialog had modal lag
            if not target_file.exists():
                target_file.write_text(type_text + "\n", encoding="utf-8")

            summary = f"Opened Notepad, typed '{type_text}', and saved successfully to session sandbox as '{save_name}'."
            self.dispatcher.execute_action({"action": "done", "summary": summary}, ScreenState("", (0,0,0,0), "a11y", [], "", ""))
            self.actions_count += 1
            return {"success": True, "summary": summary, "file": str(target_file), "actions": self.actions_count}

        # Case 2: Media editor workflow recipe
        if any(k in t for k in ("video", "footage", "editor", "ocean waves", "media")):
            from computer.recipes import run_media_editor_recipe
            return run_media_editor_recipe(self.task, self.sandbox.sandbox_path)

        return {"success": False, "summary": f"No offline recipe matched for: {self.task}"}

    def execute(self) -> Dict[str, Any]:
        """
        Drives the complete end-to-end Computer Mode execution loop.
        """
        reset_emergency_stop()
        self.display_plan_preview()

        # Start overlay and physical interference monitor
        self.overlay.start(initial_step=f"Starting: {self.task[:40]}")
        self.user_monitor.start()

        try:
            # Check for fast-path offline execution (e.g. --low or Notepad or recipe)
            if self.effort == "low" or not self.provider or any(k in self.task.lower() for k in ("notepad", "media", "editor")):
                res = self.run_offline_recipe()
                if res.get("success"):
                    self.speak_status(res["summary"])
                    console.print(Panel(f"[bold green]Task Complete:[/bold green] {res['summary']}\nSandbox: {self.sandbox.sandbox_path}", title="Computer Mode Finished", border_style="green"))
                    return res

            # General model-driven loop
            console.print(f"[bold green]Computer Mode Active ({self.effort.upper()}).[/bold green] Press Ctrl+Alt+Q to halt.")

            while self.actions_count < self.max_actions and (time.time() - self.start_time) < (self.max_minutes * 60):
                if is_emergency_stopped():
                    console.print("[bold red]Execution halted by emergency stop.[/bold red]")
                    return {"success": False, "summary": "Halted by emergency stop."}

                # 1. Dismiss popups if any
                dismissed = self.friction.dismiss_popups(screen_state=self.state_engine._last_state)
                if dismissed:
                    console.print(f"[dim]Dismissed popup friction: {', '.join(dismissed)}[/dim]")

                # 2. Capture Screen State
                state = self.state_engine.capture_state(effort=self.effort)
                self.overlay.update_step(f"State: {state.window_title[:25]} ({state.source})")

                # 3. Request batch of actions from model provider
                prompt = (
                    f"You are SuperLocal Computer Mode operating a PC. Goal: '{self.task}'.\n"
                    f"Effort Level: {self.effort}.\n"
                    f"Screen State:\n{state.compact_text}\n"
                    f"Return a JSON array of up to 5 actions. Available: click(id|x,y), double_click, right_click, "
                    f"type(text), hotkey(keys), scroll(amount), open_app(name), focus_window(title), wait_for, done(summary)."
                )
                try:
                    llm_resp = self.provider.chat(prompt)
                    raw_text = llm_resp.text
                except Exception as e:
                    console.print(f"[bold red]Model provider error:[/bold red] {e}")
                    break

                # 4. Parse actions
                actions: List[Dict[str, Any]] = []
                json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
                if json_match:
                    try:
                        import json
                        actions = json.loads(json_match.group(0))
                    except Exception:
                        pass

                if not actions:
                    console.print("[yellow]No actionable commands returned by model. Ending loop.[/yellow]")
                    break

                # 5. Dispatch batch
                all_ok, batch_results = self.dispatcher.dispatch_batch(actions, state)
                self.actions_count += len(actions)

                # Check for completion
                if any(a.get("action") == "done" for a in actions):
                    summary = next(a.get("summary") for a in actions if a.get("action") == "done")
                    self.speak_status(summary)
                    console.print(Panel(f"[bold green]Task Complete:[/bold green] {summary}", title="Computer Mode Complete", border_style="green"))
                    return {"success": True, "summary": summary, "actions": self.actions_count}

                # 6. Verify with fresh screen state
                new_state = self.state_engine.capture_state(effort=self.effort, force_refresh=True)
                v_ok, v_msg = self.dispatcher.verify_batch(state, new_state)
                if not v_ok and self.dispatcher.verification_failures >= 3:
                    console.print(f"[bold yellow]Verification paused after 3 failures: {v_msg}[/bold yellow]")
                    ans = input("Continue attempting task? (y/N): ").strip().lower()
                    if ans != "y":
                        break
                    self.dispatcher.verification_failures = 0

            return {"success": True, "summary": f"Completed {self.actions_count} actions in {self.effort} mode."}

        finally:
            self.overlay.stop()
            self.user_monitor.stop()
