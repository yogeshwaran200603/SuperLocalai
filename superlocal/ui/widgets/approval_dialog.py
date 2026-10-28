"""
SuperLocal Safety Approval Modal Dialog
Displays:
- Detailed breakdown of gated action
- Risk badge (High = Red, Medium = Orange, Low = Blue)
- Exact target (file, app, recipient)
- For send actions: shows recipient and message preview
- "Allow once" / "Always for this session" (disabled for delete/send/pay/install/admin) / "Deny"
- 60-second countdown timer (timeout automatically defaults to Deny)
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QApplication,
)
from superlocal.ui.theme import Colors


class ApprovalDialog(QDialog):
    """Modal confirmation card for sensitive operations."""

    decision_made = Signal(bool, bool)  # (approved, always_for_session)

    def __init__(
        self,
        request_id: str,
        action_type: str,
        details: dict,
        risk_level: str = "medium",
        target: str = "",
        message: str = "",
        timeout_seconds: int = 60,
        parent=None,
    ):
        super().__init__(parent)
        self.request_id = request_id
        self.action_type = action_type
        self.details = details or {}
        self.risk_level = risk_level.lower()
        self.target = target
        self.remaining_seconds = timeout_seconds

        self.setWindowTitle("SuperLocal Security Confirmation")
        self.setFixedWidth(460)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Header with Risk Badge
        header_layout = QHBoxLayout()
        title_label = QLabel("Permission Required", self)
        title_label.setStyleSheet("font-size: 16px; font-weight: 700;")

        risk_color = Colors.DANGER if self.risk_level == "high" else (Colors.WARNING if self.risk_level == "medium" else Colors.ACCENT)
        self.risk_badge = QLabel(f" {self.risk_level.upper()} RISK ", self)
        self.risk_badge.setStyleSheet(f"""
            background-color: {risk_color};
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 700;
            border-radius: 4px;
            padding: 3px 6px;
        """)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.risk_badge)
        layout.addLayout(header_layout)

        # 2. Main Explanation Card
        card = QFrame(self)
        card.setProperty("card", "true")
        card.setStyleSheet("""
            QFrame[card="true"] {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        # Action Type & Description
        act_label = QLabel(f"<b>Action:</b> {action_type}", card)
        card_layout.addWidget(act_label)

        if self.target:
            target_label = QLabel(f"<b>Target:</b> {self.target}", card)
            target_label.setWordWrap(True)
            card_layout.addWidget(target_label)

        # Send action preview
        if "send" in action_type.lower() or "recipient" in self.details:
            recipient = self.details.get("recipient") or self.details.get("phone") or "Unknown"
            msg_preview = self.details.get("message") or self.details.get("text") or ""
            send_box = QLabel(f"<b>Recipient:</b> {recipient}<br><b>Message:</b> {msg_preview}", card)
            send_box.setStyleSheet("background: rgba(0,0,0,0.2); padding: 6px; border-radius: 4px;")
            send_box.setWordWrap(True)
            card_layout.addWidget(send_box)
        elif self.details:
            details_str = str(self.details)
            if len(details_str) > 200:
                details_str = details_str[:200] + "..."
            dt_label = QLabel(f"<span style='color:#AAAAAA; font-family:Consolas, monospace;'>{details_str}</span>", card)
            dt_label.setWordWrap(True)
            card_layout.addWidget(dt_label)

        layout.addWidget(card)

        # 3. Countdown timer label
        self.timer_label = QLabel(f"Auto-denying in {self.remaining_seconds}s...", self)
        self.timer_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self.timer_label)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.deny_btn = QPushButton("Deny", self)
        self.deny_btn.setCursor(Qt.PointingHandCursor)
        self.deny_btn.clicked.connect(self._on_deny)

        self.allow_once_btn = QPushButton("Allow once", self)
        self.allow_once_btn.setProperty("accent", "true")
        self.allow_once_btn.setCursor(Qt.PointingHandCursor)
        self.allow_once_btn.clicked.connect(self._on_allow_once)

        btn_layout.addWidget(self.deny_btn)

        # "Always for this session" is NEVER offered for sensitive actions (send, delete, pay, install, admin)
        disallowed_always = ("send", "delete", "pay", "install", "admin", "rmdir")
        can_always = not any(w in action_type.lower() for w in disallowed_always)

        if can_always:
            self.allow_always_btn = QPushButton("Always for this session", self)
            self.allow_always_btn.setCursor(Qt.PointingHandCursor)
            self.allow_always_btn.clicked.connect(self._on_allow_always)
            btn_layout.addWidget(self.allow_always_btn)

        btn_layout.addWidget(self.allow_once_btn)
        layout.addLayout(btn_layout)

        # Start 60s countdown timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer.start(1000)

        # Play alert chime / beep
        try:
            QApplication.beep()
        except Exception:
            pass

    def _on_timer_tick(self):
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.timer.stop()
            self._on_deny()
        else:
            self.timer_label.setText(f"Auto-denying in {self.remaining_seconds}s...")

    def _on_allow_once(self):
        self.timer.stop()
        self.decision_made.emit(True, False)
        self.accept()

    def _on_allow_always(self):
        self.timer.stop()
        self.decision_made.emit(True, True)
        self.accept()

    def _on_deny(self):
        self.timer.stop()
        self.decision_made.emit(False, False)
        self.reject()

    def closeEvent(self, event):
        self.timer.stop()
        self._on_deny()
        super().closeEvent(event)
