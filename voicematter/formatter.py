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
        
        self.system_messages = [
            {"role": "system", "content": PROMPT},
            {"role": "system", "content": f"Variables: {json.dumps(VARIABLES)}"}
        ]
        
        