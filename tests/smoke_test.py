"""End-to-end smoke test for the daemon pub/sub protocol.

Spawns the daemon, connects a Subscriber, walks the state machine, and
verifies the events arrive as expected. Stops at RECORDING (does NOT
trigger the transcription pipeline — that requires a real Deepgram call).
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
from collections import deque
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voicematter.events import Subscriber


def main():
    # Clean up any leftover socket
    sock_path = "/tmp/voicematter.sock"
    if os.path.exists(sock_path):
        os.remove(sock_path)

    daemon = subprocess.Popen(
        ["uv", "run", "python", "main.py", "daemon"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    # Wait for socket
    for _ in range(40):
        if os.path.exists(sock_path):
            break
        time.sleep(0.1)
    else:
        print("FAIL: socket never appeared")
        daemon.terminate()
        return 1

    print(f"Daemon PID: {daemon.pid}, socket ready")

    received: deque[dict[str, Any]] = deque()

    def on_event(ev: dict[str, Any]) -> None:
        received.append(ev)
        print(f"  EVENT: {ev}")

    sub = Subscriber(sock_path, on_event)
    sub.start()

    # Initial sync event (state=idle)
    time.sleep(0.3)
    if not received or received[-1].get("event") != "state" or received[-1].get("state") != "idle":
        print(f"FAIL: expected initial state=idle, got {list(received)}")
        sub.close()
        daemon.terminate()
        return 1
    print("PASS: initial state=idle event received")

    # Trigger IDLE -> RECORDING
    received.clear()
    sub.trigger()
    time.sleep(0.4)
    states = [e.get("state") for e in received if e.get("event") == "state"]
    if "recording" not in states:
        print(f"FAIL: expected state=recording, got states={states}")
        sub.close()
        daemon.terminate()
        return 1
    print(f"PASS: IDLE -> RECORDING (states seen: {states})")

    # If audio failed to start, the daemon rolls back to IDLE and emits an
    # error event. In that case we can't test pause/resume, but the protocol
    # is still exercised correctly (graceful failure).
    audio_failed = any(e.get("event") == "error" for e in received)
    if audio_failed:
        print("NOTE: audio device unavailable in this environment — daemon "
              "emitted error event and returned to IDLE (graceful handling). "
              "Skipping pause/resume assertions.")
    else:
        # Pause RECORDING -> PAUSED
        received.clear()
        sub.pause()
        time.sleep(0.4)
        states = [e.get("state") for e in received if e.get("event") == "state"]
        if "paused" not in states:
            print(f"FAIL: expected state=paused, got states={states}")
            sub.close()
            daemon.terminate()
            return 1
        print(f"PASS: RECORDING -> PAUSED (states seen: {states})")

        # Resume PAUSED -> RECORDING
        received.clear()
        sub.resume()
        time.sleep(0.4)
        states = [e.get("state") for e in received if e.get("event") == "state"]
        if "recording" not in states:
            print(f"FAIL: expected state=recording after resume, got states={states}")
            sub.close()
            daemon.terminate()
            return 1
        print(f"PASS: PAUSED -> RECORDING (states seen: {states})")

    # Send a copy command (should be a no-op since last_transcription is None)
    received.clear()
    sub.copy()
    time.sleep(0.3)
    state_events = [e for e in received if e.get("event") == "state"]
    if state_events:
        print(f"FAIL: copy should not change state, got {state_events}")
        sub.close()
        daemon.terminate()
        return 1
    print("PASS: copy with no transcription is a no-op (no state events)")

    # Pause again, then quit
    sub.pause()
    time.sleep(0.2)

    sub.close()
    daemon.terminate()
    try:
        daemon.wait(timeout=5)
    except subprocess.TimeoutExpired:
        daemon.kill()

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())