from __future__ import annotations

import sounddevice as sd
import numpy as np


class Recorder:
    def __init__(self, device: int = 7, channels: int = 1, samplerate: int = 44100):
        self.device = device
        self.channels = channels
        self.samplerate = samplerate

        self.paused = False
        # RMS audio level, updated every callback. 0.0 = silence, ~1.0 = loud speech.
        # Computed from raw int16-range float samples produced by sounddevice.
        self.level = 0.0

        self.chunks: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None

    def callback(self, indata, frames, time, status):
        # Always update level so the meter reflects silence too — keeps the UI alive.
        rms = float(np.sqrt(np.mean(indata ** 2)))
        # Raw speech typically peaks around 0.2-0.4 RMS; scale up so the meter
        # visibly reacts without saturating on loud sounds.
        self.level = min(1.0, rms * 3.0)

        if self.paused:
            return
        self.chunks.append(indata.copy())

    def start_recording(self):
        print("Recording...")

        self.chunks.clear()
        self.paused = False
        self.level = 0.0

        self.stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=self.samplerate,
            callback=self.callback,
        )

        self.stream.start()

    def stop_recording(self):
        print("Stopping recording...")
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.level = 0.0
        audio_data = np.concatenate(self.chunks, axis=0)
        return audio_data

    def pause(self):
        if self.paused:
            return
        self.paused = True
        print("Pausing recording...")

    def resume(self):
        if not self.paused:
            return
        self.paused = False
        print("Resuming recording...")