"""
SuperLocal Games Workbench
Combines:
1. Poki Player:
   - Single-player browser game launcher
   - Skills selector (Cricket, Subway Surfers, etc.)
   - Play / Stop controls
   - Stats table (scores, runs, success rate)
   - Strict single-player safety banner
2. OpenFront RTS Local Workbench:
   - Local RTS bot runner
   - Enforced localhost-only guard (strictly blocks public matches)
   - Structured state perception viewer (territory, population, gold, enemies)
   - Decision strategy mode selector
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QTabWidget,
    QTextEdit,
)
from superlocal.ui.theme import Colors


class GamesPage(QWidget):
    """Games workbench for Poki Player and OpenFront."""

    play_poki_requested = Signal(str, str)  # game_name, goal
    stop_poki_requested = Signal()
    run_openfront_requested = Signal(str, str)  # server_url, strategy

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Tab widget separating Poki and OpenFront
        self.tabs = QTabWidget(self)

        # TAB 1: Poki Player
        poki_tab = QWidget()
        pt_layout = QVBoxLayout(poki_tab)
        pt_layout.setSpacing(12)

        # Safety Notice Banner
        poki_notice = QFrame(poki_tab)
        poki_notice.setStyleSheet(f"background-color: {Colors.SURFACE}; border-left: 4px solid {Colors.INFO}; border-radius: 4px; padding: 6px;")
        pn_layout = QVBoxLayout(poki_notice)
        pn_lbl = QLabel(
            "<b>Single-Player Policy:</b> SuperLocal plays only single-player browser games on poki.com. "
            "Multiplayer games and PvP leaderboards are strictly refused.",
            poki_notice
        )
        pn_lbl.setStyleSheet("font-size: 11px; color: #CCCCCC;")
        pn_layout.addWidget(pn_lbl)
        pt_layout.addWidget(poki_notice)

        # Controls Card
        poki_card = QFrame(poki_tab)
        poki_card.setProperty("card", "true")
        pc_layout = QVBoxLayout(poki_card)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("<b>Game:</b>", poki_card))
        self.game_combo = QComboBox(poki_card)
        self.game_combo.addItems(["Cricket", "Subway Surfers", "Monkey Mart", "Drive Mad", "Retro Bowl", "Custom URL..."])
        row1.addWidget(self.game_combo, stretch=1)

        row1.addWidget(QLabel("<b>Goal:</b>", poki_card))
        self.goal_edit = QLineEdit(poki_card)
        self.goal_edit.setPlaceholderText("e.g. score 2000, finish level 5, play 10 min")
        row1.addWidget(self.goal_edit, stretch=2)

        self.play_btn = QPushButton("▶ Launch Game", poki_card)
        self.play_btn.setProperty("accent", "true")
        self.play_btn.clicked.connect(self._on_play_poki)

        self.stop_btn = QPushButton("⏹ Stop", poki_card)
        self.stop_btn.setStyleSheet(f"background-color: {Colors.DANGER}; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_poki_requested.emit)

        row1.addWidget(self.play_btn)
        row1.addWidget(self.stop_btn)
        pc_layout.addLayout(row1)

        pt_layout.addWidget(poki_card)

        # Stats & Performance Table
        stats_label = QLabel("<b>Poki Player Stats & History</b>", poki_tab)
        pt_layout.addWidget(stats_label)

        self.stats_table = QTableWidget(poki_tab)
        self.stats_table.setColumnCount(5)
        self.stats_table.setHorizontalHeaderLabels(["Game", "Runs", "Best Score", "Avg FPS", "Success Rate"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setRowCount(4)

        sample_stats = [
            ("Cricket", "12", "142 runs", "30 FPS", "91%"),
            ("Subway Surfers", "8", "3,420 pts", "28 FPS", "85%"),
            ("Drive Mad", "15", "Level 14", "30 FPS", "100%"),
            ("Monkey Mart", "4", "Cash 450", "30 FPS", "80%"),
        ]
        for row, s in enumerate(sample_stats):
            for col in range(5):
                self.stats_table.setItem(row, col, QTableWidgetItem(s[col]))

        pt_layout.addWidget(self.stats_table, stretch=1)
        self.tabs.addTab(poki_tab, "🎮 Poki Browser Games")

        # TAB 2: OpenFront RTS Local Workbench
        of_tab = QWidget()
        of_layout = QVBoxLayout(of_tab)
        of_layout.setSpacing(12)

        # Guard Card
        of_guard = QFrame(of_tab)
        of_guard.setStyleSheet(f"background-color: {Colors.SURFACE}; border-left: 4px solid {Colors.WARNING}; border-radius: 4px; padding: 8px;")
        og_layout = QVBoxLayout(of_guard)
        og_title = QLabel("🛡️ Localhost Training Policy", of_guard)
        og_title.setStyleSheet(f"color: {Colors.WARNING}; font-weight: bold; font-size: 13px;")
        og_desc = QLabel(
            "OpenFront skill operates STRICTLY on local bot instances (e.g. http://localhost:8080). "
            "Connecting to public multiplayer servers is blocked by architectural guardrails to prevent unfair play.",
            of_guard
        )
        og_desc.setStyleSheet("font-size: 11px; color: #DDDDDD;")
        og_layout.addWidget(og_title)
        og_layout.addWidget(og_desc)
        of_layout.addWidget(of_guard)

        # OpenFront Controls
        of_card = QFrame(of_tab)
        of_card.setProperty("card", "true")
        oc_layout = QHBoxLayout(of_card)

        oc_layout.addWidget(QLabel("<b>Server URL:</b>", of_card))
        self.of_url_input = QLineEdit("http://localhost:8080", of_card)
        oc_layout.addWidget(self.of_url_input, stretch=1)

        oc_layout.addWidget(QLabel("<b>Strategy:</b>", of_card))
        self.of_strategy_combo = QComboBox(of_card)
        self.of_strategy_combo.addItems([
            "Early Expansion (Gold & Ports)",
            "Military Buildup (Factories & Defense)",
            "Strategic Nukes End-Game",
        ])
        oc_layout.addWidget(self.of_strategy_combo)

        self.of_start_btn = QPushButton("▶ Connect & Train", of_card)
        self.of_start_btn.setProperty("accent", "true")
        self.of_start_btn.clicked.connect(self._on_run_openfront)
        oc_layout.addWidget(self.of_start_btn)

        of_layout.addWidget(of_card)

        # Structured State Display
        state_label = QLabel("<b>Structured Perception State (No Screen OCR Required)</b>", of_tab)
        of_layout.addWidget(state_label)

        self.state_text = QTextEdit(of_tab)
        self.state_text.setReadOnly(True)
        self.state_text.setText(
            "{\n"
            "  \"territory\": 42,\n"
            "  \"population\": 1850,\n"
            "  \"gold\": 4200,\n"
            "  \"production\": {\"ports\": 2, \"factories\": 3},\n"
            "  \"military\": {\"tanks\": 14, \"infantry\": 60},\n"
            "  \"nearby_enemies\": [\n"
            "    {\"id\": \"bot_blue\", \"distance\": 12, \"strength\": \"low\"}\n"
            "  ],\n"
            "  \"next_action\": \"expand(direction='north_east', units=20)\"\n"
            "}"
        )
        of_layout.addWidget(self.state_text, stretch=1)

        self.tabs.addTab(of_tab, "⚔️ OpenFront RTS (Localhost)")

        main_layout.addWidget(self.tabs)

    def _on_play_poki(self):
        game = self.game_combo.currentText()
        goal = self.goal_edit.text().strip()
        self.play_poki_requested.emit(game, goal)

    def _on_run_openfront(self):
        url = self.of_url_input.text().strip()
        strat = self.of_strategy_combo.currentText()
        self.run_openfront_requested.emit(url, strat)
