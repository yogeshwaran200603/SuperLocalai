"""
SuperLocal Thread-Safe Event Bus
Dispatches engine events to UI and other subscribers safely across threads.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional


class EventType:
    MESSAGE = "message"
    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"
    TOOL_OUTPUT = "tool_output"
    APPROVAL_REQUESTED = "approval_requested"
    STATUS = "status"
    PROVIDER_CHANGED = "provider_changed"
    QUOTA_UPDATED = "quota_updated"
    VOICE_STATE = "voice_state"
    SCREEN_NOTE = "screen_note"
    ERROR = "error"


@dataclass
class Event:
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Thread-safe publish/subscribe event bus."""

    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}

    def subscribe(self, event_name: str, callback: Callable[[Event], None]) -> None:
        """Subscribes a callback to a specific event name or '*' for all events."""
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[Event], None]) -> None:
        """Removes a previously registered callback."""
        with self._lock:
            if event_name in self._subscribers and callback in self._subscribers[event_name]:
                self._subscribers[event_name].remove(callback)

    def emit(self, event_name: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Event:
        """Emits an event to all subscribers."""
        payload = {}
        if data and isinstance(data, dict):
            payload.update(data)
        payload.update(kwargs)
        event = Event(name=event_name, data=payload)
        with self._lock:
            targets = list(self._subscribers.get(event_name, []))
            wildcard_targets = list(self._subscribers.get("*", []))

        for cb in targets + wildcard_targets:
            try:
                cb(event)
            except Exception as e:
                # Subscriber errors must not crash the event bus
                pass

        return event

    def clear(self) -> None:
        """Clears all subscribers."""
        with self._lock:
            self._subscribers.clear()
