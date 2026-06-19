import subprocess


class Writer:

    def copy(self, text: str):
        subprocess.run(
            ["wl-copy"],
            input=text,
            text=True,
            check=True,
        )
    
    def paste(self):
        subprocess.run(
        ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
        check=False
        )
    
    def write(self, text:str):
        self.copy(text)
        print("Text copied to clipboard")
        self.paste()
        print("Text pasted into active application")
        
