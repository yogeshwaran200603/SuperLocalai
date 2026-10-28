"""
Tests for SuperLocal Stage 3: Settings Page, Keyring Storage, and First-Run Wizard
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Force offscreen Qt platform before creating QApplication
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from superlocal.core.credentials import store_credential, retrieve_credential, mask_credential
from superlocal.ui.pages.settings_page import SettingsPage
from superlocal.ui.pages.wizard import SetupWizardDialog, is_first_run, mark_setup_completed, SETUP_FLAG_PATH
from core.engine import SuperLocalEngine


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_credentials_keyring(monkeypatch):
    """Verify secure keyring storage and retrieval."""
    mock_vault = {}

    def mock_set_password(service, username, password):
        mock_vault[f"{service}:{username}"] = password

    def mock_get_password(service, username):
        return mock_vault.get(f"{service}:{username}")

    monkeypatch.setattr("keyring.set_password", mock_set_password)
    monkeypatch.setattr("keyring.get_password", mock_get_password)

    # Store credential
    store_credential("gemini", "AIzaSyTest123456789")
    retrieved = retrieve_credential("gemini")
    assert retrieved == "AIzaSyTest123456789"

    # Mask credential
    masked = mask_credential(retrieved)
    assert masked.startswith("AIza")
    assert masked.endswith("6789")
    assert "..." in masked
    assert "Test12345" not in masked


def test_settings_page_order_reorder(qapp):
    """Test moving provider order up and down."""
    page = SettingsPage()
    count = page.order_list.count()
    assert count >= 2

    # Select second item and move up
    page.order_list.setCurrentRow(1)
    second_text = page.order_list.item(1).text()
    page._move_order_up()
    assert page.order_list.item(0).text() == second_text

    # Move down
    page._move_order_down()
    assert page.order_list.item(1).text() == second_text


def test_settings_page_selftest(qapp, monkeypatch):
    """Test running diagnostics populates table."""
    mock_results = [
        {"subsystem": "OS", "check": "Windows check", "status": "PASS", "details": "Win32 OK"},
        {"subsystem": "Providers", "check": "Gemini key", "status": "PASS", "details": "Found in keyring"},
    ]
    monkeypatch.setattr("superlocal.ui.pages.settings_page.run_selftest", lambda: (True, mock_results))

    page = SettingsPage()
    page._on_run_selftest()

    assert page.diag_table.rowCount() == 2
    assert page.diag_table.item(0, 0).text() == "OS"
    assert page.diag_table.item(0, 2).text() == "PASS"
    assert page.diag_table.item(1, 0).text() == "Providers"


def test_first_run_wizard(qapp, tmp_path, monkeypatch):
    """Test first run wizard flow and marker creation."""
    test_flag = tmp_path / ".setup_completed"
    monkeypatch.setattr("superlocal.ui.pages.wizard.SETUP_FLAG_PATH", test_flag)
    monkeypatch.setattr("superlocal.ui.pages.wizard.DATA_DIR", tmp_path)

    assert is_first_run() is True

    wizard = SetupWizardDialog()
    assert wizard.stack.currentIndex() == 0

    # Step through wizard
    wizard._on_next()
    assert wizard.stack.currentIndex() == 1
    wizard._on_next()
    assert wizard.stack.currentIndex() == 2
    wizard._on_next()
    assert wizard.stack.currentIndex() == 3

    # Step back
    wizard._on_prev()
    assert wizard.stack.currentIndex() == 2
    wizard._on_next()
    assert wizard.stack.currentIndex() == 3

    # Finish wizard
    wizard._on_next()
    assert test_flag.exists()
    assert is_first_run() is False
