from anthropic import Anthropic
from dotenv import load_dotenv
import os 
import json

load_dotenv()

API_KEY = os.getenv("MINIMAX_API_KEY")
BASE_URL = os.getenv("MINIMAX_BASE_URL")
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "data", "prompt.md")
VARIABLES_PATH = os.path.join(os.path.dirname(__file__), "data", "dict.json")

with open(PROMPT_PATH, "r") as f:
    PROMPT = f.read()

with open(VARIABLES_PATH, "r") as f:
    VARIABLES = json.load(f)

class Formatter:
    def __init__(self):
        self.client = Anthropic(api_key=API_KEY, base_url=BASE_URL)
        
        self.system_prompt = PROMPT + "\n\nVariables:\n" + json.dumps(VARIABLES)
        
    def format(self, text: str) -> str:
        messages = [{"role": "user", "content": text}]
        
        response = self.client.messages.create(
            model="MiniMax-M3",
            max_tokens=10000,
            system=self.system_prompt,
            messages=messages,
        )
        
        for block in response.content:
            if block.type == "thinking":
                print(f"Thinking: {block.text}")
            elif block.type == "text":
                return block.text.strip()
        
        
        
        