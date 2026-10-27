"""
SuperLocal Poki Player: Fast Capture & Latency Monitor
High-performance screen capture targeted at 15-30 FPS:
- Uses mss for low-overhead bounding box capture
- Fast frame downscaling (320x180 grayscale or 640x360 RGB) via OpenCV
- ZERO cloud model calls in the loop
- Latency monitor tracks capture time, decision time, total frame time, and FPS
- Triggers fallback to simpler policies if decisions exceed game tolerance
"""

import time
from collections import deque
from typing import Dict, Any, Tuple, Optional, Union
import numpy as np
import cv2

try:
    import mss
    _MSS_INSTANCE = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
except Exception:
    _MSS_INSTANCE = None

from config import POKI_TARGET_FPS


class LatencyMonitor:
    """
    Monitors loop execution times, frame rates, and decision latency.
    """

    def __init__(self, target_fps: int = POKI_TARGET_FPS, latency_threshold_ms: float = 120.0):
        self.target_fps = target_fps
        self.target_frame_time = 1.0 / max(1, target_fps)
        self.latency_threshold_sec = latency_threshold_ms / 1000.0

        self.frame_times = deque(maxlen=30)
        self.capture_times = deque(maxlen=30)
        self.decision_times = deque(maxlen=30)

        self.last_timestamp = time.perf_counter()
        self.slow_decision_count = 0

    def start_frame(self):
        self.last_timestamp = time.perf_counter()

    def record_capture(self, start_t: float):
        dur = time.perf_counter() - start_t
        self.capture_times.append(dur)

    def record_decision(self, start_t: float) -> bool:
        """Records decision time. Returns True if decision took too long."""
        dur = time.perf_counter() - start_t
        self.decision_times.append(dur)

        is_slow = dur > self.latency_threshold_sec
        if is_slow:
            self.slow_decision_count += 1
        else:
            self.slow_decision_count = max(0, self.slow_decision_count - 1)

        return is_slow

    def end_frame(self):
        total_time = time.perf_counter() - self.last_timestamp
        self.frame_times.append(total_time)

    def get_fps(self) -> float:
        if not self.frame_times:
            return float(self.target_fps)
        avg_time = sum(self.frame_times) / len(self.frame_times)
        return round(1.0 / max(avg_time, 0.001), 1)

    def get_avg_decision_ms(self) -> float:
        if not self.decision_times:
            return 0.0
        return round((sum(self.decision_times) / len(self.decision_times)) * 1000.0, 1)

    def is_latency_critical(self) -> bool:
        """Returns True if the last 5 decisions consistently exceeded threshold."""
        return self.slow_decision_count >= 5


class GameCanvasCapture:
    """
    Captures the canvas or iframe region using mss with downscaling.
    """

    def __init__(
        self,
        bounding_box: Tuple[int, int, int, int] = (0, 0, 800, 600),
        downscale_size: Tuple[int, int] = (640, 360),
        grayscale: bool = False,
    ):
        """
        bounding_box: (x, y, width, height) in screen coordinates
        """
        self.bbox = bounding_box
        self.downscale_size = downscale_size
        self.grayscale = grayscale
        self.sct = _MSS_INSTANCE
        self.latency_monitor = LatencyMonitor()

    def update_bounding_box(self, x: int, y: int, width: int, height: int):
        self.bbox = (max(0, x), max(0, y), max(50, width), max(50, height))

    def capture_frame(self, page=None) -> np.ndarray:
        """
        Captures the region, downscales, and returns a numpy ndarray (BGR or Grayscale).
        Falls back to Playwright canvas screenshot if mss is unavailable.
        """
        t0 = time.perf_counter()
        frame = None

        x, y, w, h = self.bbox
        monitor = {"top": y, "left": x, "width": w, "height": h}

        if self.sct:
            try:
                sct_img = self.sct.grab(monitor)
                frame = np.array(sct_img)
                # mss returns BGRA
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            except Exception:
                frame = None

        # Fallback to Playwright screenshot if mss failed
        if frame is None and page:
            try:
                canvas_elem = page.locator("canvas").first
                if canvas_elem.count() > 0:
                    png_bytes = canvas_elem.screenshot(timeout=1000)
                    np_arr = np.frombuffer(png_bytes, np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            except Exception:
                frame = None

        # Dummy fallback frame (for headless/mock tests)
        if frame is None:
            frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Downscale
        if self.downscale_size and (frame.shape[1] != self.downscale_size[0] or frame.shape[0] != self.downscale_size[1]):
            frame = cv2.resize(frame, self.downscale_size, interpolation=cv2.INTER_AREA)

        # Grayscale if requested
        if self.grayscale and len(frame.shape) == 3 and frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        self.latency_monitor.record_capture(t0)
        return frame
