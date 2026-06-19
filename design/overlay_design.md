# VoiceMatter Overlay — Design Reference

> Visual + behavioral specification for the floating overlay window.
> Source asset: `design/overlay-design.png` (top-level mockup showing four primary states).
> Implementation: `voicematter/overlay.py` (PySide6 / Qt6).

This document extracts every state shown in the design mockup, plus the state the
codebase models that the mockup doesn't render (error). Use it as the single
source of truth for visual / behavioral changes to the overlay.

---

## 1. Design Philosophy (tagline from mockup)

> **Minimal • Always on top • Never steals focus • Auto-hides**

These four properties drive every decision below. If a proposed change breaks one
of them, it doesn't ship.

| Property            | What it means in practice                                                            |
| ------------------- | ------------------------------------------------------------------------------------ |
| Minimal             | Pill shape, single row of content, no chrome (no title bar, no close, no menu).      |
| Always on top       | `Qt.WindowStaysOnTopHint` + `Qt.Tool` flag — survives alt-tab, no taskbar entry.      |
| Never steals focus  | `Qt.WA_ShowWithoutActivating` — appears without pulling focus from the active app.  |
| Auto-hides          | The overlay is **not always visible**. It hides on `idle`, hides on dismiss, and     |
|                     | the success state has a 2-second auto-close.                                         |

---

## 2. Container — Shared Across All States

| Property            | Value                                                                  |
| ------------------- | ---------------------------------------------------------------------- |
| Shape               | Rounded pill (corner radius 22 px)                                     |
| Width × Height      | 280 × 64 px                                                            |
| Background fill     | `#111827` at 235/255 alpha (gray-900, near-opaque)                     |
| Border              | 1 px white at 30/255 alpha (subtle, 1 px inset)                        |
| Position            | Lower-middle of primary screen, ~62% down the screen height            |
| Layout              | Horizontal: mic icon (40 × 40, left) + 12 px gap + action button (flex) |
| Window flags        | `FramelessWindowHint | WindowStaysOnTopHint | Tool`                   |
| Background          | Translucent (`WA_TranslucentBackground`), pill drawn manually in `paintEvent` |
| Drop shadow         | None (per "minimal" — system-drawn shadows are not used)               |

The pill is **transparent outside its rounded rect** so it never looks like a
squared floating window on busy backgrounds.

---

## 3. State Inventory

The mockup renders four states. The code (`overlay.py`) models six — the two
extra are `idle` and `error`, included here for completeness.

| # | State       | Trigger                          | Visible? | Mockup? |
| - | ----------- | -------------------------------- | -------- | ------- |
| 1 | `idle`      | No dictation in flight           | Hidden   | No      |
| 2 | `recording` | Hotkey pressed, mic capturing    | Shown    | Yes     |
| 3 | `paused`    | User pressed Pause / F9          | Shown    | Yes     |
| 4 | `processing`| Audio captured, STT/LLM running  | Shown    | Yes     |
| 5 | `ready`     | Text cleaned, copied to clipboard| Shown    | Yes (as "Success") |
| 6 | `error`     | Daemon reported an error         | Shown    | No (code only) |

---

## 4. State 1 — `idle`

**Visible:** No. The overlay is hidden.

**Notes:** This state is intentionally invisible. The user should not know the
overlay exists until they press the hotkey. No tray icon, no notification, no
dock entry.

---

## 5. State 2 — `recording`  *(mockup: top-left)*

### Visual

- **Mic icon (left):** 40 × 40 circle, fill `#EF4444` (red-500).
  White mic glyph (rounded mic body + U-shaped stand) centered.
  Two vertical white pause bars overlay the mic glyph.
- **Reactive audio bars:** Six small vertical bars below the mic, white at
  ~85% alpha. Heights modulated in real time by the daemon's `level` events
  (range 0.0–1.0), passed through a low-pass smoother (`+= (target - current) * 0.25`).
- **Title text:** "Recording" — red (`#EF4444`), bold.
- **Timer (right):** "00:12" — `mm:ss` format, white, mono-feel, top-right of pill.
- **Subtitle (below):** "Speak clearly..." — muted gray (`#9CA3AF` / gray-400), small.
- **Action button:** Label "Pause" — red fill (matches mic), white text.
  Key chip "F9" on the left, label on the right.

### Keyboard shortcuts

| Key      | Action       |
| -------- | ------------ |
| `F8`     | Stop (terminate recording, transition to `processing`) |
| `F9`     | Pause (transition to `paused`)                            |
| `Esc`    | Cancel (drop audio, transition to `idle` / hidden)        |

### Behavior

- Audio level updates drive the six reactive bars in real time (~30 fps tick).
- Title color is the same red as the mic — the whole left side reads as
  "active recording" at a glance.
- Timer increments every 100 ms; format is zero-padded `mm:ss`.

---

## 6. State 3 — `paused`  *(mockup: bottom-right)*

### Visual

- **Mic icon (left):** 40 × 40 circle, fill `#F59E0B` (amber-500).
  White mic glyph with **pause overlay** (two vertical bars across the mic body)
  in place of the reactive audio bars.
- **Audio bars:** Six amber-tinted bars at frozen level (last seen level on
  pause). They do **not** animate in this state.
- **Title text:** "Paused" — amber (`#F59E0B`), bold.
- **Timer (right):** "00:45" — keeps counting elapsed time but reads as
  "frozen" because nothing else moves.
- **Subtitle (below):** "Recording paused" — muted gray, small.
- **Action button:** Label "Resume" — amber fill, white text.
  Key chip "F8" on the left, label on the right.

### Keyboard shortcuts

| Key      | Action       |
| -------- | ------------ |
| `F8`     | Resume (transition to `recording`)  |
| `Esc`    | Cancel (drop audio, transition to `idle`) |

### Behavior

- The pause overlay on the mic icon is the key visual cue — it tells the user
  the recording is suspended, not stopped.
- Audio bars are frozen at the last level, not zeroed, so the user has a sense
  of the level they were at when they paused.

---

## 7. State 4 — `processing`  *(mockup: top-right)*

### Visual

- **Mic icon (left):** 40 × 40 circle, fill `#3B82F6` (blue-500).
  White **loading ring** of 12 dots around the perimeter (spinner ring).
- **Title text:** "Processing..." — blue (`#3B82F6`), bold.
- **Progress checklist (right column, replaces the audio bars):**
  1. **Transcribing audio** — icon: audio waveform (`📊`/waveform glyph, blue). Status: ✓ (done).
  2. **Formatting text** — icon: sparkles (`✨` glyph, blue). Status: animated spinner (◐/◓/◑/◒ cycle at ~30 fps).
  3. **Copying to clipboard** — icon: clipboard (`📋` glyph, gray). Status: pending (empty circle).
  4. **Inserting text** — icon: text-cursor (`📝` glyph, gray). Status: pending.
- **Action button:** Label "Processing…" with leading spinner glyph (cycles ◐→◓→◑→◒). Button is **disabled** (50% opacity, no hover state). Blue fill, white text.

### Animation

- Spinner ring of dots on the mic icon: rotates ~30 fps.
- Spinner glyph in the button text: advances every frame.
- Checklist items light up as the daemon reports sub-state events.

### Behavior

- This is the longest state in normal use. The checklist tells the user *what
  is happening*, which is the difference between "feels frozen" and "feels
  alive". Don't remove the checklist.
- Disabled button prevents double-clicks. The user cannot cancel mid-processing
  (the daemon owns the workflow at this point).

---

## 8. State 5 — `ready`  *(mockup: bottom-left, labeled "Success")*

### Visual

- **Mic icon (left):** 40 × 40 circle, fill `#10B981` (emerald-500).
  White **checkmark** (✓) glyph centered.
- **Title text:** "Text inserted" — emerald (`#10B981`), bold.
- **Subtitle (below title):** "Copied to clipboard" — muted gray, small.
- **Progress bar (below subtitle):** A thin emerald line (height 2 px) that
  fills left-to-right over **2 seconds** — a visual countdown to auto-dismiss.
- **Helper text (below progress bar):** "Overlay will close in 2 seconds..."
  — muted gray, small, centered.
- **Action button:** "Copy to clipboard" — emerald fill, white text. (Re-copies
  the last transcription; useful if the user already pasted elsewhere.)

### Animation

- Progress bar: 2-second linear fill, then auto-`hide()` and transition to `idle`.
- The button stays clickable for the full 2 seconds; if clicked, re-copies and
  immediately dismisses.

### Behavior

- The 2-second auto-dismiss is the core "auto-hides" property in action. The
  user has time to read the success message but does not need to dismiss it.
- Re-copy on click: if the user alt-tabbed and missed the auto-paste, clicking
  the button pastes again without recording again.

---

## 9. State 6 — `error`  *(code only, not in mockup)*

### Visual

- **Mic icon (left):** 40 × 40 circle, fill `#DC2626` (red-600) — darker red
  than `recording` so it's distinguishable.
- **Title text:** "Error — dismiss" — red (`#DC2626`), bold.
- **Subtitle (below):** Error message string from the daemon (max ~80 chars,
  ellipsize beyond).
- **Action button:** "Error — dismiss" — red-600 fill, white text.

### Behavior

- This state is rare and only fires when the daemon itself errors (mic
  permission denied, STT 5xx, LLM 4xx, etc.).
- Click dismisses and returns to `idle`. There is no retry from the overlay —
  the user re-triggers the hotkey to retry.

---

## 10. Color Tokens (canonical)

These match `overlay.py` and Tailwind v3 / v4 conventions. Use these tokens,
not the raw hex, in any new code or design asset.

| Token              | Hex       | Used in               |
| ------------------ | --------- | --------------------- |
| `bg-pill`          | `#111827` | Pill background (gray-900, 235 alpha) |
| `border-pill`      | `rgba(255,255,255,0.12)` | 1 px pill border       |
| `text-primary`     | `#F9FAFB` | Title text, timer     |
| `text-muted`       | `#9CA3AF` | Subtitle, helper text (gray-400) |
| `text-disabled`    | `rgba(255,255,255,0.85)` | Disabled button label  |
| `state-idle`       | `#1F2937` | Mic idle (gray-800)   |
| `state-recording`  | `#EF4444` | Mic + "Recording" (red-500) |
| `state-paused`     | `#F59E0B` | Mic + "Paused" (amber-500) |
| `state-processing` | `#3B82F6` | Mic + "Processing" (blue-500) |
| `state-ready`      | `#10B981` | Mic + "Text inserted" (emerald-500) |
| `state-error`      | `#DC2626` | Mic + "Error" (red-600) |

### Button states (per state color)

| State    | Default (95% alpha) | Hover (100% alpha) | Pressed (-20 RGB) | Disabled (55% alpha) |
| -------- | ------------------- | ------------------ | ----------------- | -------------------- |
| Red      | `rgba(239,68,68,0.95)`  | `rgba(239,68,68,1.0)`   | `rgba(219,48,48,1.0)`  | `rgba(239,68,68,0.55)`  |
| Amber    | `rgba(245,158,11,0.95)` | `rgba(245,158,11,1.0)`  | `rgba(225,138,0,1.0)`  | `rgba(245,158,11,0.55)` |
| Blue     | `rgba(59,130,246,0.95)` | `rgba(59,130,246,1.0)`  | `rgba(39,110,226,1.0)` | `rgba(59,130,246,0.55)` |
| Emerald  | `rgba(16,185,129,0.95)` | `rgba(16,185,129,1.0)`  | `rgba(0,165,109,1.0)`  | `rgba(16,185,129,0.55)` |
| Red-600  | `rgba(220,38,38,0.95)`  | `rgba(220,38,38,1.0)`   | `rgba(200,18,18,1.0)`  | `rgba(220,38,38,0.55)`  |

---

## 11. Typography

The mockup uses the system default. `overlay.py` sets `QFont("Sans", 10, QFont.Medium)`
on the button and the title is rendered in the system default — no custom
font is loaded. Keep it that way for the demo, but if you add a brand font,
these are the roles:

| Role           | Size  | Weight  | Notes                          |
| -------------- | ----- | ------- | ------------------------------ |
| Title          | 14 px | 600     | State name ("Recording", etc.) |
| Timer          | 13 px | 500     | Monospaced-feel `mm:ss`        |
| Subtitle       | 11 px | 400     | Muted                          |
| Helper text    | 10 px | 400     | Muted, centered                |
| Button label   | 12 px | 600     | White on state-color           |
| Key chip       | 10 px | 700     | Monospaced, slightly raised    |

---

## 12. Spacing & Sizing

| Dimension            | Value       |
| -------------------- | ----------- |
| Pill height          | 64 px       |
| Pill width           | 280 px      |
| Pill corner radius   | 22 px       |
| Mic icon size        | 40 × 40 px  |
| Mic inner circle     | 36 px diameter |
| Mic body             | 8 × 14 px, 4 px radius |
| Button height        | 36 px       |
| Button corner radius | 18 px (half height) |
| Button padding       | 0 18 px     |
| Audio bar width      | 2.5 px      |
| Audio bar count      | 6 (3 each side of mic) |
| Pill left/right margin | 12 px     |
| Pill top/bottom margin | 14 px     |
| Mic ↔ button gap     | 12 px       |
| Progress bar height  | 2 px        |

---

## 13. Animation Timings

| Animation                  | Duration / rate        | Easing       |
| -------------------------- | ---------------------- | ------------ |
| Reactive audio bars        | 30 fps tick            | Linear per-frame, low-pass smoothed |
| Processing spinner glyph   | 30 fps tick            | Stepped (4 glyphs) |
| Processing dot ring        | 30 fps tick            | Continuous rotation |
| Progress bar countdown     | 2000 ms                | Linear       |
| State transition (show)    | Instant (no fade)      | n/a          |
| State transition (hide)    | Instant (no fade)      | n/a          |

The mockup is intentionally a still. The implementation adds the motion listed
above. When tweaking timings, prefer keeping animations **sub-perceptual for
state changes** (instant on/off) and **legible for in-state motion** (audio
bars, spinners, countdown).

---

## 14. State Transitions

```
        ┌──────┐
        │ idle │  (hidden)
        └──┬───┘
           │ hotkey pressed
           ▼
     ┌──────────┐ F9 / Pause btn   ┌────────┐
     │ recording├─────────────────►│ paused │
     └─┬────────┘ F8 / Resume btn  └────┬───┘
       │                               │ Esc / Cancel
       │ F8 / Stop                    ▼
       ▼                            (back to idle)
  ┌────────────┐
  │ processing │
  └─────┬──────┘
        │ success
        ▼
    ┌──────┐  2s auto  ┌──────┐
    │ ready├──────────►│ idle │
    └──┬───┘  click    └──────┘
       │ error
       ▼
    ┌──────┐  click  ┌──────┐
    │ error├─────────►│ idle │
    └──────┘         └──────┘
```

Transitions are owned by the daemon. The overlay only renders the current
state — it does not animate between states (no crossfades, no morphs).

---

## 15. Open Questions / Future Work

- **Light theme:** All states assume a dark pill on a light-or-dark background.
  A `state-idle` glyph that flips to white when on light backgrounds is not
  yet implemented. The `idle` state is hidden so it doesn't matter today.
- **Vertical / mobile layout:** The pill is fixed 280 × 64 and assumes a wide
  screen. Mobile / portrait layouts would need a stacked variant.
- **Localization:** The 80-char error truncation and the timer format
  (`mm:ss`) are not localized. Add `mm:ss` → locale-aware formatting when
  non-en-US ships.
- **Reduced motion:** The audio bars, spinners, and progress bar are pure
  decoration. A `prefers-reduced-motion` user setting should freeze the
  audio bars and replace the progress bar countdown with a static "Auto-closing"
  hint.
- **Error retry:** A "Try again" affordance on the `error` state would be nicer
  than dismissing + re-hotkey. Low priority.

---

## 16. File Manifest

| Path                          | Purpose                                 |
| ----------------------------- | --------------------------------------- |
| `design/overlay-design.png`   | The source mockup (this file documents)  |
| `design/overlay_design.md`    | This document                           |
| `voicematter/overlay.py`      | Implementation (PySide6, all 6 states)  |
| `voicematter/events.py`       | Daemon ↔ overlay event protocol         |

If you change the implementation, update this document in the same PR.
If you change the visual design (mockup), update the tokens in §10 and
the canonical colors in `overlay.py` to match.
