"""
SuperLocal Chat Page
Features:
- Message bubbles with user/assistant distinct styling and copy button
- Multi-line text input (Enter to send, Shift+Enter for newline)
- Attachment button (opens file picker, appends path)
- Mic button (quick voice trigger)
- Slash-command autocomplete palette popup when typing '/'
- Rich Markdown rendering & code block styling
"""

import time
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QScrollArea,
    QFrame,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QApplication,
)
from superlocal.ui.theme import Colors


class ChatMessageBubble(QFrame):
    """Rendered message bubble (User or Assistant)."""

    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        self.role = role
        self.text_content = text

        self.setProperty("card", "true")
        is_user = (role == "user")

        bg_color = Colors.ACCENT if is_user else "rgba(255, 255, 255, 0.05)"
        border_color = Colors.ACCENT if is_user else "rgba(255, 255, 255, 0.1)"
        align_margin = (120, 0) if is_user else (0, 120)

        self.setStyleSheet(f"""
            QFrame[card="true"] {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 10px;
                padding: 10px 14px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header with role & copy button
        header = QHBoxLayout()
        header_text = "You" if is_user else "SuperLocal"
        role_label = QLabel(f"<b>{header_text}</b>", self)
        role_label.setStyleSheet("font-size: 11px; opacity: 0.8;")
        header.addWidget(role_label)
        header.addStretch()

        if not is_user:
            self.copy_btn = QPushButton("📋 Copy", self)
            self.copy_btn.setFixedHeight(22)
            self.copy_btn.setCursor(Qt.PointingHandCursor)
            self.copy_btn.setStyleSheet("font-size: 10px; padding: 2px 6px;")
            self.copy_btn.clicked.connect(self._copy_to_clipboard)
            header.addWidget(self.copy_btn)

        layout.addLayout(header)

        # Body label (supports HTML / Markdown formatting)
        self.body_label = QLabel(self)
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.MarkdownText)
        self.body_label.setText(text)
        self.body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.body_label)

    def _copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_content)
        if hasattr(self, "copy_btn"):
            self.copy_btn.setText("✔ Copied")


class ChatInputEdit(QTextEdit):
    """Text editor intercepting Enter to send and Shift+Enter for new line."""

    send_requested = Signal()
    slash_typed = Signal(str)
    slash_navigated = Signal(int)  # 1 for down, -1 for up, 0 for select

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
                event.accept()
                return

        super().keyPressEvent(event)

        # Check for slash commands
        text = self.toPlainText().strip()
        if text.startswith("/"):
            self.slash_typed.emit(text)
        else:
            self.slash_typed.emit("")


class ChatPage(QWidget):
    """Main Chat conversation view with slash palette and controls."""

    submit_prompt = Signal(str)
    voice_toggle_requested = Signal()

    SLASH_COMMANDS = [
        ("/help", "Show all capabilities and quick command guide"),
        ("/health", "Test connectivity of AI providers and models"),
        ("/selftest", "Run fast offline diagnostic across all modules"),
        ("/quota", "View daily request counters and limits"),
        ("/provider", "Show active provider or switch provider (/provider <name>)"),
        ("/models", "List installed and available local Ollama models"),
        ("/auto", "Run an end-to-end autonomous goal (/auto <goal>)"),
        ("/computer", "Run @computer operator agent with sandboxing"),
        ("/poki", "Play browser game (/poki play <game>)"),
        ("/openfront", "Run local OpenFront RTS agent (/openfront play)"),
        ("/optimize", "PC Optimizer scan, clean, and disk diagnostics"),
        ("/stop", "Trigger immediate emergency stop (also Ctrl+Alt+Q)"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # 1. Scrollable Messages Area
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(10, 10, 10, 10)
        self.messages_layout.setSpacing(12)
        self.messages_layout.addStretch()
        self.scroll.setWidget(self.messages_container)

        main_layout.addWidget(self.scroll, stretch=1)

        # 2. Slash-Command Palette Popup (Overlay Card)
        self.palette = QListWidget(self)
        self.palette.setFixedHeight(160)
        self.palette.setStyleSheet("""
            QListWidget {
                background-color: rgba(30, 30, 30, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 4px;
            }
            QListWidget::item:hover, QListWidget::item:selected {
                background-color: #0078D4;
                color: #FFFFFF;
            }
        """)
        self.palette.hide()
        self.palette.itemClicked.connect(self._on_palette_item_clicked)
        main_layout.addWidget(self.palette)

        # 3. Input Controls Bar
        input_card = QFrame(self)
        input_card.setProperty("card", "true")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(6)

        self.editor = ChatInputEdit(input_card)
        self.editor.setFixedHeight(64)
        self.editor.setPlaceholderText("Ask SuperLocal anything, or type '/' for commands (Enter to send, Shift+Enter for new line)...")
        self.editor.send_requested.connect(self._on_send_clicked)
        self.editor.slash_typed.connect(self._on_slash_typed)

        input_layout.addWidget(self.editor)

        # Buttons toolbar under editor
        tools_layout = QHBoxLayout()
        tools_layout.setContentsMargins(4, 0, 4, 0)
        tools_layout.setSpacing(8)

        self.attach_btn = QPushButton("📎 Attach", input_card)
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setToolTip("Attach file or image path")
        self.attach_btn.clicked.connect(self._on_attach_clicked)

        self.mic_btn = QPushButton("🎙️ Mic", input_card)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setToolTip("Voice Mode")
        self.mic_btn.clicked.connect(self.voice_toggle_requested.emit)

        self.send_btn = QPushButton("Send ➤", input_card)
        self.send_btn.setProperty("accent", "true")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send_clicked)

        tools_layout.addWidget(self.attach_btn)
        tools_layout.addWidget(self.mic_btn)
        tools_layout.addStretch()
        tools_layout.addWidget(self.send_btn)

        input_layout.addLayout(tools_layout)
        main_layout.addWidget(input_card)

        # Add initial welcome greeting
        self.add_message("assistant", "👋 Hello! I am **SuperLocal**, your Windows AI assistant. How can I help you today?")

    def add_message(self, role: str, text: str):
        bubble = ChatMessageBubble(role, text, self.messages_container)
        # Insert before stretch
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        # Scroll to bottom
        QTimer_single = getattr(self, "_scroll_timer", None)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _on_send_clicked(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        self.palette.hide()
        self.editor.clear()
        self.submit_prompt.emit(text)

    def _on_attach_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Attach File or Image")
        if file_path:
            curr_text = self.editor.toPlainText()
            separator = " " if curr_text and not curr_text.endswith(" ") else ""
            self.editor.setPlainText(f"{curr_text}{separator}{file_path} ")
            self.editor.moveCursor(self.editor.textCursor().End)

    def _on_slash_typed(self, prefix: str):
        if not prefix or not prefix.startswith("/"):
            self.palette.hide()
            return

        self.palette.clear()
        q = prefix.lower()
        matches = [cmd for cmd in self.SLASH_COMMANDS if cmd[0].lower().startswith(q) or q in cmd[0].lower()]

        if not matches:
            self.palette.hide()
            return

        for cmd, desc in matches:
            item = QListWidgetItem(f"{cmd}  —  {desc}")
            item.setData(Qt.UserRole, cmd)
            self.palette.addItem(item)

        self.palette.setCurrentRow(0)
        self.palette.show()

    def _on_palette_item_clicked(self, item: QListWidgetItem):
        cmd = item.data(Qt.UserRole)
        if cmd:
            self.editor.setPlainText(f"{cmd} ")
            self.editor.moveCursor(self.editor.textCursor().End)
        self.palette.hide()
        self.editor.setFocus()
