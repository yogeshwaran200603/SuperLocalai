"""
SuperLocal Autopilot Package
Provides autonomous end-to-end task execution with state persistence,
git checkpointing, verification, self-healing, and budget controls.
"""

from typing import Optional, Any, List, Dict

from autopilot.state import (
    JobState,
    JobStep,
    JobStatus,
    StepStatus,
    AutopilotStateStore,
)
from autopilot.planner import AutopilotPlanner, sanitize_untrusted_data
from autopilot.verifier import AutopilotVerifier
from autopilot.executor import AutopilotExecutor

_default_executor: Optional[AutopilotExecutor] = None


def get_autopilot_engine() -> AutopilotExecutor:
    """Returns singleton AutopilotExecutor instance."""
    global _default_executor
    if _default_executor is None:
        _default_executor = AutopilotExecutor()
    return _default_executor


def run_autopilot(
    goal: str,
    dry_run: bool = False,
    provider: Optional[Any] = None,
    job_slug: Optional[str] = None,
) -> JobState:
    """Runs a complete autopilot job or displays dry run plan."""
    engine = get_autopilot_engine()
    return engine.run_job(goal, dry_run=dry_run, provider=provider, job_slug=job_slug)


def undo_last_step() -> str:
    """Rolls back the most recent completed step via git reset."""
    engine = get_autopilot_engine()
    success, msg = engine.undo_last_step()
    return msg


def list_jobs_summary(limit: int = 10) -> List[Dict[str, Any]]:
    """Returns recent jobs from SQLite store."""
    engine = get_autopilot_engine()
    return engine.store.list_jobs(limit=limit)


def get_active_job_status() -> Optional[Dict[str, Any]]:
    """Returns current active job details."""
    engine = get_autopilot_engine()
    job = engine._active_job or engine.store.get_latest_active_job()
    if not job:
        return None
    return {
        "id": job.id,
        "goal": job.goal,
        "status": job.status,
        "current_step": job.current_step_id,
        "total_steps": len(job.steps),
        "elapsed": job.format_elapsed(),
        "model_calls": job.model_calls,
        "desktop_actions": job.desktop_actions,
        "workspace": job.workspace_dir,
    }


__all__ = [
    "run_autopilot",
    "undo_last_step",
    "list_jobs_summary",
    "get_active_job_status",
    "get_autopilot_engine",
    "AutopilotExecutor",
    "AutopilotPlanner",
    "AutopilotVerifier",
    "AutopilotStateStore",
    "JobState",
    "JobStep",
    "JobStatus",
    "StepStatus",
    "sanitize_untrusted_data",
]
