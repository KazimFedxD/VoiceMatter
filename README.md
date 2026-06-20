# VoiceMatter

VoiceMatter is a voice dictation tool for Linux that records speech,
transcribes it, formats it with an LLM, copies the result to the
clipboard, and can automatically paste it into the active application.

---

## Requirements

### Required

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [PipeWire](https://pipewire.org/)
- [WirePlumber](https://pipewire.pages.freedesktop.org/wireplumber/)

### Optional

- [ydotool](https://github.com/ReimuNotMoe/ydotool) (required only for automatic paste)

Without `ydotool`, VoiceMatter still works and copies text to the
clipboard. You can manually paste with:

```text
Ctrl+V
```

---

## Installation

Clone the repository:

```bash
git clone <repo-url>
cd VoiceMatter
```

Create the virtual environment and install dependencies:

```bash
uv sync
```

Activate the environment:

```bash
source .venv/bin/activate
```

Install the `voicematter` command in editable mode:

```bash
uv pip install -e .
```

Verify the install:

```bash
voicematter --help
```

---

## Configure Environment

Create a local `.env` from the template:

```bash
cp .env.example .env
```

The following environment variables are required:

| Variable           | Description                                |
|--------------------|--------------------------------------------|
| `DEEPGRAM_API_KEY` | API key for the speech-to-text provider    |
| `MINIMAX_API_KEY`  | API key for the LLM formatter              |
| `MINIMAX_BASE_URL` | Base URL for the LLM formatter endpoint    |

Example `.env`:

```dotenv
DEEPGRAM_API_KEY=your_deepgram_api_key
MINIMAX_API_KEY=your_llm_api_key
MINIMAX_BASE_URL=https://api.example.com/anthropic
```

---

## Running VoiceMatter

Start the daemon (and overlay) manually:

```bash
voicematter daemon
```

Trigger a recording (start, or stop and process if one is in flight):

```bash
voicematter trigger
```

Pause or resume an active recording:

```bash
voicematter pause
```

Cancel the current recording:

```bash
voicematter cancel
```

Stop the daemon:

```bash
voicematter stop
```

---

## Autostart Using systemd

Create the user service file:

```text
~/.config/systemd/user/voicematter.service
```

Use the absolute path to the installed `voicematter` binary. Find it
with:

```bash
which voicematter
```

Example service:

```ini
[Unit]
Description=VoiceMatter

[Service]
ExecStart=/absolute/path/to/project/.venv/bin/voicematter daemon
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
```

Reload, enable, and start:

```bash
systemctl --user daemon-reload
systemctl --user enable voicematter
systemctl --user start voicematter
```

Check the status:

```bash
systemctl --user status voicematter
```

Follow the logs:

```bash
journalctl --user -u voicematter -f
```

---

## KDE Global Shortcuts

Open:

**System Settings → Keyboard → Shortcuts**

Create custom shortcuts that run the following commands. Use absolute
paths — KDE does not always inherit your shell's `PATH`.

| Action        | Command                                                          |
|---------------|------------------------------------------------------------------|
| Record toggle | `/absolute/path/to/voicematter trigger`                          |
| Pause / resume| `/absolute/path/to/voicematter pause`                            |
| Cancel        | `/absolute/path/to/voicematter cancel`                           |

Suggested bindings:

```text
F8  -> trigger
F9  -> pause
F10 -> cancel
```

---

## Automatic Paste (Optional)

VoiceMatter can paste the formatted text directly into the focused
application using `ydotool`. Without it, VoiceMatter falls back to
clipboard-only.

### Arch

```bash
sudo pacman -S ydotool
```

### Fedora

```bash
sudo dnf install ydotool
```

Enable and start the service:

```bash
sudo systemctl enable ydotool
sudo systemctl start ydotool
```

VoiceMatter automatically falls back to clipboard-only mode if
`ydotool` is unavailable.

---

## Microphone Selection

VoiceMatter uses the system default PipeWire microphone. It does not
take a device index from configuration.

Check the current default source:

```bash
wpctl status
```

Change the default microphone through **KDE System Settings → Audio**
(or `pavucontrol`). VoiceMatter follows the new default automatically
on the next recording.

Do not configure device indices.

---

## Troubleshooting

### `voicematter` command not found

Make sure the virtual environment is active:

```bash
source .venv/bin/activate
which voicematter
```

If it is still missing, reinstall in editable mode:

```bash
uv pip install -e .
```

### Hotkeys do not work

Use the absolute executable path in the KDE shortcut definition, not
just `voicematter`. Test that a shortcut fires with:

```bash
notify-send "VoiceMatter" "Shortcut works"
```

### Microphone not detected

Inspect PipeWire state:

```bash
wpctl status
```

Set the default source through KDE Audio Settings or `pavucontrol`.

### Daemon not running

Check the user service:

```bash
systemctl --user status voicematter
```

If the service is not loaded, re-run:

```bash
systemctl --user daemon-reload
systemctl --user enable --now voicematter
```

### Automatic paste not working

Verify `ydotool` is installed and the service is running:

```bash
ydotool --version
systemctl status ydotool
```

Clipboard copy still works even if automatic paste fails. Paste
manually with `Ctrl+V`.

---

## Verification Checklist

- [ ] VoiceMatter installs successfully
- [ ] `voicematter` command works
- [ ] Daemon starts
- [ ] Microphone records
- [ ] Transcription works
- [ ] Formatted text appears
- [ ] Clipboard copy works
- [ ] Optional automatic paste works
- [ ] Daemon starts automatically after login
- [ ] KDE shortcuts work
