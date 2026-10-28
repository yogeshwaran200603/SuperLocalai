"""
Live model check: submit 'open notepad' through SuperLocalEngine.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
from core.engine import get_engine
from core.events import EventType

def main():
    engine = get_engine()
    results = []

    def on_message(event):
        results.append(event.data)
        print(f"[{event.name}] {event.data}")

    engine.events.subscribe(EventType.MESSAGE, on_message)

    print("Submitting live command: 'open notepad'...")
    engine.submit("open notepad")

    # Wait for completion
    timeout = 10.0
    start = time.time()
    while engine.state != "idle" and time.time() - start < timeout:
        time.sleep(0.2)

    print(f"Final engine state: {engine.state}")
    print(f"Total messages received: {len(results)}")
    for r in results:
        print(f"  {r.get('role')}: {r.get('content')}")

if __name__ == "__main__":
    main()
