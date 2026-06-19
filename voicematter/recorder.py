from __future__ import annotations

import logging

import sounddevice as sd
import numpy as np


class Recorder:
    def __init__(self, device: int = 0, channels: int = 1, samplerate: int = 44100):
        self.device = device
        self.channels = channels
        self.samplerate = samplerate

        self.paused = False
        # RMS audio level, updated every callback. 0.0 = silence, ~1.0 = loud speech.
        # Computed from raw int16-range float samples produced by sounddevice.
        self.level = 0.0

        self.chunks: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None

        self._log = logging.getLogger(__name__)

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

        # Reset any leftover state from a previous (possibly failed) attempt.
        self.chunks.clear()
        self.paused = False
        self.level = 0.0
        self.stream = None

        try:
            stream = sd.InputStream(
                device=self.device,
                channels=self.channels,
                samplerate=self.samplerate,
                callback=self.callback,
            )
        except Exception as e:
            self._log.error("Failed to open audio input stream: %s", e)
            self.stream = None
            raise

        try:
            stream.start()
        except Exception as e:
            self._log.error("Failed to start audio stream: %s", e)
            try:
                stream.close()
            except Exception:
                pass
            self.stream = None
            raise

        self.stream = stream

    def stop_recording(self):
        """Stop the stream and return captured audio.

        Safe to call even if `start_recording` never succeeded: in that case
        `self.stream is None` and we return an empty array. Also tolerates a
        stream that was created but failed to start (close may still raise).
        """
        print("Stopping recording...")
        stream = self.stream
        self.stream = None
        self.level = 0.0
        self.paused = False

        if stream is None:
            # Nothing to stop — clear chunks and return silence.
            self.chunks.clear()
            return np.empty((0, self.channels), dtype=np.float32)

        try:
            try:
                stream.stop()
            except Exception as e:
                self._log.debug("stream.stop() raised (continuing): %s", e)
            try:
                stream.close()
            except Exception as e:
                self._log.debug("stream.close() raised (continuing): %s", e)
        finally:
            pass

        if not self.chunks:
            return np.empty((0, self.channels), dtype=np.float32)
        return np.concatenate(self.chunks, axis=0)

    def pause(self):
        # Safe regardless of stream state — just flip the flag so the callback
        # ignores incoming audio. A subsequent stop_recording will still work.
        if self.paused:
            return
        self.paused = True
        print("Pausing recording...")

    def resume(self):
        # Mirror of pause: always safe, just flip the flag back.
        if not self.paused:
            return
        self.paused = False
        print("Resuming recording...")