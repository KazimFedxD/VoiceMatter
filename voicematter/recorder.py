import sounddevice as sd
import soundfile as sf
import numpy as np

chunks = []

def callback(indata, frames, time, status):
    chunks.append(indata.copy())

stream = sd.InputStream(
    device=7,
    channels=1,
    samplerate=44100,
    callback=callback,
)

print("Recording...")
stream.start()
input("Press Enter to stop\n")
stream.stop()
stream.close()

audio = np.concatenate(chunks)

sf.write("recording.wav", audio, 44100)

print("Saved")