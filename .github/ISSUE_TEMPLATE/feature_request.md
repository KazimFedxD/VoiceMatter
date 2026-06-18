---
name: Feature request
about: Suggest an idea for VoiceMatter — new mode preset, hotkey behavior, pipeline stage, or prompt tweak
title: "[Feature]: "
labels: enhancement, needs-triage
assignees: ''

---

Thanks for the suggestion. VoiceMatter is intentionally small, so
before we add anything we want to understand the *job* it's trying
to do, not just the shape of the feature.

## What category does this fall into?

Pick the closest fit. Most requests live in one of these buckets.

- [ ] **Mode preset** — a new `list` / `paragraph` / `sentence` /
  `email` / `code comment` flavor, or tweaks to an existing one's
  cleanup prompt.
- [ ] **Hotkey / input** — different or smarter hotkey, push-to-talk
  vs toggle, multi-hotkey routing, etc.
- [ ] **Audio / recording** — different sample rate, device picker,
  noise suppression, VAD, etc.
- [ ] **STT** — provider support (Whisper, AssemblyAI, local),
  streaming vs batch, language hints, etc.
- [ ] **LLM cleanup** — prompt changes, new cleanup behaviors,
  model selection, etc.
- [ ] **Local model** — offline support, Ollama / llama.cpp
  integration, model recommendations, etc.
- [ ] **History / UX** — searchable history, side-by-side raw vs
  cleaned view, undo, etc.
- [ ] **Streaming** — token-by-token clipboard updates, partial
  results, etc.
- [ ] **Style file** — new fields, per-app rules, etc.
- [ ] **CLI / packaging** — flags, output formats, install methods,
  Homebrew / pip / uv distribution, etc.
- [ ] **Other** — describe below.

## Is your feature request related to a problem?

A clear and concise description of what problem this solves.
*"I'm always frustrated when [...]. I'd love it if [...]. Currently
I have to [...]."*

## Describe the solution you'd like

What you want to be able to do, and what you'd expect the
experience to look like. A short worked example (input transcript
→ expected cleaned output) is the most useful thing you can include.

## Describe alternatives you've considered

Other approaches you've thought about or already tried — manual
post-editing, a different tool, a different hotkey, etc.

## Pipeline impact

Does this touch the **recording**, **transcription**, **cleanup**,
or **output** stage? (See the bug report template for the
breakdown.) This helps us figure out where the change goes.

- [ ] Recording
- [ ] Transcription (STT)
- [ ] Cleanup (LLM)
- [ ] Output (clipboard / paste target)
- [ ] CLI / config only — no pipeline change
- [ ] Not sure

## Additional context

Mockups, related issues, links to similar features in other tools,
or anything else that helps us understand the request.