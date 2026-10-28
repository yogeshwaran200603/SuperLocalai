"""
Tests for SuperLocal Stage 5: Tasks, Games, Optimizer, Skills, and History Pages
"""

import os
import pytest
from pathlib import Path

# Force offscreen Qt platform before creating QApplication
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from superlocal.ui.pages.tasks_page import TasksPage
from superlocal.ui.pages.games_page import GamesPage
from superlocal.ui.pages.optimizer_page import OptimizerPage
from superlocal.ui.pages.skills_page import SkillsPage
from superlocal.ui.pages.history_page import HistoryPage
from superlocal.ui.main_window import SuperLocalMainWindow
from core.engine import SuperLocalEngine


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_tasks_page_signals(qapp, qtbot):
    """Test TasksPage run and dry-run goal signals."""
    page = TasksPage()
    qtbot.addWidget(page)

    page.goal_input.setText("build a todo app")
    with qtbot.waitSignal(page.run_goal_requested, timeout=1000) as blocker:
        page.run_btn.click()
    assert blocker.args == ["build a todo app", False]

    with qtbot.waitSignal(page.run_goal_requested, timeout=1000) as blocker:
        page.dry_btn.click()
    assert blocker.args == ["build a todo app", True]


def test_games_page_poki_and_openfront(qapp, qtbot):
    """Test GamesPage poki launch and openfront controls."""
    page = GamesPage()
    qtbot.addWidget(page)

    page.goal_edit.setText("score 2000")
    with qtbot.waitSignal(page.play_poki_requested, timeout=1000) as blocker:
        page.play_btn.click()
    assert blocker.args[1] == "score 2000"

    with qtbot.waitSignal(page.stop_poki_requested, timeout=1000) as blocker:
        page.stop_btn.click()
    assert blocker.signal_triggered

    # OpenFront test
    with qtbot.waitSignal(page.run_openfront_requested, timeout=1000) as blocker:
        page.of_start_btn.click()
    assert blocker.args[0] == "http://localhost:8080"


def test_optimizer_page_clean_and_scan(qapp, qtbot):
    """Test OptimizerPage category checkboxes and clean signal."""
    page = OptimizerPage()
    qtbot.addWidget(page)

    assert page.score_label.text() != ""
    assert len(page.category_checkboxes) >= 3

    with qtbot.waitSignal(page.clean_requested, timeout=1000) as blocker:
        page.clean_btn.click()
    assert len(blocker.args[0]) >= 1


def test_skills_page_macro_recorder(qapp, qtbot):
    """Test SkillsPage macro recording and skill save."""
    page = SkillsPage()
    qtbot.addWidget(page)

    with qtbot.waitSignal(page.record_macro_toggled, timeout=1000) as blocker:
        page.record_btn.click()
    assert blocker.args == [True]

    with qtbot.waitSignal(page.record_macro_toggled, timeout=1000) as blocker:
        page.record_btn.click()
    assert blocker.args == [False]

    page.macro_name_input.setText("my_macro")
    with qtbot.waitSignal(page.save_macro_requested, timeout=1000) as blocker:
        page.save_macro_btn.click()
    assert blocker.args == ["my_macro"]


def test_history_page_search(qapp, qtbot):
    """Test HistoryPage filtering."""
    page = HistoryPage()
    qtbot.addWidget(page)

    total_rows = page.history_table.rowCount()
    assert total_rows >= 1

    first_text = page.history_table.item(0, 1).text()
    keyword = first_text.split(":")[0].strip() if ":" in first_text else first_text[:4]
    page.search_edit.setText(keyword)
    filtered_rows = page.history_table.rowCount()
    assert filtered_rows >= 1
    assert filtered_rows <= total_rows


def test_main_window_all_8_pages_navigation(qapp, qtbot):
    """Test that all 8 pages exist in MainWindow and switch cleanly."""
    engine = SuperLocalEngine()
    window = SuperLocalMainWindow(engine=engine)
    qtbot.addWidget(window)

    assert window.page_stack.count() == 8

    for i in range(8):
        window.sidebar.select_page(i)
        assert window.page_stack.currentIndex() == i
