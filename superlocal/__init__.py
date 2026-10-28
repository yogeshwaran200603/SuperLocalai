"""
SuperLocal Desktop Application Package
"""

import sys
from pathlib import Path

# Ensure root workspace is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.engine import get_engine, SuperLocalEngine
from core.events import EventBus, Event, EventType

__all__ = ["get_engine", "SuperLocalEngine", "EventBus", "Event", "EventType"]
