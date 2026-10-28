"""
SuperLocal Tasks Page (Autopilot Workbench)
Full management for Autopilot jobs:
- Goal launcher (/auto <goal> and --dry)
- Jobs list (past and current)
- Step plan viewer (step id, tool, description, risk, checkpoint)
- Execution log / REPORT.md viewer
- Action buttons: Run, Dry Run, Pause, Stop, Undo, Open in VS Code
"""

import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTextEdit,
    QSplitter,
    QFrame,
    QMessageBox,
)
from superlocal.ui.theme import Colors


class TasksPage(QWidget):
    """Autopilot jobs control page."""

    run_goal_requested = Signal(str, bool)  # goal, is_dry_run
    undo_requested = Signal(str)            # job_id

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header & Launcher Card
        launcher_card = QFrame(self)
        launcher_card.setProperty("card", "true")
        lc_layout = QVBoxLayout(launcher_card)

        title = QLabel("Autopilot Task Execution", launcher_card)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        lc_layout.addWidget(title)

        input_box = QHBoxLayout()
        self.goal_input = QLineEdit(launcher_card)
        self.goal_input.setPlaceholderText("Enter goal (e.g. 'build a portfolio website with dark mode and a contact form')")
        self.goal_input.returnPressed.connect(self._on_run_goal)

        self.run_btn = QPushButton("🚀 Run End-to-End", launcher_card)
        self.run_btn.setProperty("accent", "true")
        self.run_btn.clicked.connect(self._on_run_goal)

        self.dry_btn = QPushButton("📋 Dry Run (Plan Only)", launcher_card)
        self.dry_btn.clicked.connect(self._on_dry_run)

        input_box.addWidget(self.goal_input, stretch=1)
        input_box.addWidget(self.run_btn)
        input_box.addWidget(self.dry_btn)
        lc_layout.addLayout(input_box)

        main_layout.addWidget(launcher_card)

        # Splitter: Left (Jobs list & Plan), Right (Report & Logs)
        splitter = QSplitter(Qt.Horizontal, self)

        # Left Container
        left_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Past Jobs Table
        jobs_label = QLabel("<b>Past & Active Jobs</b>", left_widget)
        left_layout.addWidget(jobs_label)

        self.jobs_table = QTableWidget(left_widget)
        self.jobs_table.setColumnCount(4)
        self.jobs_table.setHorizontalHeaderLabels(["Job ID", "Goal", "Status", "Steps"])
        self.jobs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.jobs_table.setSelectionMode(QTableWidget.SingleSelection)
        self.jobs_table.itemSelectionChanged.connect(self._on_job_selected)
        left_layout.addWidget(self.jobs_table, stretch=1)

        # Plan Viewer
        plan_label = QLabel("<b>Execution Plan & Steps</b>", left_widget)
        left_layout.addWidget(plan_label)

        self.plan_table = QTableWidget(left_widget)
        self.plan_table.setColumnCount(4)
        self.plan_table.setHorizontalHeaderLabels(["#", "Tool", "Description", "Status"])
        self.plan_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        left_layout.addWidget(self.plan_table, stretch=1)

        splitter.addWidget(left_widget)

        # Right Container (Logs & Report)
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        report_label = QLabel("<b>Job Details & REPORT.md</b>", right_widget)
        right_layout.addWidget(report_label)

        self.report_viewer = QTextEdit(right_widget)
        self.report_viewer.setReadOnly(True)
        self.report_viewer.setPlaceholderText("Select a job or execute a goal to view the generated plan, live execution log, and final summary report...")
        right_layout.addWidget(self.report_viewer, stretch=1)

        # Job Action Bar
        act_box = QHBoxLayout()
        self.undo_btn = QPushButton("↩ Undo Job Changes", right_widget)
        self.undo_btn.setStyleSheet(f"color: {Colors.DANGER}; font-weight: bold;")
        self.undo_btn.clicked.connect(self._on_undo_clicked)

        self.open_vscode_btn = QPushButton("📂 Open in VS Code", right_widget)
        self.open_vscode_btn.clicked.connect(self._on_open_vscode)

        self.refresh_btn = QPushButton("🔄 Refresh Jobs", right_widget)
        self.refresh_btn.clicked.connect(self.load_jobs)

        act_box.addWidget(self.undo_btn)
        act_box.addWidget(self.open_vscode_btn)
        act_box.addStretch()
        act_box.addWidget(self.refresh_btn)
        right_layout.addLayout(act_box)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)
        main_layout.addWidget(splitter, stretch=1)

        # Initial jobs scan
        self.load_jobs()

    def _on_run_goal(self):
        text = self.goal_input.text().strip()
        if text:
            self.run_goal_requested.emit(text, False)

    def _on_dry_run(self):
        text = self.goal_input.text().strip()
        if text:
            self.run_goal_requested.emit(text, True)

    def _on_undo_clicked(self):
        row = self.jobs_table.currentRow()
        if row >= 0:
            job_id = self.jobs_table.item(row, 0).text()
            self.undo_requested.emit(job_id)

    def _on_open_vscode(self):
        row = self.jobs_table.currentRow()
        if row >= 0:
            ws_item = self.jobs_table.item(row, 0)
            if ws_item:
                import subprocess
                subprocess.Popen(["code", f"jobs/{ws_item.text()}"], shell=True)

    def load_jobs(self):
        """Scans jobs/ folder for past jobs."""
        self.jobs_table.setRowCount(0)
        jobs_dir = Path("jobs")
        if not jobs_dir.exists():
            return

        job_folders = sorted([d for d in jobs_dir.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
        self.jobs_table.setRowCount(len(job_folders))

        for row, f in enumerate(job_folders):
            job_id = f.name
            report_file = f / "REPORT.md"
            status = "Completed" if report_file.exists() else "Active"

            self.jobs_table.setItem(row, 0, QTableWidgetItem(job_id))
            self.jobs_table.setItem(row, 1, QTableWidgetItem(job_id.replace("-", " ")))
            st_item = QTableWidgetItem(status)
            st_item.setForeground(Qt.green if status == "Completed" else Qt.cyan)
            self.jobs_table.setItem(row, 2, st_item)
            self.jobs_table.setItem(row, 3, QTableWidgetItem("N/A"))

    def _on_job_selected(self):
        row = self.jobs_table.currentRow()
        if row >= 0:
            job_id = self.jobs_table.item(row, 0).text()
            report_path = Path("jobs") / job_id / "REPORT.md"
            log_path = Path("jobs") / job_id / "logs" / "execution.log"
            content = ""
            if report_path.exists():
                content += f"=== REPORT.md ===\n{report_path.read_text(encoding='utf-8', errors='ignore')}\n\n"
            if log_path.exists():
                content += f"=== LOGS ===\n{log_path.read_text(encoding='utf-8', errors='ignore')}\n"
            if not content:
                content = f"Job {job_id} selected. No report or logs generated yet."
            self.report_viewer.setText(content)
