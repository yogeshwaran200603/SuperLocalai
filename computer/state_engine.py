"""
SuperLocal Computer Mode: Screen State Engine
Multi-tiered perception engine (cheapest first):
1. A11y Tree: pywinauto UIA for native apps, compact text (max 80 items) with clickable IDs
2. Local OCR: RapidOCR on the active window for custom UI / non-UIA apps
3. Vision: Active window screenshot, resized to max 1024px, JPEG quality 50 with numbered boxes
State caching and hashing prevents redundant screen captures when the screen hasn't changed.
"""

import os
import sys
import io
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont
import pyautogui
import pygetwindow as gw

from config import (
    COMPUTER_VISION_MAX_WIDTH,
    COMPUTER_VISION_JPEG_QUALITY,
    SAVE_SCREENS,
    SCREENS_DIR,
)

# Optional RapidOCR import
try:
    from rapidocr_onnxruntime import RapidOCR
    _RAPID_OCR_INSTANCE = RapidOCR()
except Exception:
    _RAPID_OCR_INSTANCE = None


@dataclass
class UIElement:
    id: int
    name: str
    control_type: str
    bounds: Tuple[int, int, int, int]  # (x, y, w, h)
    center: Tuple[int, int]           # (cx, cy)
    source: str                       # a11y, ocr, vision
    state: str = "Enabled"

    def to_compact_str(self) -> str:
        clean_name = self.name.replace("\n", " ").strip()[:40]
        return f"[{self.id}] {self.control_type} \"{clean_name}\" ({self.state}) at ({self.center[0]},{self.center[1]})"


@dataclass
class ScreenState:
    window_title: str
    window_bounds: Tuple[int, int, int, int]
    source: str
    elements: List[UIElement]
    compact_text: str
    state_hash: str
    scale_factor: float = 1.0
    screenshot_bytes: Optional[bytes] = None
    created_at: float = field(default_factory=time.time)

    def find_element_by_id(self, el_id: int) -> Optional[UIElement]:
        for el in self.elements:
            if el.id == el_id:
                return el
        return None

    def find_element_by_text(self, text: str) -> Optional[UIElement]:
        q = text.lower().strip()
        for el in self.elements:
            if q in el.name.lower():
                return el
        return None


class ComputerStateEngine:
    """
    Tiered screen perception engine with state caching and change detection.
    """

    def __init__(self):
        self._last_state: Optional[ScreenState] = None
        self._last_hash: Optional[str] = None
        self.ocr = _RAPID_OCR_INSTANCE

    def get_active_window_info(self) -> Tuple[str, Tuple[int, int, int, int]]:
        """Returns (title, (x, y, w, h)) of the current active foreground window."""
        try:
            active = gw.getActiveWindow()
            if active and active.visible and not active.isMinimized and active.width > 20 and active.height > 20:
                return (
                    active.title or "Active Window",
                    (max(0, active.left), max(0, active.top), active.width, active.height)
                )
        except Exception:
            pass

        # Fallback to entire virtual desktop
        try:
            size = pyautogui.size()
            return "Desktop", (0, 0, size.width, size.height)
        except Exception:
            return "Screen", (0, 0, 1920, 1080)

    def capture_active_window_image(self, bounds: Tuple[int, int, int, int]) -> Image.Image:
        """Captures region for the active window."""
        x, y, w, h = bounds
        try:
            return pyautogui.screenshot(region=(x, y, w, h))
        except Exception:
            # Fallback
            return Image.new("RGB", (max(100, w), max(100, h)), color=(40, 40, 40))

    def _extract_a11y_tree(self, bounds: Tuple[int, int, int, int], win_title: str) -> List[UIElement]:
        """
        Tier 1: pywinauto UIA accessibility tree.
        Extracts up to 80 compact interactive elements.
        """
        elements: List[UIElement] = []
        win_x, win_y, win_w, win_h = bounds

        try:
            import pywinauto
            desktop = pywinauto.Desktop(backend="uia")
            windows = desktop.windows()
            target_win = None

            for w in windows:
                try:
                    r = w.rectangle()
                    if abs(r.left - win_x) < 50 and abs(r.top - win_y) < 50:
                        target_win = w
                        break
                except Exception:
                    continue

            if not target_win and windows:
                target_win = windows[0]

            if target_win:
                descendants = target_win.descendants()
                allowed_types = {
                    "Button", "Edit", "MenuItem", "TabItem", "CheckBox",
                    "RadioButton", "Hyperlink", "ListItem", "ComboBox", "Document", "Text"
                }

                elem_id = 1
                for el in descendants:
                    if elem_id > 80:
                        break
                    try:
                        info = el.element_info
                        c_type = info.control_type
                        name = info.name or ""
                        if c_type in allowed_types and (name.strip() or c_type in ("Button", "Edit", "MenuItem")):
                            rect = el.rectangle()
                            w, h = rect.width(), rect.height()
                            if w > 5 and h > 5:
                                cx = rect.left + w // 2
                                cy = rect.top + h // 2
                                elements.append(UIElement(
                                    id=elem_id,
                                    name=name or f"<{c_type}>",
                                    control_type=c_type,
                                    bounds=(rect.left, rect.top, w, h),
                                    center=(cx, cy),
                                    source="a11y",
                                    state="Enabled" if el.is_enabled() else "Disabled"
                                ))
                                elem_id += 1
                    except Exception:
                        continue
        except Exception:
            pass

        return elements

    def _extract_ocr_elements(self, img: Image.Image, bounds: Tuple[int, int, int, int]) -> List[UIElement]:
        """
        Tier 2: Local OCR using RapidOCR.
        Extracts bounding boxes and text from the active window image.
        """
        elements: List[UIElement] = []
        if not self.ocr:
            return elements

        win_x, win_y, _, _ = bounds

        try:
            import numpy as np
            np_img = np.array(img)
            ocr_results, _ = self.ocr(np_img)

            if ocr_results:
                elem_id = 1
                for item in ocr_results:
                    if elem_id > 80:
                        break
                    try:
                        box, text, score = item[0], item[1], item[2]
                        if float(score) > 0.4 and text.strip():
                            # Box is 4 points: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                            xs = [p[0] for p in box]
                            ys = [p[1] for p in box]
                            bx = int(min(xs)) + win_x
                            by = int(min(ys)) + win_y
                            bw = int(max(xs) - min(xs))
                            bh = int(max(ys) - min(ys))
                            cx = bx + bw // 2
                            cy = by + bh // 2

                            elements.append(UIElement(
                                id=elem_id,
                                name=text.strip(),
                                control_type="OCR_Text",
                                bounds=(bx, by, bw, bh),
                                center=(cx, cy),
                                source="ocr",
                                state=f"{score:.2f} conf"
                            ))
                            elem_id += 1
                    except Exception:
                        continue
        except Exception:
            pass

        return elements

    def _render_vision_screenshot(
        self, img: Image.Image, elements: List[UIElement], bounds: Tuple[int, int, int, int]
    ) -> Tuple[bytes, float]:
        """
        Tier 3: Vision capture with max 1024px width, JPEG quality 50, and numbered badges.
        """
        win_x, win_y, _, _ = bounds
        orig_w, orig_h = img.size

        # Scale down if width > COMPUTER_VISION_MAX_WIDTH (1024px)
        scale = 1.0
        if orig_w > COMPUTER_VISION_MAX_WIDTH:
            scale = COMPUTER_VISION_MAX_WIDTH / float(orig_w)
            new_h = int(orig_h * scale)
            vis_img = img.resize((COMPUTER_VISION_MAX_WIDTH, new_h), Image.Resampling.LANCZOS)
        else:
            vis_img = img.copy()

        draw = ImageDraw.Draw(vis_img)
        font = ImageFont.load_default()

        # Overlay numbered badges
        for el in elements:
            bx, by, bw, bh = el.bounds
            rel_x = int((bx - win_x) * scale)
            rel_y = int((by - win_y) * scale)
            rel_w = int(bw * scale)
            rel_h = int(bh * scale)

            # Draw rectangle
            draw.rectangle([rel_x, rel_y, rel_x + rel_w, rel_y + rel_h], outline="red", width=2)
            badge_text = str(el.id)
            draw.rectangle([rel_x, rel_y, rel_x + 18, rel_y + 14], fill="red")
            draw.text((rel_x + 2, rel_y + 1), badge_text, fill="white", font=font)

        out_io = io.BytesIO()
        vis_img.save(out_io, format="JPEG", quality=COMPUTER_VISION_JPEG_QUALITY)
        return out_io.getvalue(), scale

    def capture_state(self, effort: str = "medium", force_refresh: bool = False) -> ScreenState:
        """
        Captures the screen state following the cheapest-first hierarchy:
        1. A11y Tree
        2. RapidOCR (if a11y yields nothing or on medium/high)
        3. Vision (if requested in high, or when levels 1 & 2 fail)
        """
        win_title, bounds = self.get_active_window_info()

        # 1. Try A11y tree first
        elements = self._extract_a11y_tree(bounds, win_title)
        source = "a11y"

        # 2. If a11y gave 0 items and effort is medium or high, try OCR
        img = None
        if not elements and effort in ("medium", "high"):
            img = self.capture_active_window_image(bounds)
            elements = self._extract_ocr_elements(img, bounds)
            if elements:
                source = "ocr"

        # Compute hash
        hash_str = f"{win_title}|{len(elements)}|" + ";".join(e.name[:8] for e in elements[:15])
        current_hash = hashlib.md5(hash_str.encode("utf-8", errors="replace")).hexdigest()

        if not force_refresh and self._last_state and self._last_hash == current_hash:
            return self._last_state

        # 3. Vision screenshot if effort is high or elements still empty
        screenshot_bytes = None
        scale_factor = 1.0
        if effort == "high" or (not elements and effort == "medium"):
            if img is None:
                img = self.capture_active_window_image(bounds)
            screenshot_bytes, scale_factor = self._render_vision_screenshot(img, elements, bounds)
            source = "vision" if not elements else source

        # Format compact text representation
        lines = [f"=== Active Window: '{win_title}' ({source.upper()}) ==="]
        if elements:
            for el in elements:
                lines.append(el.to_compact_str())
        else:
            lines.append("No clickable elements detected via accessibility or OCR.")

        compact_text = "\n".join(lines)

        state = ScreenState(
            window_title=win_title,
            window_bounds=bounds,
            source=source,
            elements=elements,
            compact_text=compact_text,
            state_hash=current_hash,
            scale_factor=scale_factor,
            screenshot_bytes=screenshot_bytes,
        )

        self._last_state = state
        self._last_hash = current_hash
        return state
