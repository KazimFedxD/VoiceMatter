from __future__ import annotations

import socket
import os
import json
import threading
import time

from enum import Enum
from typing import Any

from io import BytesIO
import soundfile as sf

from helper import debug

from .transcriber import Transcriber
from .recorder import Recorder
from .formatter import Formatter
from .writer import Writer

SOCKET_PATH = "/tmp/voicematter.sock"

LEVEL_EMIT_INTERVAL = 0.05  # 20 Hz level updates while recording


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    PROCESSING = "processing"


class VoiceMatterDaemon:
    def __init__(self):
        self.state = State.IDLE
        self.last_transcription: str | None = None

        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.formatter = Formatter()
        self.writer = Writer()

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.settimeout(None)

        self._subscribers: list[socket.socket] = []
        self._subscribers_lock = threading.Lock()
        self._processing_lock = threading.Lock()
        self._cancel_requested: bool = False
        self._shutdown_event = threading.Event()

        self.setup_daemon()

    def setup_daemon(self):
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        self.server.bind(SOCKET_PATH)
        self.server.listen(5)

    # ---------- pub/sub ----------

    def emit(self, event: str, **payload: Any):
        """Best-effort broadcast to all subscribers. Dead sockets are pruned."""
        msg = (json.dumps({"event": event, **payload}) + "\n").encode()
        with self._subscribers_lock:
            dead: list[socket.socket] = []
            for sub in self._subscribers:
                try:
                    sub.sendall(msg)
                except OSError:
                    dead.append(sub)
            for d in dead:
                self._subscribers.remove(d)

    # ---------- connection handling ----------

    def start_daemon(self):
        debug("VoiceMatter Daemon started. Listening for events...")
        while True:
            conn, _ = self.server.accept()
            threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                daemon=True,
            ).start()

    def _handle_connection(self, conn: socket.socket):
        try:
            data = conn.recv(4096)
            if not data:
                return
            first_line = data.split(b"\n", 1)[0]
            try:
                msg = json.loads(first_line.decode())
            except json.JSONDecodeError:
                debug("Received invalid JSON data.")
                return

            action = msg.get("action")

            if action == "subscribe":
                # Persistent connection: keep reading commands, push events.
                self._serve_subscriber(conn)
                return

            # One-shot command path (existing CLI behavior).
            if action == "stop":
                debug("Stopping daemon...")
                self._request_shutdown()
            elif action == "trigger":
                self.handle_trigger()
            elif action == "pause":
                self.handle_pause()
            elif action == "resume":
                self.handle_resume()
            elif action == "cancel":
                self.handle_cancel()
            elif action == "copy":
                self.handle_copy()
            else:
                debug(f"Unknown action: {action}")
        except Exception as e:
            debug(f"Connection error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _serve_subscriber(self, conn: socket.socket):
        """Run a persistent subscriber session: send events, accept commands."""
        with self._subscribers_lock:
            self._subscribers.append(conn)

        # Sync the overlay with current state on connect.
        self.emit("state", state=self.state.value)

        try:
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode())
                    except json.JSONDecodeError:
                        continue
                    action = msg.get("action")
                    if action == "pause":
                        self.handle_pause()
                    elif action == "resume":
                        self.handle_resume()
                    elif action == "cancel":
                        self.handle_cancel()
                    elif action == "copy":
                        self.handle_copy()
                    elif action == "trigger":
                        self.handle_trigger()
                    elif action == "stop":
                        debug("Stopping daemon...")
                        self._request_shutdown()
        except OSError:
            pass
        finally:
            with self._subscribers_lock:
                if conn in self._subscribers:
                    self._subscribers.remove(conn)
            try:
                conn.close()
            except OSError:
                pass

    # ---------- commands ----------

    def handle_trigger(self):
        debug(f"Current state: {self.state}")
        if self.state == State.IDLE:
            self.state = State.RECORDING
            self.emit("state", state=self.state.value)
            try:
                self.recorder.start_recording()
            except Exception as e:
                # Audio failed to start (e.g. bad device/channel config). Roll back
                # to IDLE so subsequent commands still work and stay subscribed.
                debug(f"start_recording failed: {e}")
                self.state = State.IDLE
                self.emit("state", state=self.state.value)
                self.emit("error", message=f"Recording failed to start: {e}")
                return
            self._start_level_emitter()
            debug("Recording started.")
        elif self.state == State.RECORDING or self.state == State.PAUSED:
            self.state = State.PROCESSING
            self.emit("state", state=self.state.value)
            debug("Recording stopped. Processing audio...")
            threading.Thread(target=self.process_audio, daemon=True).start()
        elif self.state == State.PROCESSING:
            debug("Currently processing. Cannot trigger recording.")

    def handle_pause(self):
        """Toggle pause on the active recording. RECORDING ↔ PAUSED."""
        debug(f"Pause toggle. Current state: {self.state}")
        if self.state == State.RECORDING:
            self.recorder.pause()
            self.state = State.PAUSED
            self.emit("state", state=self.state.value)
            debug("Recording paused.")
        elif self.state == State.PAUSED:
            self.recorder.resume()
            self.state = State.RECORDING
            self.emit("state", state=self.state.value)
            debug("Recording resumed.")

    def handle_resume(self):
        debug(f"Current state: {self.state}")
        if self.state == State.PAUSED:
            self.recorder.resume()
            self.state = State.RECORDING
            self.emit("state", state=self.state.value)
            debug("Recording resumed.")

    def handle_copy(self):
        """Re-copy the last transcription (used by the overlay's success button)."""
        if self.last_transcription:
            self.writer.copy(self.last_transcription)
            print("Text re-copied to clipboard (overlay button)")
        else:
            debug("handle_copy called with no buffered transcription.")

    def handle_cancel(self):
        """Drop in-flight audio and return to idle. Used by compositor-bound Esc."""
        debug(f"Cancel requested. Current state: {self.state}")
        if self.state == State.IDLE:
            return
        if self.state in (State.RECORDING, State.PAUSED):
            try:
                self.recorder.stop_recording()
            except Exception as e:
                debug(f"stop_recording during cancel raised: {e}")
            self.state = State.IDLE
            self.emit("state", state=self.state.value)
        elif self.state == State.PROCESSING:
            # Soft cancel: flag is checked between processing steps.
            self._cancel_requested = True

    def _request_shutdown(self):
        """Emit shutdown, ask Qt to quit, fall back to hard exit after 500ms."""
        debug("Shutdown requested.")
        self._shutdown_event.set()
        try:
            self.emit("shutdown")
        except Exception as e:
            debug(f"emit shutdown raised: {e}")
        # Try graceful Qt shutdown if running in the same process.
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception:
            pass
        # Fall back to hard exit after a grace period.
        threading.Timer(0.5, os._exit, args=[0]).start()

    # ---------- audio level emitter ----------

    def _start_level_emitter(self):
        def loop():
            while self.state in (State.RECORDING, State.PAUSED):
                self.emit("level", level=self.recorder.level)
                time.sleep(LEVEL_EMIT_INTERVAL)
        threading.Thread(target=loop, daemon=True).start()

    # ---------- processing pipeline ----------

    def process_audio(self):
        self._cancel_requested = False
        with self._processing_lock:
            try:
                audio_data = self.recorder.stop_recording()
                if self._cancel_requested:
                    self._cancel_to_idle()
                    return

                buffer = BytesIO()
                sf.write(buffer, audio_data, self.recorder.samplerate, format="WAV")
                buffer.seek(0)

                self.emit("step", name="transcribe", status="started")
                transcription = self.transcriber.transcribe(buffer.read())
                self.emit("step", name="transcribe", status="done")
                if self._cancel_requested:
                    self._cancel_to_idle()
                    return

                if not transcription:
                    debug("No transcription received.")
                    self.last_transcription = None
                    self._emit_error_idle("No transcription received")
                    return

                self.last_transcription = transcription
                print(f"Transcription: {transcription}")

                self.emit("step", name="format", status="started")
                formatted_text = self.formatter.format(transcription)
                self.emit("step", name="format", status="done")
                if self._cancel_requested:
                    self._cancel_to_idle()
                    return
                print(f"Formatted Text: {formatted_text}")

                self.emit("step", name="copy", status="started")
                self.writer.copy(formatted_text)
                self.emit("step", name="copy", status="done")
                if self._cancel_requested:
                    self._cancel_to_idle()
                    return

                self.emit("step", name="insert", status="started")
                self.writer.paste()
                self.emit("step", name="insert", status="done")

                self.state = State.IDLE
                self.emit("state", state=self.state.value)
                self.emit("ready", text=formatted_text)
            except Exception as e:
                debug(f"Processing failed: {e}")
                self._emit_error_idle(str(e))

    def _cancel_to_idle(self):
        """Used by process_audio when cancel is requested between steps."""
        self.state = State.IDLE
        self.emit("state", state=self.state.value)
        self.emit("error", message="Cancelled")

    def _emit_error_idle(self, msg: str):
        """Common path: go to idle and surface an error to the overlay."""
        self.state = State.IDLE
        self.emit("state", state=self.state.value)
        self.emit("error", message=msg)


if __name__ == "__main__":
    daemon = VoiceMatterDaemon()
    daemon.start_daemon()