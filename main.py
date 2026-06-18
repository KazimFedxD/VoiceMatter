from voicematter import VoiceMatter
from voicematter.events import EventHandler
import sys

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if not arg:
        vm = VoiceMatter()
        vm.start_daemon()
    else:
        event_handler = EventHandler("/tmp/voicematter.sock")
        if arg == "trigger":
            event_handler.trigger()
        elif arg == "pause":
            event_handler.pause()
        elif arg == "help":
            print("Usage: python main.py [trigger|pause|help]")
        else:
            print(f"Unknown argument: {arg}")
            
    
    