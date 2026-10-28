"""
SuperLocal Core Engine
Decoupled background execution engine with thread-safe EventBus API.
Supports asynchronous submissions, step tracking, safety approvals,
quota updates, emergency stops, and crash recovery.
"""

import os
import sys
import time
import uuid
import logging
import threading
import traceback
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path

from core.events import EventBus, EventType
from config import (
    LOGS_DIR,
    WORKSPACE_DIR,
    QUOTA_PER_DAY,
    PROVIDER_ORDER,
)
from safety import (
    trigger_emergency_stop,
    reset_emergency_stop,
    is_emergency_stopped,
    set_approval_callback,
    log_action,
)

# Setup GUI logging to logs/gui.log
LOGS_DIR.mkdir(parents=True, exist_ok=True)
GUI_LOG_PATH = LOGS_DIR / "gui.log"
logger = logging.getLogger("superlocal.gui")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(GUI_LOG_PATH, encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(fh)


class EngineState:
    IDLE = "Idle"
    WORKING = "Working"
    WAITING_APPROVAL = "Waiting for approval"
    STOPPED = "Stopped"
    ERROR = "Error"


class SuperLocalEngine:
    """
    Main controller for SuperLocal operations.
    Runs tasks asynchronously in a worker thread.
    Emits events over self.events for the GUI or any observer.
    """

    def __init__(self):
        self.events = EventBus()
        self.state = EngineState.IDLE
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._session_allowlist: set = set()
        self._is_paused = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially

        # Lazy initialized agent
        self._agent = None

        # Register safety approval callback
        set_approval_callback(self._on_safety_approval_requested)

    @property
    def agent(self):
        if self._agent is None:
            from agent import AstraAgent
            self._agent = AstraAgent()
        return self._agent

    def restart(self) -> None:
        """Restarts the core agent and clears any error/stop flags."""
        logger.info("Restarting engine...")
        reset_emergency_stop()
        self._pending_approvals.clear()
        self._is_paused = False
        self._pause_event.set()
        try:
            from agent import AstraAgent
            self._agent = AstraAgent()
            self.state = EngineState.IDLE
            self.events.emit(EventType.STATUS, status="SUCCESS", message="Engine restarted successfully.")
            self._emit_quota_update()
            logger.info("Engine restart complete.")
        except Exception as e:
            self.state = EngineState.ERROR
            self.events.emit(EventType.ERROR, error=f"Engine restart failed: {e}", traceback=traceback.format_exc(), recoverable=True)
            logger.error(f"Engine restart error: {e}")

    def submit(self, prompt: str) -> None:
        """Submits a command or prompt to be executed asynchronously."""
        clean_text = prompt.strip()
        if not clean_text:
            return

        with self._lock:
            if self.state == EngineState.WORKING:
                self.events.emit(EventType.ERROR, error="Engine is currently busy with another task.", recoverable=True)
                return
            self.state = EngineState.WORKING

        reset_emergency_stop()
        self.events.emit(EventType.MESSAGE, role="user", content=clean_text, timestamp=time.time())

        # Start execution in worker thread
        self._worker_thread = threading.Thread(
            target=self._run_task_worker,
            args=(clean_text,),
            name=f"EngineWorker-{uuid.uuid4().hex[:6]}",
            daemon=True
        )
        self._worker_thread.start()

    def stop(self) -> None:
        """Interrupts and terminates active operations immediately."""
        logger.info("Stop requested via engine.stop()")
        trigger_emergency_stop("User STOP button or Ctrl+Alt+Q")
        self.state = EngineState.STOPPED
        self.events.emit(EventType.STATUS, status="FAILED", message="Operation cancelled: Emergency stop triggered.")

    def pause(self) -> None:
        """Pauses the worker loop."""
        self._is_paused = True
        self._pause_event.clear()
        logger.info("Engine paused.")

    def resume(self) -> None:
        """Resumes the worker loop."""
        self._is_paused = False
        self._pause_event.set()
        logger.info("Engine resumed.")

    def toggle_pause(self) -> bool:
        """Toggles pause/resume and returns new pause state."""
        if self._is_paused:
            self.resume()
            return False
        else:
            self.pause()
            return True

    def approve(self, request_id: str, approved: bool, always: bool = False) -> None:
        """Resolves an outstanding approval request."""
        with self._lock:
            req = self._pending_approvals.get(request_id)
            if not req:
                return

            req["approved"] = approved
            if approved and always:
                action_sig = f"{req.get('action_type')}:{req.get('target', '')}"
                # Never allow "always" for critical dangerous actions
                disallowed_always = ("send", "delete", "pay", "install", "admin", "rmdir")
                if not any(d in action_sig.lower() for d in disallowed_always):
                    self._session_allowlist.add(action_sig)
                    logger.info(f"Added to session allowlist: {action_sig}")

            req["event"].set()

    def set_provider(self, provider_name: str) -> None:
        """Switches active provider and emits provider_changed event."""
        try:
            new_prov = self.agent.set_provider(provider_name)
            active_model = getattr(new_prov, "active_model", getattr(new_prov, "model", "default"))
            self.events.emit(EventType.PROVIDER_CHANGED, provider=new_prov.name, model=active_model)
            self._emit_quota_update()
            logger.info(f"Switched provider to {new_prov.name} ({active_model})")
        except Exception as e:
            self.events.emit(EventType.ERROR, error=f"Failed to switch provider: {e}", recoverable=True)
            logger.error(f"Failed to switch provider: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns snapshot of engine state and quotas."""
        prov = getattr(self.agent, "active_provider", None)
        prov_name = getattr(prov, "name", PROVIDER_ORDER[0]) if prov else PROVIDER_ORDER[0]
        model_name = getattr(self.agent, "active_model", "gemini-3.8-flash")
        mem = getattr(self.agent, "memory", None)
        requests_today = mem.get_daily_api_calls() if mem else 0
        return {
            "state": self.state,
            "provider": prov_name,
            "model": model_name,
            "requests_today": requests_today,
            "quota_per_day": QUOTA_PER_DAY or 1000,
            "workspace": str(WORKSPACE_DIR),
            "is_paused": self._is_paused,
        }

    # ==========================================================================
    # Internal Worker Implementation
    # ==========================================================================

    def _run_task_worker(self, prompt: str) -> None:
        """Executes prompt safely, catching any exceptions and emitting updates."""
        try:
            logger.info(f"Executing task: {prompt[:80]}")
            start_time = time.time()

            # 1. Local-first check
            from agent import try_local_first_execution
            local_res = try_local_first_execution(prompt)
            if local_res:
                duration = time.time() - start_time
                self.events.emit(EventType.TOOL_OUTPUT, tool_name="local_first", output=local_res, raw={"result": local_res})
                self.events.emit(EventType.MESSAGE, role="assistant", content=local_res, timestamp=time.time())
                self.events.emit(EventType.STATUS, status="SUCCESS", message=local_res)
                self.state = EngineState.IDLE
                self._emit_quota_update()
                return

            # 2. Wrap Agent tool execution to emit live activity events
            original_execute_tool = self.agent.execute_tool
            step_counter = [0]

            def _hooked_execute_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
                self._pause_event.wait()  # Handle pause
                if is_emergency_stopped():
                    return {"success": False, "status": "EMERGENCY_STOPPED", "error": "Emergency stop active."}

                step_counter[0] += 1
                curr_step = step_counter[0]
                t_step_start = time.time()

                self.events.emit(
                    EventType.STEP_STARTED,
                    step=curr_step,
                    max_steps=8,
                    tool_name=tool_name,
                    args=args,
                    elapsed=time.time() - start_time,
                )

                res = original_execute_tool(tool_name, args)
                duration = time.time() - t_step_start

                self.events.emit(
                    EventType.TOOL_OUTPUT,
                    tool_name=tool_name,
                    output=str(res.get("stdout") or res.get("message") or res.get("error") or res),
                    raw=res,
                )

                self.events.emit(
                    EventType.STEP_FINISHED,
                    step=curr_step,
                    tool_name=tool_name,
                    result=res,
                    success=res.get("success", True),
                    duration=duration,
                )

                self._emit_quota_update()
                return res

            self.agent.execute_tool = _hooked_execute_tool

            # Execute via agent
            result = self.agent.run(prompt)
            self.agent.execute_tool = original_execute_tool  # Restore hook

            if is_emergency_stopped():
                self.state = EngineState.STOPPED
                self.events.emit(EventType.STATUS, status="FAILED", message="Task cancelled: Emergency stop triggered.")
            else:
                self.state = EngineState.IDLE
                self.events.emit(EventType.MESSAGE, role="assistant", content=result, timestamp=time.time())
                self.events.emit(EventType.STATUS, status="SUCCESS", message="Task completed.")

            self._emit_quota_update()

        except Exception as e:
            logger.error(f"Task crash: {e}\n{traceback.format_exc()}")
            self.state = EngineState.ERROR
            self.events.emit(
                EventType.ERROR,
                error=f"Engine error: {e}",
                traceback=traceback.format_exc(),
                recoverable=True,
            )
            self.events.emit(EventType.STATUS, status="FAILED", message=f"Task error: {e}")
        finally:
            if self.state not in (EngineState.ERROR, EngineState.STOPPED):
                self.state = EngineState.IDLE

    def _on_safety_approval_requested(self, payload: Dict[str, Any]) -> bool:
        """
        Called synchronously by safety.py when an action requires approval.
        Checks session allowlist, or emits approval_requested and blocks for up to 60s.
        """
        action_type = payload.get("action_type", "action")
        target = payload.get("target", "")
        action_sig = f"{action_type}:{target}"

        # 1. Check per-session allowlist
        if action_sig in self._session_allowlist:
            logger.info(f"Action auto-approved via session allowlist: {action_sig}")
            return True

        # 2. Create approval request
        req_id = str(uuid.uuid4())[:8]
        completion_event = threading.Event()
        approval_record = {
            "request_id": req_id,
            "action_type": action_type,
            "details": payload.get("details", {}),
            "risk_level": payload.get("risk_level", "medium"),
            "target": target,
            "message": payload.get("message", f"Allow {action_type}?"),
            "event": completion_event,
            "approved": False,
        }

        with self._lock:
            self._pending_approvals[req_id] = approval_record
            prev_state = self.state
            self.state = EngineState.WAITING_APPROVAL

        # Emit event for UI dialog
        self.events.emit(
            EventType.APPROVAL_REQUESTED,
            request_id=req_id,
            action_type=action_type,
            details=payload.get("details", {}),
            risk_level=payload.get("risk_level", "medium"),
            target=target,
            message=payload.get("message", f"Allow {action_type}?"),
            timeout=60,
        )

        logger.info(f"Waiting for user approval: req_id={req_id}, action={action_type}")

        # Block with 60-second timeout (timeout counts as Deny)
        answered = completion_event.wait(timeout=60.0)

        with self._lock:
            self._pending_approvals.pop(req_id, None)
            self.state = prev_state

        if not answered:
            logger.warning(f"Approval request {req_id} timed out after 60s (Deny)")
            log_action(action_type, payload.get("details", {}), "TIMEOUT_DENIED", "Approval timed out after 60s")
            return False

        approved = approval_record.get("approved", False)
        log_action(action_type, payload.get("details", {}), "APPROVED" if approved else "USER_DENIED", f"GUI approval req_id={req_id}")
        return approved

    def _emit_quota_update(self) -> None:
        """Helper to broadcast quota changes."""
        try:
            mem = getattr(self.agent, "memory", None)
            if mem:
                calls_today = mem.get_daily_api_calls()
                usage_summary = mem.get_daily_usage_summary()
                self.events.emit(
                    EventType.QUOTA_UPDATED,
                    requests_today=calls_today,
                    quota_per_day=QUOTA_PER_DAY or 1000,
                    usage_by_model=usage_summary,
                )
        except Exception:
            pass


# Singleton engine instance
_GLOBAL_ENGINE: Optional[SuperLocalEngine] = None


def get_engine() -> SuperLocalEngine:
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = SuperLocalEngine()
    return _GLOBAL_ENGINE
