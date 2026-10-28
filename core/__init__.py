"""
SuperLocal Core Engine Package
Clean API layer splitting UI from background execution.
"""

from core.events import EventBus, Event
from core.engine import SuperLocalEngine, get_engine

__all__ = ["EventBus", "Event", "SuperLocalEngine", "get_engine"]
