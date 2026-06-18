from __future__ import annotations

import socket
import os
import json

from enum import Enum

from helper import debug

from .transcriber import Transcriber

SOCKET_PATH = "/tmp/voicematter.sock"

class State(Enum):
    IDLE = 1
    RECORDING = 2
    PROCESSING = 3
    
class VoiceMatterDaemon:
    def __init__(self):
        self.state = State.IDLE
        self.recorder = None
        self.transcriber = Transcriber()
        self.processor = None
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    
        self.setup_daemon()
        
    def setup_daemon(self):    
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        self.server.bind(SOCKET_PATH)
        self.server.listen(5)
    
    def start_daemon(self):
        debug("VoiceMatter Daemon started. Listening for events...")
        while True:
            conn, _ = self.server.accept()
            data = conn.recv(1024)
            if not data:
                continue
            try:
                event = json.loads(data.decode())
                action = event.get("action")
                if action == "trigger":
                    self.handle_trigger()
                elif action == "pause":
                    self.handle_pause()
                else:
                    debug(f"Unknown action: {action}")
            except json.JSONDecodeError:
                debug("Received invalid JSON data.")
            finally:
                conn.close()
    
    def handle_trigger(self):
        debug(f"Current state: {self.state}")
        if self.state == State.IDLE:
            self.state = State.RECORDING
            debug("Recording started.")
        elif self.state == State.RECORDING:
            self.state = State.PROCESSING
            debug("Recording stopped. Processing audio...")
            transcription = self.transcriber.transcribe("sample-audio-2026-06-17.mp3")
            debug(f"Transcription result: {transcription}")
        elif self.state == State.PROCESSING:
            debug("Currently processing. Cannot trigger recording.")
        
    def handle_pause(self):
        debug(f"Current state: {self.state}")
        if self.state == State.RECORDING:
            debug("Paused or Unpaused | NOT IMPLEMENTED")
        
if __name__ == "__main__":
    daemon = VoiceMatterDaemon()
    daemon.start_daemon()
