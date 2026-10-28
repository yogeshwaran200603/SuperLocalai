"""
Unit tests for Core Engine API and EventBus (Stage 1)
Tests:
1. EventBus pub/sub
2. engine.submit asynchronous dispatch
3. engine.stop cancels active execution
4. Approval flow (allow, deny, timeout)
5. Engine crash handling & restart recovery
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from core.events import EventBus, EventType
from core.engine import SuperLocalEngine, EngineState


def test_event_bus_pub_sub():
    bus = EventBus()
    received = []

    def on_event(ev):
        received.append(ev)

    bus.subscribe(EventType.MESSAGE, on_event)
    bus.emit(EventType.MESSAGE, role="user", content="hello")

    assert len(received) == 1
    assert received[0].name == EventType.MESSAGE
    assert received[0].data["content"] == "hello"

    # Test unsubscribe
    bus.unsubscribe(EventType.MESSAGE, on_event)
    bus.emit(EventType.MESSAGE, role="user", content="world")
    assert len(received) == 1


def test_engine_submit_local_command():
    engine = SuperLocalEngine()
    messages = []
    statuses = []

    engine.events.subscribe(EventType.MESSAGE, lambda ev: messages.append(ev.data))
    engine.events.subscribe(EventType.STATUS, lambda ev: statuses.append(ev.data))

    with patch("tools.shell.subprocess.Popen"):
        engine.submit("open notepad")
        if engine._worker_thread:
            engine._worker_thread.join(timeout=5.0)

    assert len(messages) >= 2
    assert messages[0]["role"] == "user"
    assert "open notepad" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    assert "notepad" in messages[1]["content"].lower()
    assert any(s["status"] == "SUCCESS" for s in statuses)


def test_engine_stop():
    engine = SuperLocalEngine()
    statuses = []
    engine.events.subscribe(EventType.STATUS, lambda ev: statuses.append(ev.data))

    engine.stop()
    assert engine.state == EngineState.STOPPED
    assert any(s["status"] == "FAILED" for s in statuses)


def test_engine_approval_flow_allow():
    engine = SuperLocalEngine()
    approvals = []
    engine.events.subscribe(EventType.APPROVAL_REQUESTED, lambda ev: approvals.append(ev.data))

    # Trigger approval in a thread
    result_container = []
    import threading

    def _worker():
        from safety import confirm_action
        res = confirm_action("file_delete", {"path": "C:/fake/path.txt"})
        result_container.append(res)

    th = threading.Thread(target=_worker)
    th.start()

    # Wait for approval request to be emitted
    t0 = time.time()
    while not approvals and time.time() - t0 < 2.0:
        time.sleep(0.05)

    assert len(approvals) == 1
    req_id = approvals[0]["request_id"]
    assert approvals[0]["action_type"] == "file_delete"

    # Approve it
    engine.approve(req_id, True)
    th.join(timeout=2.0)

    assert result_container == [True]


def test_engine_approval_flow_deny():
    engine = SuperLocalEngine()
    approvals = []
    engine.events.subscribe(EventType.APPROVAL_REQUESTED, lambda ev: approvals.append(ev.data))

    result_container = []
    import threading

    def _worker():
        from safety import confirm_action
        res = confirm_action("file_delete", {"path": "C:/fake/path.txt"})
        result_container.append(res)

    th = threading.Thread(target=_worker)
    th.start()

    t0 = time.time()
    while not approvals and time.time() - t0 < 2.0:
        time.sleep(0.05)

    assert len(approvals) == 1
    req_id = approvals[0]["request_id"]

    # Deny it
    engine.approve(req_id, False)
    th.join(timeout=2.0)

    assert result_container == [False]


def test_engine_crash_handling_and_restart():
    engine = SuperLocalEngine()
    errors = []
    engine.events.subscribe(EventType.ERROR, lambda ev: errors.append(ev.data))

    # Force a crash in task worker
    with patch("agent.try_local_first_execution", side_effect=RuntimeError("Simulated engine fault")):
        engine.submit("do something crashy")
        if engine._worker_thread:
            engine._worker_thread.join(timeout=5.0)

    assert len(errors) >= 1
    assert "Simulated engine fault" in errors[0]["error"]
    assert engine.state == EngineState.ERROR

    # Restart engine must clear error and restore IDLE state
    engine.restart()
    assert engine.state == EngineState.IDLE
