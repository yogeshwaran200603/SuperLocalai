"""
SuperLocal Computer Mode: Action Dispatcher & Verification Engine
Executes batched computer actions (up to 5 actions per turn):
- Actions: click, double_click, right_click, drag, type, hotkey, scroll,
  focus_window, open_app, wait_for, screenshot_if_needed, done
- 0.3s pause between actions
- Pre-execution validation against sandbox and app allowlist
- Cheap polling for wait_for without model calls
- Verification after each batch (window focus, state hash changes) with up to 3 retries
- Action logging with credential masking into logs/actions.log
"""

import os
import sys
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

import pyautogui
import pygetwindow as gw
from rich.console import Console

from config import COMPUTER_ACTION_PAUSE, LOGS_DIR
from safety import is_emergency_stopped, log_action
from computer.state_engine import ScreenState, UIElement
from computer.permissions import ComputerPermissionManager, ComputerSessionSandbox

console = Console()


class ActionDispatcher:
    """
    Validates and executes actions on the PC with retry loops and polling.
    """

    def __init__(
        self,
        sandbox: ComputerSessionSandbox,
        permissions: ComputerPermissionManager,
        pause_sec: float = COMPUTER_ACTION_PAUSE,
    ):
        self.sandbox = sandbox
        self.permissions = permissions
        self.pause_sec = pause_sec
        self.actions_log_path = LOGS_DIR / "actions.log"
        self.verification_failures = 0

    def _log_dispatched_action(self, action_name: str, details: Dict[str, Any], state: ScreenState):
        """Logs action to logs/actions.log with masked sensitive values."""
        clean_details = dict(details)
        if "text" in clean_details:
            t = str(clean_details["text"])
            if any(k in t.lower() for k in ("password", "secret", "token", "key")):
                clean_details["text"] = "********"

        log_action(f"computer_{action_name}", clean_details, status="executed", details=f"win='{state.window_title}'")

    def resolve_target_coordinates(
        self, action: Dict[str, Any], state: ScreenState
    ) -> Optional[Tuple[int, int]]:
        """Resolves (x, y) from element id or raw coordinates with scale compensation."""
        # 1. By ID
        if "id" in action:
            el_id = int(action["id"])
            el = state.find_element_by_id(el_id)
            if el:
                return el.center

        # 2. By text match
        if "text" in action and "id" not in action and "x" not in action:
            el = state.find_element_by_text(str(action["text"]))
            if el:
                return el.center

        # 3. By raw x, y
        if "x" in action and "y" in action:
            raw_x = int(action["x"])
            raw_y = int(action["y"])
            # Map back if vision scaled
            if state.scale_factor != 1.0 and state.scale_factor > 0:
                win_x, win_y, _, _ = state.window_bounds
                mapped_x = int(raw_x / state.scale_factor) + win_x
                mapped_y = int(raw_y / state.scale_factor) + win_y
                return (mapped_x, mapped_y)
            return (raw_x, raw_y)

        return None

    def execute_action(
        self, action: Dict[str, Any], state: ScreenState
    ) -> Tuple[bool, str]:
        """Validates and executes a single action."""
        if is_emergency_stopped():
            return False, "Halted by emergency stop."

        act_type = action.get("action", "").lower().strip()

        # 1. open_app
        if act_type == "open_app":
            app_name = action.get("name", "")
            if not app_name:
                return False, "open_app requires 'name' parameter."

            allowed, perm_msg = self.permissions.request_app_control(app_name)
            if not allowed:
                return False, perm_msg

            from tools.shell import open_app
            res = open_app(app_name)
            self._log_dispatched_action("open_app", action, state)
            time.sleep(1.0)
            return res.get("success", True), f"Opened app '{app_name}'"

        # 2. focus_window
        elif act_type == "focus_window":
            title = action.get("title", "")
            all_wins = gw.getWindowsWithTitle(title)
            if all_wins:
                try:
                    all_wins[0].activate()
                    time.sleep(0.5)
                    self._log_dispatched_action("focus_window", action, state)
                    return True, f"Focused window matching '{title}'"
                except Exception as e:
                    return False, f"Could not focus window: {e}"
            return False, f"Window matching '{title}' not found."

        # 3. click
        elif act_type == "click":
            coords = self.resolve_target_coordinates(action, state)
            if not coords:
                return False, f"Target element or coordinate not found for click: {action}"
            pyautogui.click(coords[0], coords[1])
            self._log_dispatched_action("click", {"coords": coords}, state)
            time.sleep(self.pause_sec)
            return True, f"Clicked at ({coords[0]}, {coords[1]})"

        # 4. double_click
        elif act_type == "double_click":
            coords = self.resolve_target_coordinates(action, state)
            if not coords:
                return False, f"Target element or coordinate not found for double_click: {action}"
            pyautogui.doubleClick(coords[0], coords[1])
            self._log_dispatched_action("double_click", {"coords": coords}, state)
            time.sleep(self.pause_sec)
            return True, f"Double-clicked at ({coords[0]}, {coords[1]})"

        # 5. right_click
        elif act_type == "right_click":
            coords = self.resolve_target_coordinates(action, state)
            if not coords:
                return False, f"Target element or coordinate not found for right_click: {action}"
            pyautogui.rightClick(coords[0], coords[1])
            self._log_dispatched_action("right_click", {"coords": coords}, state)
            time.sleep(self.pause_sec)
            return True, f"Right-clicked at ({coords[0]}, {coords[1]})"

        # 6. type
        elif act_type in ("type", "type_text"):
            text = action.get("text", "")
            press_enter = action.get("press_enter", False)
            pyautogui.write(text, interval=0.02)
            if press_enter:
                pyautogui.press("enter")
            self._log_dispatched_action("type", {"text": text, "press_enter": press_enter}, state)
            time.sleep(self.pause_sec)
            return True, f"Typed text of length {len(text)}"

        # 7. hotkey
        elif act_type == "hotkey":
            keys = action.get("keys", [])
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split("+")]
            if keys:
                pyautogui.hotkey(*keys)
                self._log_dispatched_action("hotkey", {"keys": keys}, state)
                time.sleep(self.pause_sec)
                return True, f"Pressed hotkey: {'+'.join(keys)}"
            return False, "hotkey requires list of keys."

        # 8. scroll
        elif act_type == "scroll":
            amount = int(action.get("amount", -300))
            pyautogui.scroll(amount)
            self._log_dispatched_action("scroll", {"amount": amount}, state)
            time.sleep(self.pause_sec)
            return True, f"Scrolled {amount}"

        # 9. drag
        elif act_type == "drag":
            from_pt = action.get("from")
            to_pt = action.get("to")
            if from_pt and to_pt:
                pyautogui.moveTo(from_pt[0], from_pt[1])
                pyautogui.dragTo(to_pt[0], to_pt[1], duration=0.6, button="left")
                self._log_dispatched_action("drag", action, state)
                time.sleep(self.pause_sec)
                return True, f"Dragged from {from_pt} to {to_pt}"
            return False, "drag requires 'from' and 'to' coordinate tuples."

        # 10. wait_for (Long running tasks: cheap polling without model calls)
        elif act_type == "wait_for":
            seconds = action.get("seconds")
            target_text = action.get("text")
            file_pattern = action.get("file")
            max_wait = int(action.get("timeout", 60))

            if seconds:
                time.sleep(min(float(seconds), 60.0))
                return True, f"Waited {seconds} seconds"

            # Cheap polling loop every 5 seconds
            start_poll = time.time()
            console.print(f"[dim]Polling for completion condition (max {max_wait}s)...[/dim]")

            while (time.time() - start_poll) < max_wait:
                if is_emergency_stopped():
                    return False, "Aborted during wait_for polling."

                # Check file condition
                if file_pattern:
                    matches = list(self.sandbox.sandbox_path.glob(file_pattern))
                    if matches and matches[0].stat().st_size > 0:
                        return True, f"Found expected file: {matches[0].name}"

                # Check text condition via window titles
                if target_text:
                    q = target_text.lower()
                    active_title, _ = gw.getActiveWindow().title if gw.getActiveWindow() else ("", None)
                    if q in (active_title or "").lower():
                        return True, f"Detected text in window title: '{active_title}'"

                time.sleep(5.0)

            return True, f"wait_for finished or reached timeout ({max_wait}s)"

        # 11. done
        elif act_type == "done":
            summary = action.get("summary", "Task completed.")
            self._log_dispatched_action("done", {"summary": summary}, state)
            return True, f"DONE: {summary}"

        return False, f"Unknown action type: {act_type}"

    def dispatch_batch(
        self, actions: List[Dict[str, Any]], state: ScreenState
    ) -> Tuple[bool, List[str]]:
        """
        Executes a batch of up to 5 actions with pauses.
        Returns (all_success: bool, results: List[str]).
        """
        results: List[str] = []
        batch = actions[:5]

        for idx, act in enumerate(batch, 1):
            if is_emergency_stopped():
                results.append("Batch aborted: Emergency stop active.")
                return False, results

            console.print(f"[dim]  Executing action {idx}/{len(batch)}: {act.get('action')}[/dim]")
            success, msg = self.execute_action(act, state)
            results.append(msg)
            if not success:
                return False, results

        return True, results

    def verify_batch(
        self, prev_state: ScreenState, new_state: ScreenState, expected_app: str = ""
    ) -> Tuple[bool, str]:
        """
        Verifies batch outcome:
        - Detects whether screen state hash changed
        - Verifies expected application window focus
        Returns (passed, message).
        """
        # If expected window name provided, verify title
        if expected_app:
            norm_app = expected_app.lower()
            if norm_app not in new_state.window_title.lower():
                self.verification_failures += 1
                return False, f"Verification failed: active window '{new_state.window_title}' does not match expected '{expected_app}'"

        # Check if screen state changed
        if prev_state.state_hash == new_state.state_hash:
            self.verification_failures += 1
            return False, f"Verification warning: screen state remained unchanged after batch execution ({self.verification_failures}/3 failures)"

        self.verification_failures = 0
        return True, "Batch verification passed."
