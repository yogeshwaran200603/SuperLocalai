"""
SuperLocal Skills & Tools Page
Manages:
- Available tools and capabilities (shell, browser, file, poki, optimizer)
- MCP (Model Context Protocol) servers
- Macro recorder (record keyboard/mouse sequences, name, and replay)
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QScrollArea,
)
from superlocal.ui.theme import Colors


class SkillsPage(QWidget):
    """Skills, Tools, MCP servers, and Macro recorder page."""

    record_macro_toggled = Signal(bool)  # is_recording
    save_macro_requested = Signal(str)   # macro_name

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)

        # 1. Macro Recorder Card
        macro_card = QFrame(container)
        macro_card.setProperty("card", "true")
        mc_layout = QVBoxLayout(macro_card)

        mc_title = QLabel("Desktop Macro Recorder", macro_card)
        mc_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        mc_layout.addWidget(mc_title)

        mc_desc = QLabel("Record human operator actions (clicks, keypresses) into reusable local skills.", macro_card)
        mc_desc.setStyleSheet("color: #888888; font-size: 11px;")
        mc_layout.addWidget(mc_desc)

        m_bar = QHBoxLayout()
        self.macro_name_input = QLineEdit(macro_card)
        self.macro_name_input.setPlaceholderText("Enter macro name (e.g. 'export_monthly_excel')")
        m_bar.addWidget(self.macro_name_input, stretch=2)

        self.record_btn = QPushButton("⏺ Record Macro", macro_card)
        self.record_btn.setStyleSheet(f"background-color: {Colors.DANGER}; font-weight: bold;")
        self.record_btn.clicked.connect(self._toggle_recording)
        m_bar.addWidget(self.record_btn)

        self.save_macro_btn = QPushButton("💾 Save Skill", macro_card)
        self.save_macro_btn.clicked.connect(self._save_macro)
        m_bar.addWidget(self.save_macro_btn)

        mc_layout.addLayout(m_bar)
        self.record_status = QLabel("Status: Idle", macro_card)
        self.record_status.setStyleSheet("color: #888888; font-size: 11px;")
        mc_layout.addWidget(self.record_status)

        layout.addWidget(macro_card)

        # 2. Core Tools & Capabilities Table
        tools_card = QFrame(container)
        tools_card.setProperty("card", "true")
        tc_layout = QVBoxLayout(tools_card)

        tc_title = QLabel("Active Built-in Tools", tools_card)
        tc_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        tc_layout.addWidget(tc_title)

        self.tools_table = QTableWidget(tools_card)
        self.tools_table.setColumnCount(4)
        self.tools_table.setHorizontalHeaderLabels(["Tool", "Category", "Risk Level", "Description"])
        self.tools_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tools_table.setFixedHeight(180)

        tools = [
            ("shell_exec", "System", "High", "Execute safe Windows PowerShell scripts"),
            ("file_read / file_write", "Filesystem", "Medium", "Safe workspace file read and write operations"),
            ("browser_open / click", "Playwright", "Low", "DOM-based browser automation"),
            ("poki_player", "Games", "Low", "Canvas-driven single-player Poki gaming"),
            ("openfront_rts", "Games", "Low", "Localhost RTS bot perception and action engine"),
            ("pc_optimizer", "Maintenance", "Low", "psutil and WMI system scan and cleaning"),
        ]
        self.tools_table.setRowCount(len(tools))
        for row, t in enumerate(tools):
            for col in range(4):
                item = QTableWidgetItem(t[col])
                if col == 2:
                    item.setForeground(Qt.red if t[2] == "High" else (Qt.yellow if t[2] == "Medium" else Qt.green))
                self.tools_table.setItem(row, col, item)

        tc_layout.addWidget(self.tools_table)
        layout.addWidget(tools_card)

        # 3. Model Context Protocol (MCP) Servers
        mcp_card = QFrame(container)
        mcp_card.setProperty("card", "true")
        mp_layout = QVBoxLayout(mcp_card)

        mp_title = QLabel("Model Context Protocol (MCP) Servers", mcp_card)
        mp_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        mp_layout.addWidget(mp_title)

        self.mcp_table = QTableWidget(mcp_card)
        self.mcp_table.setColumnCount(4)
        self.mcp_table.setHorizontalHeaderLabels(["Server", "Transport", "Status", "Command"])
        self.mcp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.mcp_table.setFixedHeight(140)

        mcp_servers = [
            ("filesystem-mcp", "stdio", "Active", "npx @modelcontextprotocol/server-filesystem C:\\astra_workspace"),
            ("git-mcp", "stdio", "Active", "mcp-server-git --repository ."),
            ("sqlite-mcp", "stdio", "Standby", "mcp-server-sqlite --db data/astra_memory.db"),
        ]
        self.mcp_table.setRowCount(len(mcp_servers))
        for row, s in enumerate(mcp_servers):
            for col in range(4):
                item = QTableWidgetItem(s[col])
                if col == 2:
                    item.setForeground(Qt.green if s[2] == "Active" else Qt.gray)
                self.mcp_table.setItem(row, col, item)

        mp_layout.addWidget(self.mcp_table)
        layout.addWidget(mcp_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self._is_recording = False

    def _toggle_recording(self):
        self._is_recording = not self._is_recording
        if self._is_recording:
            self.record_btn.setText("⏹ Stop Recording")
            self.record_status.setText("Status: Recording operator actions... (clicks, keys)")
            self.record_status.setStyleSheet(f"color: {Colors.DANGER}; font-weight: bold;")
        else:
            self.record_btn.setText("⏺ Record Macro")
            self.record_status.setText("Status: Recording stopped. Enter skill name and click Save.")
            self.record_status.setStyleSheet("color: #888888;")
        self.record_macro_toggled.emit(self._is_recording)

    def _save_macro(self):
        name = self.macro_name_input.text().strip()
        if name:
            self.save_macro_requested.emit(name)
            self.record_status.setText(f"Skill '{name}' saved successfully to skills/custom/")
            self.record_status.setStyleSheet(f"color: {Colors.SUCCESS}; font-weight: bold;")
