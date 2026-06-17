# VoiceMatter

> Press-to-record voice dictation that *thinks* about what you meant.

Hold a key, talk, release. VoiceMatter records your voice, transcribes
the audio, and then runs the raw transcript through an LLM to fix
the things humans actually do when they speak out loud — mid-sentence
corrections, false starts, "uh"s, last-minute swaps, trailing thoughts.
The output is a clean list, paragraph, or sentence you can paste
anywhere.

---

## The problem with raw transcripts

Speech-to-text is honest. Maybe too honest. Talk into a microphone
and STT will give you back exactly what you said, mistakes and all:

> *"I want apples, kiwi, strawberry, no strawberry, banana, melons,
> and — wait not banana — melons, also grapes"*

That's the literal transcript. It's also useless if you wanted a
grocery list. STT captured your words perfectly. It just didn't
understand them.

VoiceMatter is the layer between the transcript and your destination.
It uses an LLM to *interpret* what you said, applying the same
corrections a human listener would:

> - apples
> - kiwi
> - strawberry
> - melons
> - grapes

The LLM dropped `banana` (twice — you retracted it both times), kept
`strawberry` (you retracted it once, then re-added it by context),
and ordered the list roughly by what you said. No magic, no rules
engine, just a model that reads the transcript like a person would.

---

## How it works

```
┌─────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────┐
│  MIC    │──▶│  Transcribe  │──▶│  LLM Clean   │──▶│ Output  │
│ (hold   │   │  (STT)       │   │  (format)    │   │ (clip-  │
│  key)   │   │              │   │              │   │ board)  │
└─────────┘   └──────────────┘   └──────────────┘   └─────────┘
```

1. **Record** — Hotkey is held down; audio is captured from the
   default input device. Released = stop.
2. **Transcribe** — The audio buffer is sent to a speech-to-text
   provider and converted to a raw text transcript.
3. **Clean** — The transcript is sent to an LLM with a prompt that
   asks it to apply human-style corrections, fix grammar, and emit
   the result in the target shape (list / paragraph / sentence).
4. **Emit** — The cleaned text lands in the system clipboard,
   ready to paste.

The whole round-trip from key-release to clipboard should take
1–3 seconds on a normal machine.

---

## What the LLM actually does

The cleanup prompt is the product. It tells the model to behave like
a careful listener who:

- **Drops retractions.** *"X, no not X, Y"* → keep Y only.
- **Resolves duplicates.** *"X, also X"* → keep one X.
- **Reorders for clarity.** Sometimes the order in which you thought
  of items is not the order that reads well.
- **Fixes grammar.** *"i want apple and banana"* → *"apples and
  bananas"* (or just *"apples, bananas"* in a list).
- **Respects scope.** If you said *"make a list"*, emit a list. If
  you said *"write me a paragraph"*, emit a paragraph. The mode is
  configurable.
- **Does not invent.** If the transcript says *"... and something
  else"*, the cleanup does not hallucinate what the something else
  is. It either omits the placeholder or flags it as `[unclear]`.

The model never sees your voice, only the transcript. This is
intentional — it keeps the LLM context small (a few hundred tokens
of transcript + a system prompt is enough) and the response fast.

---

## Planned features

- **Hotkey-driven dictation** — global hotkey, works in any focused
  text field.
- **Mode presets** — *list*, *paragraph*, *sentence*, *email*,
  *code comment*. Each preset has a tailored cleanup prompt.
- **Per-user style** — a small "style" file the user can edit to
  teach the model their quirks (e.g. *"I always say 'um' — strip
  those"*, *"I prefer British spelling"*).
- **History** — last N dictations, searchable, with the raw
  transcript + cleaned output side-by-side so you can see what the
  LLM did.
- **Streaming** — the LLM response streams into the clipboard so
  long outputs feel instant.
- **Local model option** — for offline / privacy use, swap the
  cloud LLM for a local one (Ollama, llama.cpp, etc.).

---

## Tech stack (planned)

| Layer        | Choice                          | Why                                     |
|--------------|---------------------------------|-----------------------------------------|
| Language     | Python 3.11+                    | already pinned in `.python-version`     |
| Audio I/O    | `sounddevice` + `soundfile`     | cross-platform mic capture, no PyAudio   |
| STT          | Deepgram (streaming + batch)    | fast, accurate, has a free tier          |
| LLM          | OpenAI-compatible chat API      | works with OpenAI, Together, Groq, etc. |
| CLI          | `typer` + `rich`                | clean UX, auto `--help`                  |
| Config       | `pydantic-settings`             | env vars + `.env` file, type-safe        |
| Packaging    | `uv`                            | fast resolver, `pyproject.toml` native  |

---

## Status

**Scaffold only.** No source code, no dependencies installed, no
implementation yet. The directory contains the `uv init` skeleton
plus this README and the planned description in `pyproject.toml`.

Next steps (not started):
1. Wire up `sounddevice` for mic capture
2. Add Deepgram STT client
3. Add OpenAI-compatible LLM client
4. Build the typer CLI (`dictate`, `transcribe <file>`, `config`)
5. Write the cleanup prompt + a `style.toml` for user preferences
6. End-to-end smoke test

See `pyproject.toml` for the planned package name (`voicematter`)
and version (`0.1.0`).
