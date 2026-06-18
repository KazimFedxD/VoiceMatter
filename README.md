# VoiceMatter

> Press-to-record voice dictation that *thinks* about what you meant.

**Built for Wayland on Linux.** Hold a key, talk, release. VoiceMatter
records your voice, transcribes the audio, and then runs the raw
transcript through an LLM to fix the things humans actually do when
they speak out loud — mid-sentence corrections, false starts,
"uh"s, last-minute swaps, trailing thoughts. The output is a clean
list, paragraph, or sentence you can paste anywhere.

---

## Platform support

VoiceMatter is **built for and primarily tested on Wayland Linux**.
Other platforms are not in scope for this project — if you don't
run Wayland, this is probably not the tool for you.

| Platform           | Status                                                  |
|--------------------|---------------------------------------------------------|
| **Wayland Linux**  | Primary target — designed for this                     |
| X11 Linux          | Not a target. May work coincidentally, will not be fixed|
| macOS / Windows    | Not supported, no plans to add                          |

"Wayland Linux" means a Linux distribution running a Wayland
compositor — GNOME, KDE Plasma 6, Sway, Hyprland, River, COSMIC,
etc. — with PipeWire (or PulseAudio as fallback) for audio and
`wl-clipboard` utilities on `$PATH`.

If you want a cross-platform dictation tool, look elsewhere.
VoiceMatter leans into the Wayland stack on purpose; see
[Why Wayland](#why-wayland-linux) below.

---

## Why Wayland Linux?

Three reasons.

1. **The hotkey problem has a clean answer on Wayland.** X11 let
   any process grab global keys. Wayland's security model makes
   that impossible by design, and replaces it with explicit
   compositor-mediated hotkeys (`wlr-layer-shell`, KDE's
   `KGlobalAcceld`, GNOME's `mutter` keybindings, etc.). This is
   the right design — but it means a Wayland-native tool talks
   directly to the compositor instead of fighting it.
2. **The clipboard story is small and composable.** `wl-copy` and
   `wl-paste` from `wl-clipboard` are 100-line C utilities. A
   `subprocess.Popen(["wl-copy"], stdin=...)` is the entire
   integration. There's no platform abstraction to maintain.
3. **The user base is here.** The people who care about a 1–3
   second press-to-record loop with LLM cleanup are mostly people
   who already picked their Linux distro and their compositor
   deliberately. Building for them is more honest than pretending
   to also support macOS.

Wayland being the target also means VoiceMatter will *not* ship
X11 fallbacks, Windows builds, or macOS workarounds. If those
platforms matter to you, please fork — the codebase is small.

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
│ (hold   │   │  (STT)       │   │  (format)    │   │ (wl-    │
│  key)   │   │              │   │              │   │  copy)  │
└─────────┘   └──────────────┘   └──────────────┘   └─────────┘
```

1. **Record** — Hotkey is held down; audio is captured from the
   default input device via PipeWire. Released = stop.
2. **Transcribe** — The audio buffer is sent to a speech-to-text
   provider and converted to a raw text transcript.
3. **Clean** — The transcript is sent to an LLM with a prompt that
   asks it to apply human-style corrections, fix grammar, and emit
   the result in the target shape (list / paragraph / sentence).
4. **Emit** — The cleaned text is piped into `wl-copy`, landing in
   the Wayland clipboard, ready to paste.

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

## Wayland-specific implementation notes

These are the bits that make VoiceMatter Wayland-native rather
than "runs on Linux sometimes." The implementation may change as
the codebase grows, but the dependencies won't.

- **Global hotkey.** Bound through the compositor's native keybinding
  mechanism, not through X11-style key grabbing. Concretely:
  - GNOME / KDE → D-Bus service registering with the desktop's
    keybinding daemon (`mutter` / `KGlobalAcceld`).
  - wlroots-based compositors (Sway, Hyprland, River, COSMIC) →
    `wlr-layer-shell` surface that catches keys itself, or a
    compositor-specific config snippet.
  - The exact interface is `voicematter hotkey bind <compositor>`,
    which writes the right config for the running session.
- **Clipboard.** `wl-copy` from `wl-clipboard`, fed via stdin.
  Tool selection is honoured automatically (text vs. image mime
  negotiation), so apps that only read the primary selection still
  work.
- **Audio.** `sounddevice` talks to PortAudio, which on a modern
  Wayland desktop talks to PipeWire. PipeWire's default-source
  mapping is respected — pick your input in `wpctl` / `pavucontrol`
  and VoiceMatter uses it. PulseAudio-only systems are supported
  as a fallback but not the development target.
- **Display protocol.** VoiceMatter does not draw any UI in v0.1;
  everything happens through the hotkey + clipboard. When a
  tray / status window shows up later, it will use
  `wlr-layer-shell` so it integrates cleanly with all compositors.

If any of this stops working on a specific Wayland compositor,
that's a bug — file it (see `Bug report` template). VoiceMatter's
promise is "works on the Wayland Linux desktop," not "might work
on some of them."

---

## Planned features

- **Hotkey-driven dictation** — global hotkey bound through the
  compositor, works in any focused text field.
- **Mode presets** — *list*, *paragraph*, *sentence*, *email*,
  *code comment*. Each preset has a tailored cleanup prompt.
- **Per-user style** — a small `style.toml` the user can edit to
  teach the model their quirks (e.g. *"I always say 'um' — strip
  those"*, *"I prefer British spelling"*).
- **History** — last N dictations, searchable, with the raw
  transcript + cleaned output side-by-side so you can see what the
  LLM did.
- **Streaming** — the LLM response streams into the clipboard so
  long outputs feel instant.
- **Local model option** — for offline / privacy use, swap the
  cloud LLM for a local one (Ollama, llama.cpp, etc.). Runs
  on the same PipeWire / Wayland stack with no UI changes.
- **Compositor-aware hotkey setup** — `voicematter hotkey bind`
  detects the running compositor and writes the right config
  (Sway config, Hyprland binds, GNOME dconf, KDE shortcuts, …).

---

## Tech stack (planned)

| Layer        | Choice                              | Why                                                |
|--------------|-------------------------------------|----------------------------------------------------|
| Language     | Python 3.11+                        | already pinned in `.python-version`                |
| Display      | **Wayland** (via compositor APIs)   | primary target — see [Why Wayland](#why-wayland-linux) |
| Audio I/O    | `sounddevice` + `soundfile` over **PipeWire** | PortAudio → PipeWire is the modern Wayland default |
| Clipboard    | `wl-copy` (wl-clipboard)            | native Wayland, ~100 LOC, no abstraction needed    |
| STT          | Deepgram (streaming + batch)        | fast, accurate, has a free tier                    |
| LLM          | OpenAI-compatible chat API          | works with OpenAI, Together, Groq, local Ollama    |
| CLI          | `typer` + `rich`                    | clean UX, auto `--help`                            |
| Config       | `pydantic-settings`                 | env vars + `.env` file, type-safe                  |
| Packaging    | `uv`                                | fast resolver, `pyproject.toml` native             |

---

## Status

**Scaffold only.** No source code, no dependencies installed, no
implementation yet. The directory contains the `uv init` skeleton
plus this README and the planned description in `pyproject.toml`.

Next steps (not started):
1. Wire up `sounddevice` for mic capture via PipeWire
2. Add `wl-copy` integration for the clipboard stage
3. Pick a compositor (GNOME first, since it's the most common) and
   write the hotkey-binding code path
4. Add Deepgram STT client
5. Add OpenAI-compatible LLM client
6. Build the typer CLI (`dictate`, `transcribe <file>`, `config`,
   `hotkey bind`)
7. Write the cleanup prompt + a `style.toml` for user preferences
8. End-to-end smoke test on GNOME / Sway / Hyprland

See `pyproject.toml` for the planned package name (`voicematter`)
and version (`0.1.0`).

---

## Contributing

Issues and PRs welcome, with one rule: **VoiceMatter stays on
Wayland Linux.** Don't open PRs adding X11 fallbacks, Windows
builds, or macOS shims — they'd just bloat the codebase for a
platform we don't test on. If you want one of those, fork the
project; it's small.

Use the templates in `.github/ISSUE_TEMPLATE/`. There's a
dedicated **Cleanup quality report** template for prompt issues
— that's usually the right place if "the LLM did the wrong thing
to my text."