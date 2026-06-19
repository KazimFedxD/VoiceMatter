from __future__ import annotations

import socket
import os
import json

from enum import Enum

from io import BytesIO
import soundfile as sf

from helper import debug

from .transcriber import Transcriber
from .recorder import Recorder

SOCKET_PATH = "/tmp/voicematter.sock"

class State(Enum):
    IDLE = 1
    RECORDING = 2
    PROCESSING = 3
    
class VoiceMatterDaemon:
    def __init__(self):
        self.state = State.IDLE
        self.recorder = Recorder()
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
            self.recorder.start_recording()
            debug("Recording started.")
        elif self.state == State.RECORDING:
            self.state = State.PROCESSING
            debug("Recording stopped. Processing audio...")
            self.process_audio()
        elif self.state == State.PROCESSING:
            debug("Currently processing. Cannot trigger recording.")
        
    def handle_pause(self):
        debug(f"Current state: {self.state}")
        if self.state == State.RECORDING:
            self.recorder.pause_recording()
            debug("Recording paused.")
    
    def process_audio(self):
        audio_data = self.recorder.stop_recording()
        buffer = BytesIO()

        sf.write(
            buffer,
            audio_data,
            self.recorder.samplerate,
            format="WAV"
        )

        buffer.seek(0)
        transcription = self.transcriber.transcribe(buffer.read()
                                                    )
        print(f"Transcription: {transcription}")
        self.state = State.IDLE

    
if __name__ == "__main__":
    daemon = VoiceMatterDaemon()
    daemon.start_daemon()
