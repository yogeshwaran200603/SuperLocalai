"""
SuperLocal Poki Player: Overlay & User Interruption Monitor
- Real-time status line: "[Poki] <game> | run 3 | score 1240 | 24 FPS"
- Monitors for human mouse and keyboard movements:
  automatically pauses if user physically moves mouse or types for > 2 seconds
- Hotkeys:
  - Ctrl+Alt+Q: Emergency Stop
  - Ctrl+Alt+P: Pause / Resume Toggle
"""

import time
import threading
from typing import Optional, Callable
import pyautogui

try:
    import keyboard
except ImportError:
    keyboard = None

from rich.console import Console
from rich.live import Live
from rich.text import Text

from safety import is_emergency_stopped, trigger_emergency_stop

console = Console()


class PokiOverlay:
    """
    Manages terminal status line and physical input pause detection.
    """

    def __init__(self, game_name: str):
        self.game_name = game_name
        self.run_number = 1
        self.score = 0.0
        self.fps = 24.0
        self.is_paused = False
        self.is_running = False

        self._hotkeys_registered = False
        self._last_mouse_pos = None
        self._user_input_start = None
        self._monitor_thread = None

    def start(self):
        """Starts background monitor and hotkeys."""
        self.is_running = True
        self.is_paused = False
        self._user_input_start = None
        try:
            self._last_mouse_pos = pyautogui.position()
        except Exception:
            self._last_mouse_pos = (0, 0)

        self._register_hotkeys()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="PokiUserMonitor"
        )
        self._monitor_thread.start()

    def stop(self):
        """Stops monitor."""
        self.is_running = False

    def update_status(self, run: int, score: float, fps: float):
        self.run_number = run
        self.score = score
        self.fps = fps
        status_line = f"[Poki] {self.game_name} | run {self.run_number} | score {int(self.score)} | {self.fps:.0f} FPS"
        console.print(f"[bold cyan]{status_line}[/bold cyan]", end="\r")

    def _register_hotkeys(self):
        if not keyboard or self._hotkeys_registered:
            return

        try:
            # Stop: Ctrl+Alt+Q
            keyboard.add_hotkey("ctrl+alt+q", lambda: trigger_emergency_stop("Poki stopped by Ctrl+Alt+Q"))

            # Pause/Resume: Ctrl+Alt+P
            def toggle_pause():
                self.is_paused = not self.is_paused
                state_str = "PAUSED" if self.is_paused else "RESUMED"
                console.print(f"\n[bold yellow][Poki] Ctrl+Alt+P: Game {state_str}[/bold yellow]")

            keyboard.add_hotkey("ctrl+alt+p", toggle_pause)
            self._hotkeys_registered = True
        except Exception:
            pass

    def _monitor_loop(self):
        """Monitors for continuous human mouse movement for > 2 seconds."""
        while self.is_running:
            time.sleep(0.1)

            if is_emergency_stopped() or self.is_paused:
                try:
                    self._last_mouse_pos = pyautogui.position()
                except Exception:
                    pass
                self._user_input_start = None
                continue

            try:
                curr_pos = pyautogui.position()
            except Exception:
                continue

            if self._last_mouse_pos is None:
                self._last_mouse_pos = curr_pos
                continue

            dx = curr_pos[0] - self._last_mouse_pos[0]
            dy = curr_pos[1] - self._last_mouse_pos[1]
            dist = (dx**2 + dy**2)**0.5

            if dist > 25:  # User physically displaced mouse
                now = time.time()
                if self._user_input_start is None:
                    self._user_input_start = now
                elif (now - self._user_input_start) >= 2.0:
                    # User input sustained for 2 full seconds
                    self.is_paused = True
                    console.print("\n[bold yellow][Poki] User physical input detected for >2s. Game paused.[/bold yellow]")
                    console.print("[dim]Press Ctrl+Alt+P to resume, or Ctrl+Alt+Q to stop.[/dim]")
            else:
                self._user_input_start = None

            self._last_mouse_pos = curr_pos
