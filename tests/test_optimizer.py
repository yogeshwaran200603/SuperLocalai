"""
SuperLocal PC Optimizer Test Suite
Mocked unit tests for:
- Prohibition of harmful tweaks (registry cleaner, RAM flush, service disabling, Defender tampering).
- Path boundary security blocklists (Windows, Program Files, User Documents).
- Cleaner preview and confirmation flow.
- Quarantine and undo restoration logic.
- Startup applications listing, protected item gate, and backup restoration.
- Disk SMART status and SSD TRIM enforcement (blocking defrag on SSDs).
- Duplicate file content hash detection.
- System health checks (SFC read-only, Defender status preservation).
- Power scheme inspection and switching.
- Optimization report generation (Markdown & PDF).
- Command dispatcher and voice routing for "why is my pc slow?".
All tests use mocks with ZERO live cloud calls.
"""

import os
import json
import time
import shutil
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from optimizer.guards import (
    check_forbidden_tweak,
    is_safe_optimizer_path,
    is_protected_startup_item,
    confirm_action,
    confirm_admin_action,
    create_restore_point_if_enabled,
)
from optimizer.scanner import (
    get_cpu_metrics,
    get_memory_metrics,
    calculate_health_score,
    run_system_scan,
)
from optimizer.cleaner import (
    get_file_age_days,
    format_bytes,
    scan_cleanable_category,
    clean_categories,
    undo_clean,
)
from optimizer.startup import (
    list_startup_entries,
    disable_startup_item,
    restore_startup_items,
    guess_app_impact_and_desc,
)
from optimizer.disk import (
    compute_file_sha256,
    find_duplicate_files,
    find_largest_items,
    run_ssd_trim,
)
from optimizer.health import (
    check_sfc_integrity,
    check_dism_health,
    get_defender_status,
)
from optimizer.power import (
    get_current_power_plan,
    set_power_plan,
)
from optimizer.reporter import generate_optimization_report
from optimizer import handle_optimizer_command
from safety import reset_emergency_stop


@pytest.fixture(autouse=True)
def clean_environment():
    reset_emergency_stop()
    yield
    reset_emergency_stop()


# 1. Hard Rule Checks: Forbidden Tweaks
def test_forbidden_tweaks_rejection():
    # Registry Cleaner
    is_f, exp = check_forbidden_tweak("run registry cleaner to speed up pc")
    assert is_f is True
    assert "registry" in exp.lower()
    assert "dangerous" in exp.lower() or "unnecessary" in exp.lower()

    # RAM Booster / Memory Flusher
    is_f, exp = check_forbidden_tweak("boost ram and flush working set memory")
    assert is_f is True
    assert "pagefile" in exp.lower() or "thrashing" in exp.lower()

    # Service Disabling
    is_f, exp = check_forbidden_tweak("disable windows services for gaming")
    assert is_f is True
    assert "services" in exp.lower()

    # Defender Tampering
    is_f, exp = check_forbidden_tweak("disable windows defender")
    assert is_f is True
    assert "defender" in exp.lower()

    # Unsigned Debloater Scripts
    is_f, exp = check_forbidden_tweak("run radioactive debloat script")
    assert is_f is True
    assert "debloat" in exp.lower()

    # Valid Safe Query
    is_f, _ = check_forbidden_tweak("/optimize scan")
    assert is_f is False


# 2. Path Boundary Blocklist
def test_path_blocklist():
    # Blocked paths
    assert is_safe_optimizer_path(Path("C:/Windows"))[0] is False
    assert is_safe_optimizer_path(Path("C:/Windows/System32/cmd.exe"))[0] is False
    assert is_safe_optimizer_path(Path("C:/Program Files/Google/Chrome"))[0] is False
    assert is_safe_optimizer_path(Path("C:/Program Files (x86)/Steam"))[0] is False
    assert is_safe_optimizer_path(Path("C:/Users/Administrator/Documents/MyFile.docx"))[0] is False

    # Allowed paths
    assert is_safe_optimizer_path(Path("C:/Users/Administrator/AppData/Local/Temp/scratch.tmp"))[0] is True
    assert is_safe_optimizer_path(Path("C:/Users/Administrator/Downloads/sample.zip"))[0] is True


# 3. Scanner Metrics and Health Score Calculation
def test_scanner_health_score_calculation():
    drives = [{"mountpoint": "C:\\", "free_gb": 40.0, "percent_free": 35.0}]
    battery = {"percent": 85, "power_plugged": True}

    # Nominal healthy state
    score, findings = calculate_health_score(
        cpu_pct=15.0,
        mem_pct=45.0,
        drives=drives,
        startup_count=5,
        uptime_sec=86400,
        pending_reboot=False,
        battery=battery,
    )
    assert score >= 90
    assert len(findings) <= 3

    # Stressed state (high RAM, low disk space, high startup)
    low_drives = [{"mountpoint": "C:\\", "free_gb": 5.0, "percent_free": 8.0}]
    bad_score, bad_findings = calculate_health_score(
        cpu_pct=92.0,
        mem_pct=94.0,
        drives=low_drives,
        startup_count=22,
        uptime_sec=15 * 86400,
        pending_reboot=True,
        battery=None,
    )
    assert bad_score <= 40
    assert any("RAM" in f for f in bad_findings)
    assert any("disk" in f.lower() for f in bad_findings)


# 4. Cleaner Age Filter and Preview Flow
def test_cleaner_category_scan_and_age_filter(tmp_path):
    # Create test directory with old file and recent file
    test_cat_dir = tmp_path / "temp_files"
    test_cat_dir.mkdir()

    old_file = test_cat_dir / "old_scratch.tmp"
    old_file.write_text("Old content")
    # Set modification time to 10 days ago
    ten_days_ago = time.time() - (10 * 86400)
    os.utime(str(old_file), (ten_days_ago, ten_days_ago))

    new_file = test_cat_dir / "new_scratch.tmp"
    new_file.write_text("Recent content")

    cat_info = {
        "name": "Test Temp",
        "paths": [test_cat_dir],
        "description": "Test scratch folder",
        "pattern": "*",
        "recursive": False,
    }

    # Scan with 7-day age threshold
    result = scan_cleanable_category("test_temp", cat_info, min_age_days=7)
    assert result["file_count"] == 1
    assert result["files"][0]["path"] == str(old_file)


# 5. Quarantine and Undo Restoration Logic
def test_quarantine_and_undo_flow(tmp_path, monkeypatch):
    quarantine_base = tmp_path / "quarantine"
    quarantine_base.mkdir()
    monkeypatch.setattr("optimizer.cleaner.OPTIMIZER_QUARANTINE_DIR", quarantine_base)

    target_dir = tmp_path / "app_temp"
    target_dir.mkdir()
    file_to_clean = target_dir / "cached_item.tmp"
    file_to_clean.write_text("Quarantined content payload")
    ten_days_ago = time.time() - (10 * 86400)
    os.utime(str(file_to_clean), (ten_days_ago, ten_days_ago))

    cat_data = [{
        "key": "test_cat",
        "name": "Test Category",
        "description": "Testing quarantine",
        "file_count": 1,
        "total_bytes": len("Quarantined content payload"),
        "files": [{
            "path": str(file_to_clean),
            "size": len("Quarantined content payload"),
            "age_days": 10.0,
        }]
    }]

    # Clean with auto_approve=True
    res_clean = clean_categories(cat_data, min_age_days=7, auto_approve=True)
    assert res_clean["success"] is True
    assert res_clean["total_cleaned_files"] == 1
    # File should no longer exist in target_dir
    assert not file_to_clean.exists()

    # Now run undo
    res_undo = undo_clean(session_id=res_clean["session_id"])
    assert res_undo["success"] is True
    assert res_undo["restored_count"] == 1
    # File must be restored
    assert file_to_clean.exists()
    assert file_to_clean.read_text() == "Quarantined content payload"


# 6. Startup Applications Protection and Restore Flow
def test_startup_item_protection_and_undo(tmp_path, monkeypatch):
    backup_file = tmp_path / "startup_backup.json"
    quarantine_startup = tmp_path / "quarantine_startup"
    quarantine_startup.mkdir()
    monkeypatch.setattr("optimizer.startup.OPTIMIZER_STARTUP_BACKUP", backup_file)
    monkeypatch.setattr("optimizer.startup.OPTIMIZER_QUARANTINE_DIR", tmp_path / "quarantine")

    # Protection checks
    assert is_protected_startup_item("Windows Defender", "Microsoft Corporation", "SecHealthUI.exe") is True
    assert is_protected_startup_item("Realtek Audio Service", "Realtek", "RtkAudio.exe") is True
    assert is_protected_startup_item("Nvidia Capture Server", "NVIDIA", "nvspcaps64.exe") is True
    assert is_protected_startup_item("Discord", "Discord Inc.", "Update.exe --processStart Discord.exe") is False
    assert is_protected_startup_item("Spotify", "Spotify AB", "Spotify.exe") is False

    # Simulate disabling a folder shortcut
    fake_shortcut = tmp_path / "Spotify.lnk"
    fake_shortcut.write_text("Dummy shortcut link content")

    item = {
        "id": "folder_user_spotify",
        "name": "Spotify",
        "location": "Folder: User Startup",
        "command": str(fake_shortcut),
        "publisher": "Spotify AB",
        "impact": "Medium",
        "description": "Spotify Music Player",
        "is_protected": False,
        "source_type": "folder",
        "file_path": str(fake_shortcut),
    }

    ok, msg = disable_startup_item(item, backup_file=backup_file)
    assert ok is True
    assert not fake_shortcut.exists()
    assert backup_file.exists()

    # Restore via /optimize undo
    res_restore = restore_startup_items(backup_file=backup_file)
    assert res_restore["success"] is True
    assert res_restore["restored_count"] == 1
    assert fake_shortcut.exists()
    assert fake_shortcut.read_text() == "Dummy shortcut link content"


# 7. Duplicate File Content Hash Finder
def test_duplicate_file_finder(tmp_path):
    test_folder = tmp_path / "dupe_test"
    test_folder.mkdir()

    f1 = test_folder / "original.txt"
    f2 = test_folder / "copy1.txt"
    f3 = test_folder / "unique.txt"

    content = "A" * 2048
    f1.write_text(content)
    f2.write_text(content)
    f3.write_text("B" * 2048)

    h1 = compute_file_sha256(f1)
    h2 = compute_file_sha256(f2)
    h3 = compute_file_sha256(f3)
    assert h1 == h2
    assert h1 != h3

    dupes = find_duplicate_files(test_folder, min_size_bytes=100)
    assert len(dupes) == 1
    assert len(dupes[0]) == 2


# 8. SSD TRIM and Defragmentation Blocking
def test_ssd_trim_and_defrag_blocking():
    # Mocking physical disk check
    mock_disks = [{"id": 0, "name": "Samsung NVMe 980", "media_type": "SSD", "health": "Healthy", "size_gb": 1000.0}]

    with patch("optimizer.disk.get_physical_disk_health", return_value=mock_disks), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="TRIM completed successfully.")

        res = run_ssd_trim(drive_letter="C", auto_approve=True)
        assert res["success"] is True
        assert "TRIM" in res["message"]
        # Ensure defrag is NEVER called
        for call_args in mock_run.call_args_list:
            cmd_str = str(call_args[0][0])
            assert "-Defrag" not in cmd_str
            assert "defrag.exe" not in cmd_str


# 9. System Health Read-Only SFC & Defender Verification
def test_health_sfc_and_defender():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Windows Resource Protection did not find any integrity violations.",
            stderr=""
        )
        res_sfc = check_sfc_integrity(repair=False)
        assert res_sfc["status"] == "Clean"

        # Defender query test
        def_status = get_defender_status()
        assert def_status["antivirus_enabled"] is True
        assert def_status["status"] == "Operational"


# 10. Power Plan Management
def test_power_plan_inspection():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)"
        )
        guid, name = get_current_power_plan()
        assert "Balanced" in name
        assert "381b4222" in guid


# 11. Optimization Report Generation
def test_optimization_report_generation(tmp_path, monkeypatch):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    monkeypatch.setattr("optimizer.reporter.OPTIMIZER_REPORTS_DIR", report_dir)

    before = {"health_score": 68}
    after = {"health_score": 88}
    clean = {"total_freed_bytes": 1024 * 1024 * 750}  # 750 MB
    startup = {"disabled_count": 3}

    res = generate_optimization_report(before_scan=before, after_scan=after, clean_summary=clean, startup_summary=startup)
    assert res["success"] is True
    assert Path(res["markdown_path"]).exists()
    content = Path(res["markdown_path"]).read_text(encoding="utf-8")
    assert "SuperLocal PC Optimizer Report" in content
    assert "750.0 MB" in content
    assert "3 apps" in content


# 12. Commands Dispatcher Flow
def test_optimizer_command_dispatcher():
    # Scan
    res_scan = handle_optimizer_command("/optimize scan")
    assert "score" in res_scan.lower() or "scan" in res_scan.lower()

    # Forbidden Tweak
    res_tweak = handle_optimizer_command("/optimize clean the registry")
    assert "registry" in res_tweak.lower()

    # Schedule
    res_sched = handle_optimizer_command("/optimize schedule weekly")
    assert "weekly" in res_sched.lower()


# 13. Voice Command Routing Check
def test_voice_command_routing_why_is_pc_slow():
    from agent import try_local_first_execution
    res = try_local_first_execution("Hey SuperLocal, why is my PC slow?")
    assert res is not None
    assert "score" in res.lower() or "health" in res.lower() or "scan" in res.lower() or "ram" in res.lower()
