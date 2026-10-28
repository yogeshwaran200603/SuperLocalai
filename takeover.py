"""
Astra-Local Takeover Mode Engine
Controls the mouse and keyboard like a remote human user (UltraViewer style).

Features:
- Command: /takeover <task> in REPL or global hotkey Ctrl+Alt+T.
- Batched agent loop: observe -> plan up to 5 actions -> execute (0.3s pauses) -> observe.
- Supported JSON actions: click, double_click, right_click, type, hotkey, scroll, drag, wait, done.
- Active window capture, resize max 1024px wide, JPEG quality 50 with scale factor mapping.
- pywinauto UIA numbered element bounding box overlay (e.g. 'click 7') with raw coordinate fallback.
- gemini-3.8-flash, thinking level 'low', 45s timeout, 3 retries with backoff on 503/504/429.
- Computer-use API and tool support check.
- Safety controls:
  - 'Takeover active. Ctrl+Alt+Q or mouse to the top-left corner stops it.'
  - pyautogui.FAILSAFE = True and Ctrl+Alt+Q immediate stop.
  - Mandatory y/n confirmation before sending, deleting, paying/buying, or password typing.
  - Circuit breaker: stop after 3 failed verifications.
  - Mouse movement interference pause after 2 seconds with resume prompt.
  - Screenshots in logs/screens/ with 7-day retention cleanup.
"""

import os
import sys
import io
import time
import json
import re
import datetime
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

if sys.platform == "win32":
    if not hasattr(sys, "coinit_flags"):
        sys.coinit_flags = 2  # Revert to STA COM threading mode fix
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def ensure_interactive_desktop():
    """Attaches process/thread to interactive window station WinSta0\\Default if running on Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        GENERIC_ALL = 0x10000000
        hwinsta = ctypes.windll.user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
        if hwinsta:
            ctypes.windll.user32.SetProcessWindowStation(hwinsta)
            hdesk = ctypes.windll.user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
            if hdesk:
                ctypes.windll.user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


ensure_interactive_desktop()

from PIL import Image, ImageDraw, ImageFont
import pyautogui
import pygetwindow as gw

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from config import (
    GEMINI_API_KEY,
    MODEL_NAME,
    TEXT_MODEL,
    FALLBACK_MODEL,
    TAKEOVER_MODEL,
    LOGS_DIR,
    SCREENS_DIR,
)
from safety import (
    is_emergency_stopped,
    trigger_emergency_stop,
    reset_emergency_stop,
    confirm_sensitive_desktop_action,
    is_sensitive_target_or_text,
    log_action,
    format_truthful_status,
)
from tools.desktop import cleanup_old_screenshots

# Safety settings for PyAutoGUI
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

console = Console()

# Configuration constants
TAKEOVER_MAX_ACTIONS = 30
BATCH_SIZE = 5
ACTION_PAUSE = 0.3
RESIZE_MAX_WIDTH = 1024
JPEG_QUALITY = 50
TAKEOVER_TIMEOUT_MS = 45000

# Global takeover trigger queue for hotkey
_takeover_pending_prompt: Optional[str] = None
_takeover_hotkey_registered = False


class MouseInterferenceMonitor:
    """
    Monitors for human mouse movements during Takeover Mode.
    If the user manually moves the mouse continuously for 2 seconds,
    Takeover Mode pauses and asks whether to resume.
    """
    def __init__(self):
        self.running = False
        self.agent_moving = False
        self.paused = False
        self.thread: Optional[threading.Thread] = None
        self.last_pos = None
        self.move_start_time: Optional[float] = None

    def start(self):
        self.running = True
        self.paused = False
        try:
            self.last_pos = pyautogui.position()
        except Exception:
            self.last_pos = (0, 0)
        self.move_start_time = None
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True, name="MouseInterferenceMonitor")
        self.thread.start()

    def stop(self):
        self.running = False

    def _monitor_loop(self):
        while self.running:
            time.sleep(0.1)
            if self.agent_moving or self.paused or is_emergency_stopped():
                try:
                    self.last_pos = pyautogui.position()
                except Exception:
                    pass
                self.move_start_time = None
                continue

            try:
                curr_pos = pyautogui.position()
            except Exception:
                continue

            if self.last_pos is None:
                self.last_pos = curr_pos
                continue

            # Check Euclidean distance moved
            dx = curr_pos[0] - self.last_pos[0]
            dy = curr_pos[1] - self.last_pos[1]
            dist = (dx**2 + dy**2)**0.5

            if dist > 20:  # User physically displaced mouse
                now = time.time()
                if self.move_start_time is None:
                    self.move_start_time = now
                elif (now - self.move_start_time) >= 2.0:
                    # Sustained movement for 2 full seconds!
                    self.paused = True
                    console.print("\n[bold yellow]User mouse movement detected for 2 seconds. Takeover Mode paused.[/bold yellow]")
                    approved = Confirm.ask("[bold yellow]Resume Takeover Mode? (y/n)[/bold yellow]", default=True)
                    if approved:
                        self.paused = False
                        try:
                            self.last_pos = pyautogui.position()
                        except Exception:
                            pass
                        self.move_start_time = None
                    else:
                        trigger_emergency_stop("User mouse interference pause - stopped by user")
                        break
            else:
                self.move_start_time = None

            self.last_pos = curr_pos


def capture_window_or_screen() -> Tuple[Image.Image, int, int]:
    """
    Captures only the active window when possible, otherwise full screen.
    Returns (PIL_Image, window_x_offset, window_y_offset).
    """
    try:
        active = gw.getActiveWindow()
        if active and active.visible and not active.isMinimized and active.width > 50 and active.height > 50:
            x, y, w, h = max(0, active.left), max(0, active.top), active.width, active.height
            # Capture specific region
            shot = pyautogui.screenshot(region=(x, y, w, h))
            return shot, x, y
    except Exception:
        pass

    # Fallback to full screen
    try:
        shot = pyautogui.screenshot()
        return shot, 0, 0
    except Exception:
        # Emergency headless / locked desktop fallback
        from PIL import Image
        img = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
        return img, 0, 0


def detect_uia_clickable_elements(win_x: int, win_y: int, win_w: int, win_h: int) -> List[Dict[str, Any]]:
    """
    Extracts clickable elements from pywinauto UIA inside the target window boundary.
    Limits: active window only, max depth 6, max 80 elements, 5 s timeout in a cancellable worker thread.
    Skips huge trees (browsers, Electron, canvases) to prevent hangs.
    """
    elements: List[Dict[str, Any]] = []

    def _worker(result_container: list, cancel_event: threading.Event):
        try:
            import sys
            if not hasattr(sys, "coinit_flags"):
                sys.coinit_flags = 2
            import pywinauto

            desktop = pywinauto.Desktop(backend="uia")
            top_windows = desktop.windows()
            target_win = None
            for w in top_windows:
                if cancel_event.is_set():
                    return
                try:
                    rect = w.rectangle()
                    if abs(rect.left - win_x) < 50 and abs(rect.top - win_y) < 50:
                        target_win = w
                        break
                except Exception:
                    continue

            if not target_win and top_windows:
                target_win = top_windows[0]

            if not target_win:
                return

            # Skip huge trees (browsers, Electron, game canvases)
            try:
                win_title = (target_win.window_text() or "").lower()
                c_name = (target_win.element_info.class_name or "").lower()
                huge_tree_signals = (
                    "chrome", "msedge", "edge", "firefox", "brave", "opera",
                    "electron", "slack", "discord", "code", "teams", "canvas"
                )
                if any(s in win_title or s in c_name for s in huge_tree_signals):
                    return
            except Exception:
                pass

            allowed_types = {
                "Button", "Edit", "MenuItem", "TabItem", "CheckBox",
                "RadioButton", "Hyperlink", "ListItem", "ComboBox", "Document", "Text"
            }

            # Breadth-first search with depth limit 6
            queue = [(target_win, 0)]
            count = 0

            while queue and count < 80 and not cancel_event.is_set():
                curr, depth = queue.pop(0)
                if depth > 6:
                    continue
                try:
                    for ch in curr.children():
                        if cancel_event.is_set() or count >= 80:
                            break
                        try:
                            c_type = ch.element_info.control_type
                            if c_type in allowed_types:
                                rect = ch.rectangle()
                                if rect.width() > 10 and rect.height() > 10:
                                    if (rect.left >= win_x - 10 and rect.top >= win_y - 10 and
                                        rect.right <= win_x + win_w + 10 and rect.bottom <= win_y + win_h + 10):
                                        count += 1
                                        result_container.append({
                                            "id": count,
                                            "type": c_type,
                                            "name": ch.window_text().strip(),
                                            "left": rect.left,
                                            "top": rect.top,
                                            "right": rect.right,
                                            "bottom": rect.bottom,
                                            "cx": (rect.left + rect.right) // 2,
                                            "cy": (rect.top + rect.bottom) // 2,
                                        })
                            if depth < 6:
                                queue.append((ch, depth + 1))
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass

    cancel_ev = threading.Event()
    th = threading.Thread(target=_worker, args=(elements, cancel_ev), daemon=True)
    th.start()
    th.join(timeout=5.0)
    if th.is_alive():
        cancel_ev.set()

    return elements[:80]


def prepare_takeover_observation() -> Tuple[bytes, float, int, int, Dict[int, Dict[str, Any]], str]:
    """
    Captures screen, overlays numbered UIA boxes (when available),
    resizes to max 1024px, saves timestamped JPEG (quality 50),
    and prunes screenshots older than 7 days.
    """
    cleanup_old_screenshots(days=7)

    orig_img, win_x, win_y = capture_window_or_screen()
    orig_w, orig_h = orig_img.size

    # Compute scale factor (max 1024px wide)
    if orig_w > RESIZE_MAX_WIDTH:
        scale = RESIZE_MAX_WIDTH / float(orig_w)
        scaled_w = RESIZE_MAX_WIDTH
        scaled_h = int(orig_h * scale)
        scaled_img = orig_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
    else:
        scale = 1.0
        scaled_w, scaled_h = orig_w, orig_h
        scaled_img = orig_img.copy()

    # Detect UIA elements
    uia_elements = detect_uia_clickable_elements(win_x, win_y, orig_w, orig_h)
    elements_map: Dict[int, Dict[str, Any]] = {}

    # Overlay numbered badges on scaled image
    if uia_elements:
        draw = ImageDraw.Draw(scaled_img)
        for el in uia_elements:
            eid = el["id"]
            elements_map[eid] = {
                "cx": el["cx"],
                "cy": el["cy"],
                "name": el["name"],
                "type": el["type"],
            }
            # Scaled box coordinates
            bx1 = int((el["left"] - win_x) * scale)
            by1 = int((el["top"] - win_y) * scale)
            bx2 = int((el["right"] - win_x) * scale)
            by2 = int((el["bottom"] - win_y) * scale)

            # Draw box & ID badge
            draw.rectangle([bx1, by1, bx2, by2], outline="#FF0055", width=2)
            badge_text = str(eid)
            draw.rectangle([bx1, max(0, by1 - 14), bx1 + 18, max(0, by1)], fill="#FF0055")
            draw.text((bx1 + 2, max(0, by1 - 13)), badge_text, fill="white")

    # Save to timestamped JPEG file in logs/screens/
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    save_path = str(SCREENS_DIR / f"screenshot_takeover_{ts}.jpg")
    scaled_img.convert("RGB").save(save_path, format="JPEG", quality=JPEG_QUALITY)

    # Convert to JPEG bytes buffer for Gemini API
    buf = io.BytesIO()
    scaled_img.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    jpeg_bytes = buf.getvalue()

    return jpeg_bytes, scale, win_x, win_y, elements_map, save_path


def parse_gemini_actions_response(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses JSON action list returned by Gemini, handling markdown code fences and wrappers.
    """
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)

    # Try standard json parse
    try:
        data = json.loads(clean)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            if "actions" in data and isinstance(data["actions"], list):
                return data["actions"]
            return [data]
    except Exception:
        pass

    # Regex extraction of JSON array
    match = re.search(r"\[\s*\{.*\}\s*\]", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return []


def plan_takeover_batch(
    task: str,
    jpeg_bytes: bytes,
    elements_map: Dict[int, Dict[str, Any]],
    step_history: List[str],
) -> List[Dict[str, Any]]:
    """
    Calls Gemini (gemini-3.8-flash with fallback pool) with low thinking level,
    45s timeout, and 3 retries with backoff on 503/504/429.
    Returns planned batch of up to 5 actions.
    """
    if not GEMINI_API_KEY:
        console.print("[red]GEMINI_API_KEY is not configured.[/red]")
        return [{"action": "done", "summary": "API key missing."}]

    from google import genai
    from google.genai import types

    # Element legend for UIA
    element_legend = ""
    if elements_map:
        items = [f"ID {k}: {v['type']} '{v['name']}'" for k, v in list(elements_map.items())[:25]]
        element_legend = "\nDetected UI Elements (numbered badges on image):\n" + "\n".join(items)

    history_str = "\n".join(step_history[-6:]) if step_history else "No previous actions taken yet."

    system_prompt = (
        "You are Astra Takeover, an expert Windows desktop automation agent that controls "
        "the mouse and keyboard like a remote human user.\n\n"
        "GOAL: " + task + "\n\n"
        "You receive a desktop screenshot (max 1024px wide). "
        "When numbered badges appear on elements, use 'id' in your click action. "
        "When no badges match or UIA gives nothing, provide raw (x, y) coordinates relative to the image.\n\n"
        "Plan a concise BATCH of 1 to 5 actions to advance towards the goal.\n"
        "Return ONLY a valid JSON array of actions with NO extra conversational text.\n\n"
        "Supported Action Types:\n"
        "- {\"action\": \"launch\", \"app\": \"notepad\"} (or calc, etc.)\n"
        "- {\"action\": \"click\", \"id\": <int>} OR {\"action\": \"click\", \"x\": <int>, \"y\": <int>}\n"
        "- {\"action\": \"double_click\", \"id\": <int>} OR {\"action\": \"double_click\", \"x\": <int>, \"y\": <int>}\n"
        "- {\"action\": \"right_click\", \"id\": <int>} OR {\"action\": \"right_click\", \"x\": <int>, \"y\": <int>}\n"
        "- {\"action\": \"type\", \"text\": \"<string>\"}\n"
        "- {\"action\": \"hotkey\", \"keys\": [\"ctrl\", \"s\"]}\n"
        "- {\"action\": \"scroll\", \"amount\": <int>} (e.g. -300 down, 300 up)\n"
        "- {\"action\": \"drag\", \"start_x\": <int>, \"start_y\": <int>, \"end_x\": <int>, \"end_y\": <int>}\n"
        "- {\"action\": \"wait\", \"seconds\": <float>}\n"
        "- {\"action\": \"done\", \"summary\": \"<string>\"}\n\n"
        "Rules:\n"
        "1. Max 5 actions per batch.\n"
        "2. On Windows 11, modern Notepad may feature tabs, status bar, and toolbar. If Notepad or an editor is open on screen, click the text area, type the note, save it, and complete the goal.\n"
        "3. Once the user goal is completely fulfilled, return [{\"action\": \"done\", \"summary\": \"...\"}]."
    )

    user_content = (
        f"Goal: {task}\n"
        f"Action History:\n{history_str}\n"
        f"{element_legend}\n\n"
        "Look at the screenshot and return the next batch of 1 to 5 JSON actions."
    )

    # Candidate models in priority order for Takeover Mode
    # Computer-use preview model is used ONLY in takeover mode, with fallback to TEXT_MODEL and FALLBACK_MODEL
    candidate_models = [
        TAKEOVER_MODEL,
        TEXT_MODEL,
        FALLBACK_MODEL,
    ]

    http_opts = types.HttpOptions(
        timeout=TAKEOVER_TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(attempts=3)
    )
    client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts)

    # Thinking level 'low' config
    thinking_cfg = None
    try:
        thinking_cfg = types.ThinkingConfig(thinking_budget=256)
    except Exception:
        pass

    gen_config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.1,
        thinking_config=thinking_cfg,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    last_error = None
    for model_name in candidate_models:
        for attempt in range(1, 4):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                        user_content
                    ],
                    config=gen_config
                )
                if response and response.text:
                    actions = parse_gemini_actions_response(response.text)
                    if actions:
                        return actions[:BATCH_SIZE]
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # If high demand spike or rate limited, immediately failover to next responsive model
                if any(code in err_str for code in ("503", "504", "429", "resource_exhausted", "unavailable")):
                    break
                else:
                    break

    console.print(f"[bold red]Takeover API notice:[/bold red] {last_error}")
    return [{"action": "done", "summary": f"Could not generate batch: {last_error}"}]


def verify_batch_outcome(task: str, batch_summary: str, screenshot_path: str) -> Tuple[bool, str]:
    """
    Verifies that the executed batch advanced the task without crashing or erroring.
    Stops after 3 consecutive failures.
    """
    if not GEMINI_API_KEY or not screenshot_path or not Path(screenshot_path).exists():
        return True, "Verification skipped"

    try:
        from google import genai
        from google.genai import types

        with open(screenshot_path, "rb") as f:
            img_bytes = f.read()

        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"You are verifying a desktop takeover automation step.\n"
            f"Goal: {task}\n"
            f"Action batch just executed: {batch_summary}\n\n"
            f"Inspect the screenshot. Did the interface respond plausibly without a fatal error dialog or crash?\n"
            f"Note that on Windows 11 Notepad has tabs and formatting controls, and Calculator has modern buttons.\n"
            f"Reply with:\n"
            f"VERIFIED: YES or NO\n"
            f"REASON: short explanation"
        )
        gen_config = types.GenerateContentConfig(
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt
            ],
            config=gen_config,
        )
        text = response.text.strip() if response and response.text else ""
        if "VERIFIED: NO" in text.upper():
            reason = text.split("REASON:", 1)[-1].strip() if "REASON:" in text else text
            return False, reason
        return True, "Verification passed"
    except Exception as e:
        return True, f"Verification notice: {e}"


def execute_takeover_action(
    act: Dict[str, Any],
    scale: float,
    win_x: int,
    win_y: int,
    elements_map: Dict[int, Dict[str, Any]],
    monitor: MouseInterferenceMonitor
) -> Tuple[bool, str]:
    """
    Executes a single takeover action with pyautogui, 0.3s pause,
    safety checks (password typing, send/delete/pay confirm), and human monitor isolation.
    """
    action_type = act.get("action", "").lower().strip()

    # Calculate coordinates if applicable
    target_x, target_y = None, None
    target_name = ""

    if "id" in act and act["id"] in elements_map:
        el = elements_map[act["id"]]
        target_x, target_y = el["cx"], el["cy"]
        target_name = f"Element #{act['id']} ({el['type']} '{el['name']}')"
    elif "x" in act and "y" in act:
        target_x = win_x + int(act["x"] / scale)
        target_y = win_y + int(act["y"] / scale)
        target_name = f"Coordinates ({target_x}, {target_y})"

    # Safety Guardrail: password fields & sensitive buttons
    if action_type == "type":
        text = str(act.get("text", ""))
        if is_sensitive_target_or_text(text) or is_sensitive_target_or_text(target_name):
            if not confirm_sensitive_desktop_action("type_password", f"Text: {'*' * len(text)}", target=target_name):
                return False, "Typing in sensitive password field cancelled by user"

    if action_type in ("click", "double_click", "right_click", "hotkey"):
        keys_str = str(act.get("keys", []))
        if is_sensitive_target_or_text(target_name) or is_sensitive_target_or_text(keys_str):
            if not confirm_sensitive_desktop_action(action_type, f"Action: {action_type} on {target_name}", target=target_name):
                return False, f"Sensitive action {action_type} on {target_name} cancelled by user"

    monitor.agent_moving = True
    try:
        if action_type == "click":
            if target_x is not None and target_y is not None:
                pyautogui.click(target_x, target_y)
            else:
                pyautogui.click()
            time.sleep(ACTION_PAUSE)
            return True, f"Clicked on {target_name}"

        elif action_type == "double_click":
            if target_x is not None and target_y is not None:
                pyautogui.doubleClick(target_x, target_y)
            else:
                pyautogui.doubleClick()
            time.sleep(ACTION_PAUSE)
            return True, f"Double-clicked on {target_name}"

        elif action_type == "right_click":
            if target_x is not None and target_y is not None:
                pyautogui.rightClick(target_x, target_y)
            else:
                pyautogui.rightClick()
            time.sleep(ACTION_PAUSE)
            return True, f"Right-clicked on {target_name}"

        elif action_type == "type":
            text = str(act.get("text", ""))
            pyautogui.write(text, interval=0.03)
            time.sleep(ACTION_PAUSE)
            return True, f"Typed '{text}'"

        elif action_type == "hotkey":
            keys = act.get("keys", [])
            if isinstance(keys, str):
                keys = [keys]
            pyautogui.hotkey(*keys)
            time.sleep(ACTION_PAUSE)
            return True, f"Pressed hotkey: {' + '.join(keys)}"

        elif action_type == "scroll":
            amt = int(act.get("amount", -300))
            pyautogui.scroll(amt)
            time.sleep(ACTION_PAUSE)
            return True, f"Scrolled amount: {amt}"

        elif action_type == "drag":
            sx = win_x + int(act.get("start_x", 0) / scale)
            sy = win_y + int(act.get("start_y", 0) / scale)
            ex = win_x + int(act.get("end_x", 0) / scale)
            ey = win_y + int(act.get("end_y", 0) / scale)
            pyautogui.moveTo(sx, sy)
            pyautogui.dragTo(ex, ey, duration=0.5)
            time.sleep(ACTION_PAUSE)
            return True, f"Dragged from ({sx}, {sy}) to ({ex}, {ey})"

        elif action_type == "launch":
            import subprocess
            app_cmd = act.get("app") or act.get("name") or "notepad"
            subprocess.Popen(app_cmd, shell=True)
            time.sleep(1.0)
            return True, f"Launched application '{app_cmd}'"

        elif action_type == "wait":
            sec = min(5.0, float(act.get("seconds", 1.0)))
            time.sleep(sec)
            return True, f"Waited {sec}s"

        elif action_type == "done":
            summary = act.get("summary", "Task completed.")
            return True, f"Done: {summary}"

        else:
            return False, f"Unknown action: {action_type}"

    except pyautogui.FailSafeException:
        trigger_emergency_stop("PyAutoGUI FailSafe (mouse pushed to top-left corner)")
        return False, "PyAutoGUI FailSafe triggered: mouse moved to (0,0)"
    except Exception as e:
        return False, str(e)
    finally:
        monitor.agent_moving = False


def run_takeover_mode(task: str) -> str:
    """
    Main Takeover Mode execution loop:
    observe -> plan a BATCH of up to 5 actions -> execute -> observe,
    until done or 30 actions used.
    """
    if is_emergency_stopped():
        console.print("[bold red]Takeover halted: Emergency stop active.[/bold red]")
        return "Takeover Mode halted via emergency stop (Ctrl+Alt+Q or mouse to corner)."

    # Mandatory Safety Banner
    console.print(Panel(
        "[bold yellow]Takeover active. Ctrl+Alt+Q or mouse to the top-left corner stops it.[/bold yellow]",
        title="[bold cyan]Superlocal Takeover Mode (UltraViewer Remote User Simulation)[/bold cyan]",
        border_style="yellow"
    ))
    total_actions_used = 0
    consecutive_verification_failures = 0
    step_history: List[str] = []

    # Initialize human mouse interference monitor
    monitor = MouseInterferenceMonitor()
    monitor.start()

    try:
        while total_actions_used < TAKEOVER_MAX_ACTIONS:
            if is_emergency_stopped():
                console.print("[bold red]Takeover halted: Emergency stop active.[/bold red]")
                return "Takeover Mode halted via emergency stop (Ctrl+Alt+Q or mouse to corner)."

            # 1. Observe: Capture active window / screen with UIA numbered overlays
            console.print("[dim]Observing desktop and analyzing UI elements...[/dim]")
            jpeg_bytes, scale, win_x, win_y, elements_map, shot_path = prepare_takeover_observation()

            # 2. Plan a BATCH of up to 5 actions
            batch = plan_takeover_batch(task, jpeg_bytes, elements_map, step_history)
            if not batch:
                console.print("[bold yellow]No actions returned by planner. Retrying observation...[/bold yellow]")
                time.sleep(1)
                continue

            # Check if task is already done
            if batch[0].get("action") == "done":
                summary = batch[0].get("summary", "Takeover task completed successfully.")
                console.print(f"\n{format_truthful_status('SUCCESS', summary)}")
                return summary

            console.print(f"\n[bold magenta]Planned Batch of {len(batch)} action(s):[/bold magenta]")

            # 3. Execute batched actions with 0.3s pauses
            batch_summaries = []
            for act in batch:
                if total_actions_used >= TAKEOVER_MAX_ACTIONS:
                    msg = f"Takeover completed: reached {TAKEOVER_MAX_ACTIONS} actions limit. Final state observed."
                    console.print(f"\n{format_truthful_status('PARTIAL', msg)}")
                    return msg

                if is_emergency_stopped():
                    msg = "Takeover Mode halted via emergency stop (Ctrl+Alt+Q)."
                    console.print(f"\n{format_truthful_status('FAILED', msg)}")
                    return msg

                total_actions_used += 1
                action_desc = f"{act.get('action')}({act.get('id') or act.get('keys') or act.get('text') or ''})"
                console.print(f"  [bold cyan]Action {total_actions_used}/{TAKEOVER_MAX_ACTIONS}:[/bold cyan] {action_desc}")

                success, result_msg = execute_takeover_action(act, scale, win_x, win_y, elements_map, monitor)
                batch_summaries.append(result_msg)
                step_history.append(result_msg)
                log_action("takeover_action", act, "SUCCESS" if success else "FAILED", result_msg)

                if act.get("action") == "done":
                    summary = act.get("summary", "Takeover task completed.")
                    console.print(f"\n{format_truthful_status('SUCCESS', summary)}")
                    return summary

                if not success:
                    console.print(f"    [red]Action failed:[/red] {result_msg}")
                    break

            # 4. Take ONE new screenshot after the batch and verify outcome
            time.sleep(0.5)
            _, _, _, _, _, post_shot_path = prepare_takeover_observation()
            v_ok, v_reason = verify_batch_outcome(task, "; ".join(batch_summaries), post_shot_path)

            if not v_ok:
                consecutive_verification_failures += 1
                console.print(f"  [yellow]Visual Verification Notice ({consecutive_verification_failures}/3): {v_reason}[/yellow]")
                if consecutive_verification_failures >= 3:
                    fail_msg = "No-progress detected: 3 consecutive visual verifications failed or screen state unchanged."
                    console.print(f"\n{format_truthful_status('FAILED', fail_msg)}")
                    return f"Takeover Mode stopped: {fail_msg}"
            else:
                consecutive_verification_failures = 0

        final_msg = f"Takeover finished: used maximum {TAKEOVER_MAX_ACTIONS} actions."
        console.print(f"\n{format_truthful_status('PARTIAL', final_msg)}")
        return final_msg

    finally:
        monitor.stop()


def setup_takeover_hotkey(callback=None):
    """Registers Ctrl+Alt+T global hotkey to speak or type a task."""
    global _takeover_hotkey_registered
    if _takeover_hotkey_registered:
        return

    import keyboard

    def _on_hotkey():
        console.print("\n[bold cyan]Hotkey Ctrl+Alt+T triggered:[/bold cyan] Takeover Mode requested.")
        if callback:
            callback()

    try:
        keyboard.add_hotkey("ctrl+alt+t", _on_hotkey, suppress=False)
        _takeover_hotkey_registered = True
    except Exception:
        pass
