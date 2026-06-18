from deepgram import DeepgramClient
from dotenv import load_dotenv
import os

load_dotenv()




class Transcriber:
    def __init__(self):
        self.client = DeepgramClient(api_key=os.getenv("DEEPGRAM_API_KEY"))
    
    def transcribe(self, path: str) -> str | None: # change to bytes in the future directly from captured audio
        try:
            with open(path, "rb") as f:
                audio_data = f.read()
                
            response = self.client.listen.v1.media.transcribe_file(
                request=audio_data,
                model="nova-3",
                language="multi",
                smart_format=True
            )
            
            if response.results and response.results.channels:
                transcript = response.results.channels[0].alternatives[0].transcript
                return transcript
            else:
                print("No transcript found in response.")
                return None
        except Exception as e:
            print(f"Error during STT transcription: {e}")
            return None