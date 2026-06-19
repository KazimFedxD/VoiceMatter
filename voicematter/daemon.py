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
                os._exit(0)
            elif action == "trigger":
                self.handle_trigger()
            elif action == "pause":
                self.handle_pause()
            elif action == "resume":
                self.handle_resume()
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
                    elif action == "copy":
                        self.handle_copy()
                    elif action == "trigger":
                        self.handle_trigger()
                    elif action == "stop":
                        debug("Stopping daemon...")
                        os._exit(0)
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
            self.recorder.start_recording()
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
        debug(f"Current state: {self.state}")
        if self.state == State.RECORDING:
            self.recorder.pause()
            self.state = State.PAUSED
            self.emit("state", state=self.state.value)
            debug("Recording paused.")

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

    # ---------- audio level emitter ----------

    def _start_level_emitter(self):
        def loop():
            while self.state in (State.RECORDING, State.PAUSED):
                self.emit("level", level=self.recorder.level)
                time.sleep(LEVEL_EMIT_INTERVAL)
        threading.Thread(target=loop, daemon=True).start()

    # ---------- processing pipeline ----------

    def process_audio(self):
        with self._processing_lock:
            try:
                audio_data = self.recorder.stop_recording()
                buffer = BytesIO()
                sf.write(buffer, audio_data, self.recorder.samplerate, format="WAV")
                buffer.seek(0)
                transcription = self.transcriber.transcribe(buffer.read())
                print(f"Transcription: {transcription}")

                if not transcription:
                    debug("No transcription received.")
                    self.last_transcription = None
                    self.state = State.IDLE
                    self.emit("state", state=self.state.value)
                    self.emit("error", message="No transcription received")
                    return

                self.last_transcription = transcription
                formatted_text = self.formatter.format(transcription)
                print(f"Formatted Text: {formatted_text}")

                self.writer.write(formatted_text)

                self.state = State.IDLE
                self.emit("state", state=self.state.value)
                self.emit("ready", text=formatted_text)
            except Exception as e:
                debug(f"Processing failed: {e}")
                self.state = State.IDLE
                self.emit("state", state=self.state.value)
                self.emit("error", message=str(e))


if __name__ == "__main__":
    daemon = VoiceMatterDaemon()
    daemon.start_daemon()