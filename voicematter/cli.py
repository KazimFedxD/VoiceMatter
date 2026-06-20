"""VoiceMatter CLI entry point.

Default (no arg) and `daemon`: start the daemon AND the overlay in one
process. The overlay is hidden in idle and appears automatically when the
daemon transitions to a non-idle state.

The compositor is expected to bind the following hotkeys per the design:
  F8  -> python main.py trigger
  F9  -> python main.py pause   (toggle: RECORDING <-> PAUSED)
  Esc -> python main.py cancel
"""

from __future__ import annotations

import sys
import threading

from voicematter import VoiceMatter
from voicematter.events import EventHandler
from voicematter.overlay import main as overlay_main

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "daemon":
        # Daemon + overlay in one process.
        try:
            d = VoiceMatter()
            threading.Thread(
                target=d.start_daemon, daemon=True, name="vm-accept"
            ).start()
            overlay_main()
        except KeyboardInterrupt:
            EventHandler("/tmp/voicematter.sock").stop()
    elif arg == "trigger":
        EventHandler("/tmp/voicematter.sock").trigger()
    elif arg == "pause":
        EventHandler("/tmp/voicematter.sock").pause()
    elif arg == "resume":
        EventHandler("/tmp/voicematter.sock").resume()
    elif arg == "cancel":
        EventHandler("/tmp/voicematter.sock").send_event("cancel")
    elif arg == "stop":
        EventHandler("/tmp/voicematter.sock").stop()
    elif arg == "dict":
        newarg = sys.argv[2] if len(sys.argv) > 2 else None
        if newarg is None:
            print(
                "Usage: python main.py dict get <key>\n"
                "       python main.py dict set <key> <value>\n"
                "       python main.py dict all\n"
                "       python main.py dict delete <key>\n"
                "\n"
            )
        elif newarg == "get":
            key = sys.argv[3] if len(sys.argv) > 3 else None
            if key in (None, "help", "-h", "--help"):
                print("Usage: python main.py dict get <key>")
            else:
                from voicematter.dict import DictManager

                dm = DictManager()
                value = dm.get(key)
                if value is not None:
                    print(value)
                else:
                    print(f"Key not found: {key}")
        elif newarg == "set":
            key = sys.argv[3] if len(sys.argv) > 3 else None
            value = sys.argv[4] if len(sys.argv) > 4 else None
            if key is None or value is None:
                print("Usage: python main.py dict set <key> <value>")
            else:
                from voicematter.dict import DictManager

                dm = DictManager()
                dm.set(key, value)
                print(f"Set {key} = {value}")
        elif newarg == "all":
            from voicematter.dict import DictManager

            dm = DictManager()
            if not dm.all():
                print("Dictionary is empty.")
            for key, value in dm.all().items():
                print(f"{key}: {value}")
        elif newarg == "delete":
            key = sys.argv[3] if len(sys.argv) > 3 else None
            if key in (None, "help", "-h", "--help"):
                print("Usage: python main.py dict delete <key>")
            else:
                from voicematter.dict import DictManager

                dm = DictManager()
                dm.delete(key)
                print(f"Deleted key: {key}")
        else:
            print(f"Unknown dict command: {newarg}")
    elif arg in ("help", "-h", "--help", None):
        print(
            "Usage: python main.py [daemon|trigger|pause|resume|cancel|stop|help]\n"
            "\n"
            "  (no arg) / daemon : start daemon + overlay together (one process)\n"
            "  trigger           : start recording, or stop and process\n"
            "  pause             : toggle pause on the active recording\n"
            "  resume            : resume a paused recording\n"
            "  cancel            : drop in-flight audio, return to idle\n"
            "  stop              : stop the daemon\n"
        )
    else:
        print(f"Unknown argument: {arg}")
if __name__ == "__main__":
    main()