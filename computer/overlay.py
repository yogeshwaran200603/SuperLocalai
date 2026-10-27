"""
SuperLocal Computer Mode: Always-On-Top Overlay & User Activity Monitor
- Displays an always-on-top overlay: "SuperLocal is controlling this PC - press Ctrl+Alt+Q to stop"
- Updates with the current active step in real-time
- Monitors for human mouse and keyboard movements for > 2 seconds:
  automatically pauses and asks whether to resume or hand control back
- Global Hotkeys:
  - Ctrl+Alt+Q: Instant Emergency Stop
  - Ctrl+Alt+P: Pause / Resume Toggle
  - Ctrl+Alt+H: Hand control back cleanly
"""

import sys
import time
import threading
from typing import Optional, Callable
import pyautogui

try:
    import keyboard
except ImportError:
    keyboard = None

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from safety import is_emergency_stopped, trigger_emergency_stop

console = Console()


class ComputerOverlayWindow:
    """
    Lightweight, always-on-top banner window running in a dedicated background thread.
    """

    def __init__(self):
        self.root = None
        self.label = None
        self.thread: Optional[threading.Thread] = None
        self.current_text = "SuperLocal is controlling this PC - press Ctrl+Alt+Q to stop"
        self._running = False

    def start(self, initial_step: str = "Initializing..."):
        self.current_text = f"SuperLocal is controlling this PC - press Ctrl+Alt+Q to stop | {initial_step}"
        self._running = True
        self.thread = threading.Thread(target=self._run_gui, daemon=True, name="ComputerOverlayWindow")
        self.thread.start()

    def update_step(self, step_text: str):
        self.current_text = f"SuperLocal is controlling this PC - press Ctrl+Alt+Q to stop | {step_text}"
        if self.root and self.label:
            try:
                self.root.after(0, lambda: self.label.config(text=self.current_text))
            except Exception:
                pass

    def stop(self):
        self._running = False
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass

    def _run_gui(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
            self.root.title("SuperLocal Control Overlay")
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.90)
            self.root.overrideredirect(True)

            # Position at top center
            screen_w = self.root.winfo_screenwidth()
            w, h = 680, 36
            x = (screen_w - w) // 2
            y = 8
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.configure(bg="#0f172a")

            self.label = tk.Label(
                self.root,
                text=self.current_text,
                font=("Segoe UI", 10, "bold"),
                fg="#38bdf8",
                bg="#0f172a",
                padx=12,
                pady=6,
            )
            self.label.pack(fill=tk.BOTH, expand=True)

            while self._running:
                self.root.update()
                time.sleep(0.05)
        except Exception:
            # Fallback if headless / tkinter unavailable
            pass


class UserActivityMonitor:
    """
    Detects continuous human user input (mouse or keyboard) for > 2 seconds
    and triggers an automatic pause with hand-back options.
    """

    def __init__(self, on_user_pause: Optional[Callable[[], None]] = None):
        self.running = False
        self.agent_active = False
        self.paused = False
        self.on_user_pause = on_user_pause
        self.thread: Optional[threading.Thread] = None
        self.last_mouse_pos = None
        self.input_start_time: Optional[float] = None
        self._registered_hotkeys = False

    def start(self):
        self.running = True
        self.paused = False
        self.input_start_time = None
        try:
            self.last_mouse_pos = pyautogui.position()
        except Exception:
            self.last_mouse_pos = (0, 0)

        self._setup_hotkeys()
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True, name="UserActivityMonitor")
        self.thread.start()

    def stop(self):
        self.running = False

    def _setup_hotkeys(self):
        """Registers Ctrl+Alt+Q (Stop), Ctrl+Alt+P (Pause/Resume), Ctrl+Alt+H (Hand Back)."""
        if not keyboard or self._registered_hotkeys:
            return

        try:
            # Emergency Stop
            keyboard.add_hotkey("ctrl+alt+q", lambda: trigger_emergency_stop("Triggered Ctrl+Alt+Q"))

            # Pause / Resume
            def toggle_pause():
                self.paused = not self.paused
                state_str = "Paused" if self.paused else "Resumed"
                console.print(f"\n[bold yellow]Ctrl+Alt+P pressed: Computer Mode {state_str}.[/bold yellow]")

            keyboard.add_hotkey("ctrl+alt+p", toggle_pause)

            # Hand control back
            def hand_back():
                self.paused = True
                trigger_emergency_stop("User handed control back via Ctrl+Alt+H")
                console.print("\n[bold green]Ctrl+Alt+H pressed: Handed control back to human user.[/bold green]")

            keyboard.add_hotkey("ctrl+alt+h", hand_back)

            self._registered_hotkeys = True
        except Exception:
            pass

    def _monitor_loop(self):
        while self.running:
            time.sleep(0.1)

            if self.agent_active or self.paused or is_emergency_stopped():
                try:
                    self.last_mouse_pos = pyautogui.position()
                except Exception:
                    pass
                self.input_start_time = None
                continue

            try:
                curr_pos = pyautogui.position()
            except Exception:
                continue

            if self.last_mouse_pos is None:
                self.last_mouse_pos = curr_pos
                continue

            dx = curr_pos[0] - self.last_mouse_pos[0]
            dy = curr_pos[1] - self.last_mouse_pos[1]
            dist = (dx**2 + dy**2)**0.5

            if dist > 25:  # Significant physical displacement
                now = time.time()
                if self.input_start_time is None:
                    self.input_start_time = now
                elif (now - self.input_start_time) >= 2.0:
                    # User input sustained for full 2.0 seconds!
                    self.paused = True
                    console.print("\n[bold yellow]User physical input detected for >2s. Computer Mode paused.[/bold yellow]")
                    if self.on_user_pause:
                        self.on_user_pause()
                    else:
                        ans = Confirm.ask("[bold yellow]Resume Computer Mode execution? (y/n)[/bold yellow]", default=True)
                        if ans:
                            self.paused = False
                            try:
                                self.last_mouse_pos = pyautogui.position()
                            except Exception:
                                pass
                            self.input_start_time = None
                        else:
                            trigger_emergency_stop("Stopped by user after physical interference pause")
                            break
            else:
                self.input_start_time = None

            self.last_mouse_pos = curr_pos
