"""
SuperLocal Voice Page
Interactive voice assistant workbench:
- Animated voice orb (idle, listening, thinking, speaking)
- Live partial and final transcript display
- Spoken response card
- Push-to-talk button (also bound to F9)
- Audio level meter (RMS)
- Microphone and speaker selectors
- Wake-word toggle ("Hey SuperLocal")
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QComboBox,
    QCheckBox,
    QFrame,
    QScrollArea,
)
from superlocal.ui.theme import Colors
from superlocal.ui.widgets.orb import VoiceOrb
from core.events import EventType


class VoicePage(QWidget):
    """Voice interaction and audio control page."""

    push_to_talk_triggered = Signal(bool)  # is_active
    mic_device_changed = Signal(int)       # device_index
    wake_word_toggled = Signal(bool)      # is_enabled

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Header
        header_box = QHBoxLayout()
        title_label = QLabel("Voice Assistant", self)
        title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        header_box.addWidget(title_label)
        header_box.addStretch()

        self.wake_check = QCheckBox("Wake-word ('Hey SuperLocal')", self)
        self.wake_check.setChecked(True)
        self.wake_check.toggled.connect(self.wake_word_toggled.emit)
        header_box.addWidget(self.wake_check)
        main_layout.addLayout(header_box)

        # Center Orb Container
        orb_container = QWidget(self)
        orb_layout = QVBoxLayout(orb_container)
        orb_layout.setAlignment(Qt.AlignCenter)

        self.orb = VoiceOrb(orb_container)
        self.orb.setFixedSize(260, 260)
        orb_layout.addWidget(self.orb, alignment=Qt.AlignCenter)

        self.state_label = QLabel("Idle • Ready", orb_container)
        self.state_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #888888; margin-top: 6px;")
        orb_layout.addWidget(self.state_label, alignment=Qt.AlignCenter)

        main_layout.addWidget(orb_container)

        # Audio Meter
        meter_box = QHBoxLayout()
        meter_label = QLabel("Mic Level:", self)
        meter_label.setStyleSheet("font-size: 11px; color: #888888;")
        self.level_bar = QProgressBar(self)
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(8)
        self.level_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.SURFACE};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.ACCENT};
                border-radius: 4px;
            }}
        """)
        meter_box.addWidget(meter_label)
        meter_box.addWidget(self.level_bar, stretch=1)
        main_layout.addLayout(meter_box)

        # Transcripts Card
        transcript_card = QFrame(self)
        transcript_card.setProperty("card", "true")
        tc_layout = QVBoxLayout(transcript_card)
        tc_layout.setContentsMargins(16, 12, 16, 12)
        tc_layout.setSpacing(8)

        self.partial_label = QLabel("Listening for speech...", transcript_card)
        self.partial_label.setStyleSheet("font-size: 13px; font-style: italic; color: #0078D4;")
        self.partial_label.setWordWrap(True)

        self.final_label = QLabel("User: (No recent voice command)", transcript_card)
        self.final_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.final_label.setWordWrap(True)

        self.reply_label = QLabel("SuperLocal: \"I'm listening. Press F9 or say 'Hey SuperLocal' to begin.\"", transcript_card)
        self.reply_label.setStyleSheet("font-size: 13px; color: #BBBBBB;")
        self.reply_label.setWordWrap(True)

        tc_layout.addWidget(self.partial_label)
        tc_layout.addWidget(self.final_label)
        tc_layout.addWidget(self.reply_label)
        main_layout.addWidget(transcript_card)

        # Controls & Push-To-Talk Button
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        self.ptt_btn = QPushButton("🎙 Hold to Talk (F9)", self)
        self.ptt_btn.setProperty("accent", "true")
        self.ptt_btn.setFixedHeight(44)
        self.ptt_btn.setStyleSheet("font-size: 14px; font-weight: bold; border-radius: 8px;")
        self.ptt_btn.pressed.connect(self._on_ptt_pressed)
        self.ptt_btn.released.connect(self._on_ptt_released)

        # Global F9 shortcut inside the app
        self.f9_shortcut = QShortcut(QKeySequence("F9"), self)
        self.f9_shortcut.activated.connect(self._toggle_ptt)

        btn_box.addWidget(self.ptt_btn, stretch=2)
        main_layout.addLayout(btn_box)

        # Device Pickers Bar
        dev_box = QHBoxLayout()
        dev_box.setSpacing(12)

        mic_label = QLabel("Microphone:", self)
        mic_label.setStyleSheet("color: #888888; font-size: 11px;")
        self.mic_combo = QComboBox(self)
        self._populate_audio_devices()
        self.mic_combo.currentIndexChanged.connect(self._on_mic_selected)

        dev_box.addWidget(mic_label)
        dev_box.addWidget(self.mic_combo, stretch=1)
        main_layout.addLayout(dev_box)

        self._ptt_active = False

    def _populate_audio_devices(self):
        self.mic_combo.addItem("Default System Microphone", -1)
        try:
            import sounddevice as sd
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    self.mic_combo.addItem(f"{idx}: {dev.get('name')}", idx)
        except Exception:
            pass

    def _on_mic_selected(self, index: int):
        dev_id = self.mic_combo.currentData()
        if dev_id is not None:
            self.mic_device_changed.emit(dev_id)

    def _on_ptt_pressed(self):
        self._ptt_active = True
        self.ptt_btn.setText("🔴 Listening... (Release to Send)")
        self.set_voice_state("listening")
        self.push_to_talk_triggered.emit(True)

    def _on_ptt_released(self):
        if self._ptt_active:
            self._ptt_active = False
            self.ptt_btn.setText("🎙 Hold to Talk (F9)")
            self.set_voice_state("thinking")
            self.push_to_talk_triggered.emit(False)

    def _toggle_ptt(self):
        if self._ptt_active:
            self._on_ptt_released()
        else:
            self._on_ptt_pressed()

    def set_voice_state(self, state: str, details: str = ""):
        self.orb.set_state(state)
        st = state.lower()
        if st == "listening":
            self.state_label.setText("Listening... • Speak now")
            self.state_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {Colors.ACCENT};")
        elif st == "thinking":
            self.state_label.setText("Thinking... • Processing command")
            self.state_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {Colors.WARNING};")
        elif st == "speaking":
            self.state_label.setText("Speaking... • Responding")
            self.state_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EC4899;")
        else:
            self.state_label.setText("Idle • Ready")
            self.state_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #888888;")

    def update_audio_level(self, level: float):
        """Update audio level (0.0 to 1.0)."""
        self.orb.set_level(level)
        self.level_bar.setValue(int(level * 100))

    def update_transcripts(self, partial: str = "", final: str = "", reply: str = ""):
        if partial:
            self.partial_label.setText(f"Interim: {partial}")
            self.partial_label.show()
        if final:
            self.final_label.setText(f"User: {final}")
            self.partial_label.setText("")
        if reply:
            self.reply_label.setText(f"SuperLocal: \"{reply}\"")
