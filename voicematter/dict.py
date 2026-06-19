import json
import os

DICT_PATH = os.path.join(os.path.dirname(__file__), "data", "dict.json")

class DictManager:
    def __init__(self):
        self._dict: dict[str, str] = {}
        self.load()

    def load(self):
        try:
            with open(DICT_PATH, "r", encoding="utf-8") as f:
                self._dict = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._dict = {}

    def save(self):
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(self._dict, f, ensure_ascii=False, indent=2)

    def get(self, key: str) -> str | None:
        return self._dict.get(key)

    def set(self, key: str, value: str):
        self._dict[key] = value
        self.save()
        
    def delete(self, key: str):
        if key in self._dict:
            del self._dict[key]
            self.save()
    
    def all(self) -> dict[str, str]:
        return self._dict.copy()