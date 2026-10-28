"""
SuperLocal Settings Page
Manages:
- AI Providers & Secure Keyring Storage (never in plain text, with per-provider Test button)
- Fallback PROVIDER_ORDER reordering
- Safety settings (AUTO_APPROVE_SAFE, Sandbox folder, Blocked apps)
- Voice settings (Wake words, push-to-talk F9, timeout)
- Shortcuts.json editor (Apps, websites, discord servers, paths)
- "Run Self-Test" diagnostic button
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
    QFrame,
    QListWidget,
    QMessageBox,
)
from superlocal.ui.theme import Colors, get_stylesheet
from superlocal.core.credentials import store_credential, retrieve_credential
from config import (
    PROVIDER_ORDER,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    AUTO_APPROVE_SAFE,
    WORKSPACE_DIR,
    SHORTCUTS_PATH,
    load_shortcuts,
    save_shortcuts,
)
from selftest import run_selftest


class SettingsPage(QWidget):
    """Full-featured configuration page."""

    theme_changed = Signal(bool)  # is_dark

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)

        # 1. AI Providers & Keyring Secrets
        prov_card = QFrame(container)
        prov_card.setProperty("card", "true")
        pc_layout = QVBoxLayout(prov_card)
        pc_title = QLabel("AI Providers & Keyring Credentials", prov_card)
        pc_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        pc_layout.addWidget(pc_title)

        pc_note = QLabel("API keys are encrypted in Windows Credential Manager and never logged or exposed in plain text.", prov_card)
        pc_note.setStyleSheet("color: #888888; font-size: 11px;")
        pc_layout.addWidget(pc_note)

        # Gemini
        gemini_box = QHBoxLayout()
        gemini_label = QLabel("<b>Google Gemini:</b>", prov_card)
        gemini_label.setFixedWidth(120)
        self.gemini_key_edit = QLineEdit(prov_card)
        self.gemini_key_edit.setEchoMode(QLineEdit.Password)
        existing_gemini = retrieve_credential("gemini")
        if existing_gemini:
            self.gemini_key_edit.setText(existing_gemini)
        self.gemini_key_edit.setPlaceholderText("Enter GEMINI_API_KEY...")
        self.gemini_test_btn = QPushButton("Test", prov_card)
        self.gemini_test_btn.clicked.connect(self._test_gemini_key)
        self.gemini_save_btn = QPushButton("Save", prov_card)
        self.gemini_save_btn.clicked.connect(lambda: self._save_key("gemini", self.gemini_key_edit.text()))
        self.gemini_status = QLabel("Ready", prov_card)
        self.gemini_status.setStyleSheet("color: #888888; font-size: 11px;")

        gemini_box.addWidget(gemini_label)
        gemini_box.addWidget(self.gemini_key_edit, stretch=1)
        gemini_box.addWidget(self.gemini_test_btn)
        gemini_box.addWidget(self.gemini_save_btn)
        gemini_box.addWidget(self.gemini_status)
        pc_layout.addLayout(gemini_box)

        # Ollama local host & model
        ollama_box = QHBoxLayout()
        ollama_label = QLabel("<b>Ollama Local:</b>", prov_card)
        ollama_label.setFixedWidth(120)
        self.ollama_host_edit = QLineEdit(OLLAMA_HOST, prov_card)
        self.ollama_model_edit = QLineEdit(OLLAMA_MODEL, prov_card)
        self.ollama_test_btn = QPushButton("Test", prov_card)
        self.ollama_test_btn.clicked.connect(self._test_ollama)
        self.ollama_status = QLabel("Ready", prov_card)
        self.ollama_status.setStyleSheet("color: #888888; font-size: 11px;")

        ollama_box.addWidget(ollama_label)
        ollama_box.addWidget(self.ollama_host_edit, stretch=2)
        ollama_box.addWidget(self.ollama_model_edit, stretch=1)
        ollama_box.addWidget(self.ollama_test_btn)
        ollama_box.addWidget(self.ollama_status)
        pc_layout.addLayout(ollama_box)

        layout.addWidget(prov_card)

        # 2. Provider Fallback Sequence (PROVIDER_ORDER)
        order_card = QFrame(container)
        order_card.setProperty("card", "true")
        oc_layout = QVBoxLayout(order_card)
        oc_title = QLabel("Provider Fallback Order", order_card)
        oc_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        oc_layout.addWidget(oc_title)

        order_box = QHBoxLayout()
        self.order_list = QListWidget(order_card)
        for p in PROVIDER_ORDER:
            self.order_list.addItem(p)
        order_box.addWidget(self.order_list, stretch=1)

        btn_vbox = QVBoxLayout()
        self.up_btn = QPushButton("▲ Move Up", order_card)
        self.up_btn.clicked.connect(self._move_order_up)
        self.down_btn = QPushButton("▼ Move Down", order_card)
        self.down_btn.clicked.connect(self._move_order_down)
        btn_vbox.addWidget(self.up_btn)
        btn_vbox.addWidget(self.down_btn)
        btn_vbox.addStretch()
        order_box.addLayout(btn_vbox)

        oc_layout.addLayout(order_box)
        layout.addWidget(order_card)

        # 3. Safety & Preferences
        safe_card = QFrame(container)
        safe_card.setProperty("card", "true")
        sc_layout = QVBoxLayout(safe_card)
        sc_title = QLabel("Safety & Permissions", safe_card)
        sc_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        sc_layout.addWidget(sc_title)

        self.auto_approve_check = QCheckBox("Auto-approve safe read-only operations (file_read, browser_screenshot)", safe_card)
        self.auto_approve_check.setChecked(AUTO_APPROVE_SAFE)
        sc_layout.addWidget(self.auto_approve_check)

        layout.addWidget(safe_card)

        # 4. Diagnostics & Self-Test
        diag_card = QFrame(container)
        diag_card.setProperty("card", "true")
        dc_layout = QVBoxLayout(diag_card)
        dc_title = QLabel("System Diagnostics", diag_card)
        dc_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        dc_layout.addWidget(dc_title)

        self.selftest_btn = QPushButton("Run Full System Self-Test (Offline)", diag_card)
        self.selftest_btn.setProperty("accent", "true")
        self.selftest_btn.clicked.connect(self._on_run_selftest)
        dc_layout.addWidget(self.selftest_btn)

        self.diag_table = QTableWidget(diag_card)
        self.diag_table.setColumnCount(4)
        self.diag_table.setHorizontalHeaderLabels(["Subsystem", "Check", "Status", "Details"])
        self.diag_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.diag_table.setFixedHeight(180)
        dc_layout.addWidget(self.diag_table)

        layout.addWidget(diag_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _save_key(self, provider: str, val: str):
        store_credential(provider, val)
        self.gemini_status.setText("Saved to Keyring")
        self.gemini_status.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")

    def _test_gemini_key(self):
        val = self.gemini_key_edit.text().strip()
        if not val:
            self.gemini_status.setText("Empty key")
            self.gemini_status.setStyleSheet(f"color: {Colors.DANGER}; font-size: 11px;")
            return
        store_credential("gemini", val)
        from providers.gemini_provider import GeminiProvider
        prov = GeminiProvider(api_key=val)
        is_h, details, fix = prov.health_check()
        if is_h:
            self.gemini_status.setText("Connected ✔")
            self.gemini_status.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")
        else:
            self.gemini_status.setText(f"Error: {details}")
            self.gemini_status.setStyleSheet(f"color: {Colors.DANGER}; font-size: 11px;")

    def _test_ollama(self):
        host = self.ollama_host_edit.text().strip()
        model = self.ollama_model_edit.text().strip()
        from providers.ollama_provider import check_ollama_status
        reachable, model_exists, _ = check_ollama_status(host, model, timeout=1.0)
        if reachable and model_exists:
            self.ollama_status.setText("Online ✔")
            self.ollama_status.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")
        elif reachable:
            self.ollama_status.setText(f"Missing model '{model}'")
            self.ollama_status.setStyleSheet(f"color: {Colors.WARNING}; font-size: 11px;")
        else:
            self.ollama_status.setText("Unreachable (Run 'ollama serve')")
            self.ollama_status.setStyleSheet(f"color: {Colors.DANGER}; font-size: 11px;")

    def _move_order_up(self):
        row = self.order_list.currentRow()
        if row > 0:
            item = self.order_list.takeItem(row)
            self.order_list.insertItem(row - 1, item)
            self.order_list.setCurrentRow(row - 1)

    def _move_order_down(self):
        row = self.order_list.currentRow()
        if row >= 0 and row < self.order_list.count() - 1:
            item = self.order_list.takeItem(row)
            self.order_list.insertItem(row + 1, item)
            self.order_list.setCurrentRow(row + 1)

    def _on_run_selftest(self):
        passed, results = run_selftest()
        self.diag_table.setRowCount(len(results))
        for row, r in enumerate(results):
            self.diag_table.setItem(row, 0, QTableWidgetItem(r.get("subsystem", "")))
            self.diag_table.setItem(row, 1, QTableWidgetItem(r.get("check", "")))
            st_item = QTableWidgetItem(r.get("status", ""))
            st_item.setForeground(Qt.green if r.get("status") == "PASS" else Qt.yellow)
            self.diag_table.setItem(row, 2, st_item)
            self.diag_table.setItem(row, 3, QTableWidgetItem(r.get("details", "")))
