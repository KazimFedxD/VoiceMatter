from voicematter import VoiceMatter
from voicematter.events import EventHandler
import sys

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "daemon":
        daemon = VoiceMatter()
        daemon.start_daemon()
    elif arg == "overlay":
        from voicematter.overlay import main as overlay_main
        overlay_main()
    else:
        event_handler = EventHandler("/tmp/voicematter.sock")
        if arg == "stop":
            event_handler.stop()
        elif arg == "trigger":
            event_handler.trigger()
        elif arg == "pause":
            event_handler.pause()
        elif arg == "resume":
            event_handler.resume()
        elif arg in ("help", None):
            print("Usage: python main.py [daemon|overlay|trigger|pause|resume|stop|help]")
        else:
            print(f"Unknown argument: {arg}")