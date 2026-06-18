---
name: Cleanup quality report
about: The LLM cleanup changed my transcript in a way I didn't expect — wrong drops, hallucinations, bad reordering, wrong mode
title: "[Cleanup]: "
labels: cleanup, llm-prompt, needs-triage
assignees: ''

---

The cleanup step is the *product* — it's the part that turns
"I want apples, no wait kiwi, also grapes" into a clean list.
When the cleanup is wrong, the bug almost always lives in the
prompt, not the STT or the clipboard. This template exists so we
can reproduce the failure exactly and iterate on the prompt.

If your problem is recording, transcription, the clipboard, or the
CLI itself, please file a **Bug report** instead.

## What kind of cleanup problem is this?

- [ ] **Wrong drop** — kept something you retracted, or dropped
  something you meant to keep.
- [ ] **Hallucination** — added words or items that weren't in the
  transcript.
- [ ] **Wrong reordering** — changed the order of items / sentences
  in a way that lost your intent.
- [ ] **Wrong mode** — you asked for a list, got a paragraph (or
  vice versa).
- [ ] **Grammar over-correction** — fixed something that was
  actually fine, or changed your voice in a way you didn't want.
- [ ] **Missed correction** — left a retraction / duplicate /
  false start in place that should have been cleaned up.
- [ ] **Style file ignored** — your `style.toml` rules weren't
  applied.
- [ ] **Other** — describe below.

## Raw transcript

Paste the transcript *before* cleanup. The LLM never sees your
audio — only this text — so this is the input we need to reproduce.

```
<paste raw transcript here>
```

If you have the audio file, attaching it is even better. Drop the
`.wav` / `.mp3` here so we can re-run STT ourselves.

## What you wanted the cleanup to produce

Paste or describe what you expected the cleaned output to be.

```
<paste expected cleaned output here>
```

## What the cleanup actually produced

Paste or describe what landed in your clipboard.

```
<paste actual cleaned output here>
```

## Configuration at the time

- **Mode preset**: [ `list` / `paragraph` / `sentence` / `email` /
  `code comment` / `custom:<name>` / `default` ]
- **LLM provider + model**: [ e.g. `openai:gpt-4o-mini`,
  `groq:llama-3.3-70b`, `ollama:llama3.1:8b` ]
- **Temperature** (if you set one): `____`
- **Style file**: [ none / path — paste contents ]
- **VoiceMatter version**: `voicematter --version` → `____`

## How often does this happen?

- [ ] Every time, on every input — fully reproducible
- [ ] Often (more than half the time) with similar input
- [ ] Sometimes — only on this specific phrasing
- [ ] Only happened once

## Additional context

Anything else — your language, accent, microphone, whether the
problem gets worse with long transcripts, etc. The more we can
narrow down the trigger, the faster the prompt gets fixed.