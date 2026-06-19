"""End-to-end test for processing-step events emitted by the daemon.

Spawns the daemon with a stubbed pipeline (no real audio / Deepgram / Anthropic
calls), walks a full recording -> processing cycle, and asserts that the four
processing steps (transcribe, format, copy, insert) emit `step` events in
order, and that the pipeline completes with a `ready` event.

This test does NOT exercise the actual audio path or external services. It
uses a real `Recorder` but monkey-patches `Transcriber.transcribe`,
`Formatter.format`, `Writer.copy`, and `Writer.paste` to instant no-ops so the
daemon runs the full `process_audio` code path.
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
from collections import deque
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Allow running headless on systems without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from voicematter.events import Subscriber


STUB_TRANSCRIPTION = "hello world"
STUB_FORMATTED = "Hello, world!"


def main():
    sock_path = "/tmp/voicematter.sock"
    if os.path.exists(sock_path):
        os.remove(sock_path)

    # Inject a small bootstrap script that monkey-patches the four external
    # dependencies, then runs the daemon as usual. We do this by overriding
    # `python -c` before running `main.py`.
    bootstrap = (
        "import sys, os, voicematter.daemon as d, voicematter.recorder as r, "
        "voicematter.transcriber as t, voicematter.formatter as f, "
        "voicematter.writer as w; "
        # Recorder.start_recording should be a no-op so we don't actually open audio.
        "r.Recorder.start_recording = lambda self: None; "
        "r.Recorder.stop_recording = lambda self: __import__('numpy').zeros((1600,), dtype='float32'); "
        "r.Recorder.level = 0.0; "
        "r.Recorder.samplerate = 16000; "
        "r.Recorder.pause = lambda self: None; "
        "r.Recorder.resume = lambda self: None; "
        # Transcriber returns a stub string.
        f"t.Transcriber.transcribe = lambda self, data: '{STUB_TRANSCRIPTION}'; "
        f"f.Formatter.format = lambda self, text: '{STUB_FORMATTED}'; "
        # Writer.copy and Writer.paste are no-ops.
        "w.Writer.copy = lambda self, text: None; "
        "w.Writer.paste = lambda self: None; "
        # Trick main.py into thinking it was invoked as `python main.py daemon`.
        "sys.argv = ['main.py', 'daemon']; "
        # Now exec the daemon main.
        "exec(open('main.py').read(), {'__name__': '__main__', 'sys': sys})"
    )

    daemon = subprocess.Popen(
        ["uv", "run", "python", "-c", bootstrap],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )

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

    # Wait for initial state=idle
    time.sleep(0.3)
    if not any(e.get("event") == "state" and e.get("state") == "idle" for e in received):
        print(f"FAIL: no initial state=idle event, got {list(received)}")
        sub.close(); daemon.terminate()
        return 1
    print("PASS: initial state=idle event received")

    # IDLE -> RECORDING
    received.clear()
    sub.trigger()
    time.sleep(0.4)
    if not any(e.get("event") == "state" and e.get("state") == "recording" for e in received):
        print(f"FAIL: did not enter recording, got {list(received)}")
        sub.close(); daemon.terminate()
        return 1
    print("PASS: IDLE -> RECORDING")

    # RECORDING -> PROCESSING (and pipeline runs to completion)
    received.clear()
    sub.trigger()
    time.sleep(1.5)  # generous wait for the (stubbed) pipeline

    steps_seen = [
        (e.get("name"), e.get("status"))
        for e in received
        if e.get("event") == "step"
    ]
    print(f"Step events observed: {steps_seen}")

    expected = [
        ("transcribe", "started"),
        ("transcribe", "done"),
        ("format", "started"),
        ("format", "done"),
        ("copy", "started"),
        ("copy", "done"),
        ("insert", "started"),
        ("insert", "done"),
    ]
    if steps_seen != expected:
        print(f"FAIL: expected step order {expected}, got {steps_seen}")
        sub.close(); daemon.terminate()
        return 1
    print(f"PASS: all 4 step events fire in correct order")

    # Should have a ready event with the stub formatted text
    if not any(e.get("event") == "ready" and e.get("text") == STUB_FORMATTED for e in received):
        print(f"FAIL: no ready event with stub text, got {list(received)}")
        sub.close(); daemon.terminate()
        return 1
    print(f"PASS: ready event with stub text received")

    # And state should be back to idle
    if not any(e.get("event") == "state" and e.get("state") == "idle" for e in received):
        print(f"FAIL: state did not return to idle, got {[e for e in received if e.get('event')=='state']}")
        sub.close(); daemon.terminate()
        return 1
    print("PASS: state returned to idle after ready")

    sub.close()
    daemon.terminate()
    try:
        daemon.wait(timeout=5)
    except subprocess.TimeoutExpired:
        daemon.kill()

    print("\nALL STEP-EVENT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
