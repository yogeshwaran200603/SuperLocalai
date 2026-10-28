"""
Voice Orb Widget
Renders a smooth animated orb with 4 states:
- idle: soft breathing pulse
- listening: expanding ripple waves (cyan/teal)
- thinking: swirling orbital motion (amber/gold)
- speaking: sound-reactive pulse modulated by audio level (magenta/purple)
"""

import math
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QPen, QBrush
from PySide6.QtWidgets import QWidget


class VoiceOrb(QWidget):
    """Animated interactive voice orb."""

    STATE_IDLE = "idle"
    STATE_LISTENING = "listening"
    STATE_THINKING = "thinking"
    STATE_SPEAKING = "speaking"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.state = self.STATE_IDLE
        self._phase = 0.0
        self._rms_level = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(33)  # ~30 FPS

    def set_state(self, new_state: str):
        self.state = new_state.lower()
        self.update()

    def set_level(self, rms: float):
        self._rms_level = max(0.0, min(1.0, rms))
        self.update()

    def _on_tick(self):
        self._phase += 0.05
        if self._phase > 2 * math.pi * 100:
            self._phase = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        base_radius = min(w, h) * 0.28

        # Draw outer glows & ripples based on state
        if self.state == self.STATE_LISTENING:
            # Concentric expanding ripples
            for i in range(3):
                ripple_phase = (self._phase * 0.8 + i * 1.5) % 4.0
                r_radius = base_radius + ripple_phase * 18
                alpha = max(0, int(150 * (1.0 - ripple_phase / 4.0)))
                painter.setPen(QPen(QColor(0, 180, 216, alpha), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), r_radius, r_radius)

            center_color = QColor(0, 200, 255)
            outer_color = QColor(0, 119, 182, 160)
            glow_radius = base_radius * 1.3

        elif self.state == self.STATE_THINKING:
            # Swirling rotating arcs
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(math.degrees(self._phase * 2.0))
            for i in range(4):
                angle = i * 90
                alpha = 180
                painter.setPen(QPen(QColor(255, 183, 3, alpha), 3))
                painter.drawArc(QRectF(-base_radius * 1.2, -base_radius * 1.2, base_radius * 2.4, base_radius * 2.4), angle * 16, 45 * 16)
            painter.restore()

            center_color = QColor(255, 183, 3)
            outer_color = QColor(217, 119, 6, 160)
            glow_radius = base_radius * 1.2

        elif self.state == self.STATE_SPEAKING:
            # Sound reactive pulsing
            pulse = base_radius * (1.0 + 0.35 * self._rms_level + 0.1 * math.sin(self._phase * 4))
            center_color = QColor(236, 72, 153)
            outer_color = QColor(147, 51, 234, 180)
            glow_radius = pulse * 1.3

        else:  # IDLE
            # Breathing pulse
            pulse = base_radius * (1.0 + 0.06 * math.sin(self._phase))
            center_color = QColor(0, 120, 212)
            outer_color = QColor(118, 38, 250, 130)
            glow_radius = pulse * 1.25

        # Radial glow behind main orb
        glow_grad = QRadialGradient(cx, cy, glow_radius)
        glow_grad.setColorAt(0.0, QColor(outer_color.red(), outer_color.green(), outer_color.blue(), 100))
        glow_grad.setColorAt(0.8, QColor(outer_color.red(), outer_color.green(), outer_color.blue(), 30))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow_grad))
        painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        # Core Orb
        orb_grad = QRadialGradient(cx - base_radius * 0.25, cy - base_radius * 0.25, base_radius * 1.1)
        orb_grad.setColorAt(0.0, center_color)
        orb_grad.setColorAt(0.7, outer_color)
        orb_grad.setColorAt(1.0, QColor(15, 23, 42, 220))
        painter.setBrush(QBrush(orb_grad))
        painter.drawEllipse(QPointF(cx, cy), base_radius, base_radius)

        painter.end()
