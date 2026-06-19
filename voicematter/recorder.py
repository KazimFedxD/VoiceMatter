import sounddevice as sd
import soundfile as sf
import numpy as np


class Recorder:
    def __init__(self, device: int = 7, channels: int = 1, samplerate: int = 44100):
        self.device = device
        self.channels = channels
        self.samplerate = samplerate
        
        self.paused = False
    
        self.chunks = []

        self.stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=self.samplerate,
            callback=self.callback,
        )
        
    def callback(self, indata, frames, time, status):
        if self.paused:
            return
        self.chunks.append(indata.copy())


    def start_recording(self):
        print("Recording...")
        self.chunks.clear()
        self.paused = False
        self.stream.start()
    
    def stop_recording(self):
        print("Stopping recording...")
        self.stream.stop()
        audio_data = np.concatenate(self.chunks, axis=0)
        return audio_data
    
    def pause_recording(self):
        self.paused = not self.paused
        print("Pausing recording...") if self.paused else print("Resuming recording...")