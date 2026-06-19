from __future__ import annotations

import socket
import json
import threading
from typing import Any, Callable, Optional


class EventHandler:
    """One-shot client for sending commands to the daemon.

    Opens a fresh connection per command. Used by the CLI (`main.py trigger`,
    `main.py pause`, etc.) and by external hotkey wrappers.
    """

    def __init__(self, path: str):
        self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.client.connect(path)

    def send_event(self, action: str, **kwargs: Any):
        payload: dict[str, Any] = {"action": action, **kwargs}
        self.client.send(json.dumps(payload).encode())

    def trigger(self):
        self.send_event("trigger")

    def pause(self):
        self.send_event("pause")

    def resume(self):
        self.send_event("resume")

    def stop(self):
        self.send_event("stop")


class Subscriber:
    """Persistent subscriber to daemon events. Used by the overlay.

    Sends a `subscribe` message on connect, then keeps the socket open. The
    daemon pushes newline-delimited JSON events; the subscriber reads them on
    a background thread and invokes the supplied callback for each event.
    Commands (pause, resume, copy, trigger) are sent on the same socket.
    """

    def __init__(self, path: str, on_event: Callable[[dict[str, Any]], None]):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(path)
        self._sock.sendall((json.dumps({"action": "subscribe"}) + "\n").encode())
        self._on_event = on_event
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._send_lock = threading.Lock()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        buf = b""
        try:
            while self._running:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        event: dict[str, Any] = json.loads(line.decode())
                        self._on_event(event)
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass

    def send_command(self, action: str, **kwargs: Any):
        payload: dict[str, Any] = {"action": action, **kwargs}
        data = (json.dumps(payload) + "\n").encode()
        with self._send_lock:
            try:
                self._sock.sendall(data)
            except OSError:
                pass

    def pause(self):
        self.send_command("pause")

    def resume(self):
        self.send_command("resume")

    def copy(self):
        self.send_command("copy")

    def trigger(self):
        self.send_command("trigger")

    def close(self):
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass