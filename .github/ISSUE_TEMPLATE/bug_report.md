---
name: Bug report
about: Something in VoiceMatter is broken — recording, transcription, cleanup, or the CLI
title: "[Bug]: "
labels: bug, needs-triage
assignees: ''

---

Thanks for taking the time to report this. VoiceMatter has three
distinct stages (record → transcribe → clean), and the same symptom
usually has different causes depending on which stage fails. The
questions below help us route your report to the right place.

## Where in the pipeline is the problem?

Tell us which stage is misbehaving — this is the single most useful
piece of information in this report.

- [ ] **Recording** — wrong audio device, no audio captured,
  hotkey doesn't fire, recording won't stop, distorted audio, etc.
- [ ] **Transcription** — STT returns wrong text, misses words,
  returns empty, errors out, times out, etc.
- [ ] **Cleanup (LLM)** — raw transcript is fine, but the cleaned
  output is wrong (drops the wrong words, hallucinates, wrong mode,
  wrong grammar, etc.).
- [ ] **Output / clipboard** — cleaned text never lands in the
  clipboard, lands in the wrong app, formatting is lost, etc.
- [ ] **CLI / config** — `dictate`, `transcribe`, or `config`
  commands error out, `--help` is wrong, env vars not honored, etc.
- [ ] **Other** — please describe below.

## Describe the bug

A clear and concise description of what went wrong.

## Steps to reproduce

1. Run command: `voicematter ...` (paste the exact command)
2. Press hotkey: `____` (e.g. `ctrl+shift+space`)
3. Say: `____` (the words you spoke)
4. See: `____` (what happened — error, wrong text, nothing)

## Expected behavior

What you expected to happen instead.

## Actual output

Paste the **raw transcript** and the **cleaned output** if you have
them. Even a partial transcript is useful.

- **Raw transcript** (from STT, before cleanup):
  ```
  <paste here>
  ```
- **Cleaned output** (after LLM, what landed in the clipboard):
  ```
  <paste here>
  ```

If the cleaned output is the bug, please also note what you would
have expected it to be.

## Environment

- **VoiceMatter version**: `voicematter --version` → `____`
- **Python version**: `python --version` → `____`
- **OS**: [e.g. Ubuntu 24.04, macOS 15, Windows 11]
- **Architecture**: [e.g. x86_64, arm64]

## Configuration

- **Mode preset**: [ `list` / `paragraph` / `sentence` / `email` /
  `code comment` / `custom:<name>` / `default` ]
- **STT provider**: [ `deepgram` / `whisper` / `local:<name>` /
  `other` ]
- **LLM provider**: [ `openai` / `groq` / `together` / `ollama` /
  `other` ]
- **Style file**: [ none / `~/.config/voicematter/style.toml` /
  in-repo path — paste contents if non-trivial ]
- **Audio input device**: [ system default / device name from
  `voicematter config devices` ]
- **Hotkey**: [ e.g. `ctrl+shift+space` ]

## Logs

If you ran with verbose logging, paste the relevant lines here.
Remove any API keys before pasting.

```
<paste logs here>
```

## Additional context

Anything else that might help — first time it happened, frequency,
related issues, screenshots, etc.