"""
SuperLocal PC Optimizer Page
Autonomous diagnostics and optimization workbench:
- System Health Score (0-100) and Metrics Gauges (CPU, RAM, Disk)
- Key Findings & Recommendations
- Safe Clean Preview with Category Checkboxes (Temp files, Caches, Recycle Bin)
- Startup Applications Manager
- Scan, Clean, and Undo buttons
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QScrollArea,
    QFrame,
    QMessageBox,
)
from superlocal.ui.theme import Colors


class OptimizerPage(QWidget):
    """PC Optimizer and system health management page."""

    scan_requested = Signal()
    clean_requested = Signal(list)  # categories
    undo_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)

        # 1. Header & Quick Action Buttons
        header_card = QFrame(container)
        header_card.setProperty("card", "true")
        hc_layout = QHBoxLayout(header_card)

        v_head = QVBoxLayout()
        title = QLabel("PC Optimizer Workbench", header_card)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        subtitle = QLabel("Safe, transparent Windows optimization powered by PowerShell & psutil.", header_card)
        subtitle.setStyleSheet("color: #888888; font-size: 11px;")
        v_head.addWidget(title)
        v_head.addWidget(subtitle)
        hc_layout.addLayout(v_head, stretch=1)

        self.scan_btn = QPushButton("🔍 Run System Scan", header_card)
        self.scan_btn.setProperty("accent", "true")
        self.scan_btn.clicked.connect(self._on_scan_clicked)

        self.clean_btn = QPushButton("🧹 Clean Selected", header_card)
        self.clean_btn.clicked.connect(self._on_clean_clicked)

        self.undo_btn = QPushButton("↩ Undo Clean", header_card)
        self.undo_btn.setStyleSheet(f"color: {Colors.WARNING}; font-weight: bold;")
        self.undo_btn.clicked.connect(self.undo_requested.emit)

        hc_layout.addWidget(self.scan_btn)
        hc_layout.addWidget(self.clean_btn)
        hc_layout.addWidget(self.undo_btn)
        layout.addWidget(header_card)

        # 2. Score & Gauges Dashboard
        gauges_card = QFrame(container)
        gauges_card.setProperty("card", "true")
        gc_layout = QHBoxLayout(gauges_card)
        gc_layout.setSpacing(20)

        # Health Score Box
        score_box = QVBoxLayout()
        score_title = QLabel("PC HEALTH SCORE", gauges_card)
        score_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #888888;")
        self.score_label = QLabel("88 / 100", gauges_card)
        self.score_label.setStyleSheet("font-size: 32px; font-weight: 800; color: #107C41;")
        score_box.addWidget(score_title)
        score_box.addWidget(self.score_label)
        gc_layout.addLayout(score_box)

        # CPU Gauge
        cpu_box = QVBoxLayout()
        self.cpu_lbl = QLabel("CPU Load: 18%", gauges_card)
        self.cpu_bar = QProgressBar(gauges_card)
        self.cpu_bar.setValue(18)
        self.cpu_bar.setFixedHeight(8)
        self.cpu_bar.setTextVisible(False)
        cpu_box.addWidget(self.cpu_lbl)
        cpu_box.addWidget(self.cpu_bar)
        gc_layout.addLayout(cpu_box, stretch=1)

        # RAM Gauge
        ram_box = QVBoxLayout()
        self.ram_lbl = QLabel("RAM Usage: 42%", gauges_card)
        self.ram_bar = QProgressBar(gauges_card)
        self.ram_bar.setValue(42)
        self.ram_bar.setFixedHeight(8)
        self.ram_bar.setTextVisible(False)
        ram_box.addWidget(self.ram_lbl)
        ram_box.addWidget(self.ram_bar)
        gc_layout.addLayout(ram_box, stretch=1)

        # Disk Gauge
        disk_box = QVBoxLayout()
        self.disk_lbl = QLabel("Disk C: 64% used", gauges_card)
        self.disk_bar = QProgressBar(gauges_card)
        self.disk_bar.setValue(64)
        self.disk_bar.setFixedHeight(8)
        self.disk_bar.setTextVisible(False)
        disk_box.addWidget(self.disk_lbl)
        disk_box.addWidget(self.disk_bar)
        gc_layout.addLayout(disk_box, stretch=1)

        layout.addWidget(gauges_card)

        # 3. Clean Preview Table with Checkboxes
        clean_card = QFrame(container)
        clean_card.setProperty("card", "true")
        cc_layout = QVBoxLayout(clean_card)

        cc_title = QLabel("Cleanable Space Preview (Aged > 7 Days)", clean_card)
        cc_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        cc_layout.addWidget(cc_title)

        self.clean_table = QTableWidget(clean_card)
        self.clean_table.setColumnCount(4)
        self.clean_table.setHorizontalHeaderLabels(["Select", "Category", "Size", "Safety Level"])
        self.clean_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.clean_table.setFixedHeight(180)

        clean_items = [
            ("User Temp Files", "1.2 GB", "Safe (Aged > 7d)"),
            ("Windows System Temp", "480 MB", "Safe (Aged > 7d)"),
            ("Browser Cache (Chrome / Edge)", "850 MB", "Safe (Cache only, preserves logins)"),
            ("Thumbnail Cache", "120 MB", "Safe"),
            ("Recycle Bin", "2.4 GB", "Requires Confirmation"),
        ]
        self.clean_table.setRowCount(len(clean_items))
        self.category_checkboxes = []

        for row, (cat, sz, sf) in enumerate(clean_items):
            cb = QCheckBox(clean_card)
            cb.setChecked(True)
            self.category_checkboxes.append((cb, cat))
            self.clean_table.setCellWidget(row, 0, cb)
            self.clean_table.setItem(row, 1, QTableWidgetItem(cat))
            self.clean_table.setItem(row, 2, QTableWidgetItem(sz))
            sf_item = QTableWidgetItem(sf)
            sf_item.setForeground(Qt.green if "Safe" in sf else Qt.yellow)
            self.clean_table.setItem(row, 3, sf_item)

        cc_layout.addWidget(self.clean_table)
        layout.addWidget(clean_card)

        # 4. Startup Items Table
        startup_card = QFrame(container)
        startup_card.setProperty("card", "true")
        sc_layout = QVBoxLayout(startup_card)

        sc_title = QLabel("Startup Programs Impact", startup_card)
        sc_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        sc_layout.addWidget(sc_title)

        self.startup_table = QTableWidget(startup_card)
        self.startup_table.setColumnCount(4)
        self.startup_table.setHorizontalHeaderLabels(["Name", "Publisher", "Impact", "Status"])
        self.startup_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.startup_table.setFixedHeight(160)

        startup_items = [
            ("Microsoft OneDrive", "Microsoft Corporation", "Medium", "Enabled"),
            ("Discord", "Discord Inc.", "High", "Enabled"),
            ("Spotify", "Spotify AB", "Medium", "Enabled"),
            ("Steam Client Bootstrapper", "Valve Corp.", "High", "Disabled"),
        ]
        self.startup_table.setRowCount(len(startup_items))
        for row, s in enumerate(startup_items):
            for col in range(4):
                self.startup_table.setItem(row, col, QTableWidgetItem(s[col]))

        sc_layout.addWidget(self.startup_table)
        layout.addWidget(startup_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _on_scan_clicked(self):
        self.scan_requested.emit()
        try:
            from optimizer.scanner import run_system_scan
            res = run_system_scan()
            score = res.get("score", 90)
            self.score_label.setText(f"{score} / 100")
            cpu = int(res.get("cpu_percent", 20))
            self.cpu_bar.setValue(cpu)
            self.cpu_lbl.setText(f"CPU Load: {cpu}%")
            ram = int(res.get("ram_percent", 45))
            self.ram_bar.setValue(ram)
            self.ram_lbl.setText(f"RAM Usage: {ram}%")
        except Exception:
            pass

    def _on_clean_clicked(self):
        selected = [cat for cb, cat in self.category_checkboxes if cb.isChecked()]
        if selected:
            self.clean_requested.emit(selected)
