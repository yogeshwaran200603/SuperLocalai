"""
SuperLocal First-Run Setup Wizard
4-Step Onboarding:
1. Consent & Safety Boundaries ("What SuperLocal can control")
2. AI Provider setup & API keys
3. Audio Input Microphone Selection
4. Default Workspace Folder Selection
"""

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFrame,
)
from superlocal.ui.theme import Colors
from superlocal.core.credentials import store_credential
from config import WORKSPACE_DIR, DATA_DIR

SETUP_FLAG_PATH = DATA_DIR / ".setup_completed"


def is_first_run() -> bool:
    return not SETUP_FLAG_PATH.exists()


def mark_setup_completed():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_FLAG_PATH.write_text("completed=true", encoding="utf-8")


class SetupWizardDialog(QDialog):
    """First-run onboarding wizard modal."""

    setup_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SuperLocal - First Run Setup")
        self.resize(600, 480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Progress indicator
        self.step_label = QLabel("Step 1 of 4: Welcome & Permissions", self)
        self.step_label.setStyleSheet("font-size: 11px; color: #888888; font-weight: bold;")
        layout.addWidget(self.step_label)

        # Stacked pages
        self.stack = QStackedWidget(self)

        # Page 1: Consent
        p1 = QWidget(self)
        p1_l = QVBoxLayout(p1)
        p1_title = QLabel("What SuperLocal Can Control", p1)
        p1_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        p1_desc = QLabel(
            "SuperLocal is an autonomous Windows assistant operating locally on your PC.<br><br>"
            "<b>Safety Boundaries & Your Consent:</b><br>"
            "• <b>Desktop Control:</b> Can automate mouse and keyboard, with a global kill-switch (<b>Ctrl+Alt+Q</b>).<br>"
            "• <b>File Operations:</b> Confined to your chosen workspace and standard user folders. Windows system files are blocked.<br>"
            "• <b>Interactive Gates:</b> Deleting files, typing passwords, or sending messages ALWAYS requires your explicit confirmation.<br>"
            "• <b>Privacy:</b> Your API keys are kept encrypted in Windows Credential Manager.",
            p1
        )
        p1_desc.setWordWrap(True)
        self.consent_check = QCheckBox("I understand SuperLocal's capabilities and safety controls", p1)
        self.consent_check.setChecked(True)

        p1_l.addWidget(p1_title)
        p1_l.addWidget(p1_desc)
        p1_l.addStretch()
        p1_l.addWidget(self.consent_check)
        self.stack.addWidget(p1)

        # Page 2: Provider Keys
        p2 = QWidget(self)
        p2_l = QVBoxLayout(p2)
        p2_title = QLabel("AI Engine Configuration", p2)
        p2_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        p2_desc = QLabel("Enter your Google Gemini API key or configure local Ollama.", p2)

        p2_l.addWidget(p2_title)
        p2_l.addWidget(p2_desc)

        card2 = QFrame(p2)
        card2.setProperty("card", "true")
        card2_l = QVBoxLayout(card2)

        card2_l.addWidget(QLabel("<b>Gemini API Key:</b>", card2))
        self.gemini_input = QLineEdit(card2)
        self.gemini_input.setEchoMode(QLineEdit.Password)
        self.gemini_input.setPlaceholderText("AIzaSy...")
        card2_l.addWidget(self.gemini_input)

        card2_l.addWidget(QLabel("<b>Ollama Local Host:</b>", card2))
        self.ollama_input = QLineEdit(card2)
        self.ollama_input.setText("http://localhost:11434")
        card2_l.addWidget(self.ollama_input)

        p2_l.addWidget(card2)
        p2_l.addStretch()
        self.stack.addWidget(p2)

        # Page 3: Audio Microphone
        p3 = QWidget(self)
        p3_l = QVBoxLayout(p3)
        p3_title = QLabel("Voice & Microphone", p3)
        p3_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        p3_desc = QLabel("Select your default microphone for speech recognition.", p3)
        p3_l.addWidget(p3_title)
        p3_l.addWidget(p3_desc)

        self.mic_combo = QComboBox(p3)
        self.mic_combo.addItem("Default System Microphone")
        try:
            import sounddevice as sd
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    self.mic_combo.addItem(f"{idx}: {dev.get('name')}", idx)
        except Exception:
            pass

        p3_l.addWidget(self.mic_combo)
        p3_l.addStretch()
        self.stack.addWidget(p3)

        # Page 4: Workspace Folder
        p4 = QWidget(self)
        p4_l = QVBoxLayout(p4)
        p4_title = QLabel("Workspace Directory", p4)
        p4_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        p4_desc = QLabel("Choose the project folder where SuperLocal creates and reads files.", p4)
        p4_l.addWidget(p4_title)
        p4_l.addWidget(p4_desc)

        ws_box = QHBoxLayout()
        self.ws_input = QLineEdit(str(WORKSPACE_DIR), p4)
        self.browse_btn = QPushButton("Browse...", p4)
        self.browse_btn.clicked.connect(self._on_browse_workspace)
        ws_box.addWidget(self.ws_input)
        ws_box.addWidget(self.browse_btn)

        p4_l.addLayout(ws_box)
        p4_l.addStretch()
        self.stack.addWidget(p4)

        layout.addWidget(self.stack, stretch=1)

        # Bottom navigation buttons
        btn_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Back", self)
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._on_prev)

        self.next_btn = QPushButton("Next", self)
        self.next_btn.setProperty("accent", "true")
        self.next_btn.clicked.connect(self._on_next)

        btn_layout.addWidget(self.prev_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.next_btn)
        layout.addLayout(btn_layout)

    def _on_browse_workspace(self):
        f = QFileDialog.getExistingDirectory(self, "Select Workspace Folder", self.ws_input.text())
        if f:
            self.ws_input.setText(f)

    def _on_next(self):
        idx = self.stack.currentIndex()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self.prev_btn.setEnabled(True)
            self.step_label.setText(f"Step {idx + 2} of 4")
            if idx + 1 == self.stack.count() - 1:
                self.next_btn.setText("Finish")
        else:
            self._save_and_finish()

    def _on_prev(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self.step_label.setText(f"Step {idx} of 4")
            self.next_btn.setText("Next")
            if idx - 1 == 0:
                self.prev_btn.setEnabled(False)

    def _save_and_finish(self):
        # Save credentials if entered
        key = self.gemini_input.text().strip()
        if key:
            store_credential("gemini", key)

        mark_setup_completed()
        self.setup_finished.emit()
        self.accept()
