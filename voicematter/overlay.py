"""PySide6 overlay window for VoiceMatter.

The overlay is started in the same process as the daemon (see main.py). It
connects to the daemon as a persistent subscriber, listens for state/audio-level
events, and renders a frameless pill at the bottom-middle of the screen.

States (driven by daemon events):
  idle        -> hidden
  recording   -> red mic + pause-bar overlay + audio bars + "Recording" title
                 + mm:ss timer + "Speak clearly..." subtitle +
                 [F8 Stop] [F9 Pause] [Esc Cancel] buttons
  paused      -> amber mic + pause-bar overlay + frozen audio bars +
                 "Paused" title + frozen timer + "Recording paused" subtitle +
                 [F8 Resume] [Esc Cancel] buttons
  processing  -> blue mic + 12-dot spinner ring + "Processing..." title +
                 4-row processing checklist (transcribe / format / copy / insert)
  ready       -> emerald mic + white checkmark + "Text inserted" title +
                 "Copied to clipboard" subtitle + emerald progress bar +
                 2-second auto-dismiss + "Copy to clipboard" button
  error       -> red-600 mic + "Error" title + error message subtitle +
                 [Dismiss] button

Visual source of truth: design/overlay-design.png (PNG overrides prose in
design/overlay_design.md wherever they disagree).
"""

from __future__ import annotations

import sys
import math
import time
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QRectF, QSize
from PySide6.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QPen,
    QPainterPath,
    QFont,
    QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
)

from .events import Subscriber

SOCKET_PATH = "/tmp/voicematter.sock"

# ---- Layout ----
WINDOW_WIDTH = 360
MIC_SIZE = 48
BUTTON_HEIGHT = 36
CORNER_RADIUS = 22
BOTTOM_PADDING = 96          # px above bottom of availableGeometry()
PILL_MARGIN_X = 14
PILL_MARGIN_Y = 14
COLUMN_GAP = 14              # between mic and right column
ROW_GAP = 6                  # between rows in the right column
BUTTON_ROW_GAP = 8
KEY_CHIP_WIDTH = 20

# Per-state heights (auto-grow). Pill is 280 wide and these tall. Tuned to
# match design/overlay-design.png visually — pills are larger than the
# previous draft to give title/timer, content, subtitle, helper, and buttons
# room to breathe.
STATE_HEIGHTS = {
    "recording":  140,
    "paused":     140,
    "processing": 220,       # taller to fit 4-row checklist with breathing room
    "ready":     156,        # progress bar + helper line + button
    "error":     118,
}

# Per-state ring rotation speed for the processing-state mic.
RING_DOT_COUNT = 12

# ---- Color tokens (design/overlay_design.md §10) ----
COLOR_BG_PILL       = QColor(17, 24, 39, 235)        # gray-900
COLOR_BORDER_PILL   = QColor(255, 255, 255, 30)
COLOR_TEXT_PRIMARY  = QColor(249, 250, 251)
COLOR_TEXT_MUTED    = QColor(156, 163, 175)          # gray-400

COLOR_STATE_IDLE        = QColor(31, 41, 55)          # gray-800
COLOR_STATE_RECORDING   = QColor(239, 68, 68)         # red-500
COLOR_STATE_PAUSED      = QColor(245, 158, 11)        # amber-500
COLOR_STATE_PROCESSING  = QColor(59, 130, 246)        # blue-500
COLOR_STATE_READY       = QColor(16, 185, 129)        # emerald-500
COLOR_STATE_ERROR       = QColor(220, 38, 38)         # red-600

# Convenience maps
STATE_COLORS = {
    "idle":       COLOR_STATE_IDLE,
    "recording":  COLOR_STATE_RECORDING,
    "paused":     COLOR_STATE_PAUSED,
    "processing": COLOR_STATE_PROCESSING,
    "ready":      COLOR_STATE_READY,
    "error":      COLOR_STATE_ERROR,
}

# ---- Typography ----
FONT_FAMILY = "Sans"
FONT_TITLE        = (FONT_FAMILY, 15, QFont.DemiBold)
FONT_TIMER        = (FONT_FAMILY, 14, QFont.Medium)
FONT_SUBTITLE     = (FONT_FAMILY, 12, QFont.Normal)
FONT_HELPER       = (FONT_FAMILY, 11, QFont.Normal)
FONT_BUTTON_LABEL = (FONT_FAMILY, 13, QFont.DemiBold)
FONT_BUTTON_CHIP  = ("Monospace", 11, QFont.Bold)
FONT_CHECKLIST    = (FONT_FAMILY, 11, QFont.Normal)


# =====================================================================
# DaemonBridge — marshals daemon events (background thread) onto Qt main.
# =====================================================================
class DaemonBridge(QObject):
    state_changed = Signal(str)
    level_changed = Signal(float)
    ready = Signal(str)
    error = Signal(str)
    step_changed = Signal(str, str)  # name, status
    shutdown_requested = Signal()

    def __init__(self):
        super().__init__()
        self._subscriber: Subscriber | None = None

    def attach(self, subscriber: Subscriber):
        self._subscriber = subscriber

    def on_event(self, event: dict[str, Any]):
        # Runs on the Subscriber's background thread.
        etype = event.get("event")
        if etype == "state":
            self.state_changed.emit(str(event.get("state", "idle")))
        elif etype == "level":
            try:
                self.level_changed.emit(float(event.get("level", 0.0)))
            except (TypeError, ValueError):
                pass
        elif etype == "ready":
            self.ready.emit(str(event.get("text", "")))
        elif etype == "error":
            self.error.emit(str(event.get("message", "")))
        elif etype == "step":
            self.step_changed.emit(
                str(event.get("name", "")),
                str(event.get("status", "")),
            )
        elif etype == "shutdown":
            self.shutdown_requested.emit()

    # ---- outbound commands ----

    def pause(self):
        if self._subscriber:
            self._subscriber.pause()

    def resume(self):
        if self._subscriber:
            self._subscriber.resume()

    def copy(self):
        if self._subscriber:
            self._subscriber.copy()

    def trigger(self):
        if self._subscriber:
            self._subscriber.trigger()

    def cancel(self):
        if self._subscriber:
            self._subscriber.send_command("cancel")


# =====================================================================
# MicView — state-specific mic glyph with audio bars / spinner ring.
# =====================================================================
class MicView(QWidget):
    """Custom-painted mic icon. Renders different glyphs per state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(MIC_SIZE, MIC_SIZE)
        self._state = "idle"
        self._level = 0.0          # smoothed audio level 0..1
        self._phase = 0.0          # animation phase for spinner ring
        self._bg_color = COLOR_STATE_IDLE

    def set_state(self, state: str):
        self._state = state
        self._bg_color = STATE_COLORS.get(state, COLOR_STATE_IDLE)
        self.update()

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))

    def set_phase(self, phase: float):
        self._phase = phase

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # Background circle (always; on top of nothing because the pill is
        # transparent except for the rounded rect drawn by Overlay.paintEvent).
        p.setBrush(QBrush(self._bg_color))
        p.setPen(Qt.NoPen)
        # Inner-circle radius scales with MIC_SIZE (48) so the visible mic
        # circle has the same 3px breathing room the 40px version had.
        radius = 21
        p.drawEllipse(int(cx - radius), int(cy - radius), radius * 2, radius * 2)

        if self._state == "ready":
            self._paint_checkmark(p, cx, cy)
            return

        if self._state == "processing":
            self._paint_mic_glyph(p, cx, cy, with_pause_bars=False)
            self._paint_spinner_ring(p, cx, cy, radius + 2)
            return

        # recording, paused, error: white mic + (for recording/paused) pause bars
        with_pause_bars = self._state in ("recording", "paused")
        self._paint_mic_glyph(p, cx, cy, with_pause_bars=with_pause_bars)

        if self._state == "recording":
            self._paint_audio_bars(p, cx, cy)

    def _paint_mic_glyph(self, p: QPainter, cx: float, cy: float, with_pause_bars: bool):
        # Mic body (rounded rect). Slightly enlarged to match the bigger
        # 48px mic circle while preserving the original glyph proportions.
        p.setBrush(QBrush(QColor("white")))
        p.setPen(Qt.NoPen)
        body_w, body_h = 9, 16
        body_x = cx - body_w / 2
        body_y = cy - body_h / 2 - 1
        path = QPainterPath()
        path.addRoundedRect(int(body_x), int(body_y), int(body_w), int(body_h), 4, 4)
        p.drawPath(path)

        # Mic stand (U-shape)
        p.setPen(QPen(QColor("white"), 1.6))
        p.drawLine(int(cx), int(cy + 8), int(cx), int(cy + 11))
        p.drawArc(int(cx - 6), int(cy + 5), 12, 12, 200 * 16, 140 * 16)

        if with_pause_bars:
            # Pause-bars overlay (two vertical bars across the mic body)
            p.setBrush(QBrush(QColor("white")))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(cx - 4), int(cy - 5), 2.8, 9, 1, 1)
            p.drawRoundedRect(int(cx + 1.2), int(cy - 5), 2.8, 9, 1, 1)

    def _paint_audio_bars(self, p: QPainter, cx: float, cy: float):
        # 3 bars on each side of the mic, modulated by level. Sized for the
        # larger 48px mic — offsets moved out by 2px, bar width nudged up.
        bar_color = QColor(255, 255, 255, 220)
        p.setBrush(QBrush(bar_color))
        p.setPen(Qt.NoPen)
        offsets = [-14, -8, -2, 2, 8, 14]
        for i, dx in enumerate(offsets):
            phase = (i * 0.37) % 1.0
            bar_h = 6 + (self._level * 16) * (0.55 + 0.45 * phase)
            bx = cx + dx - 1.5
            by_top = cy - bar_h / 2 + 16
            p.drawRoundedRect(int(bx), int(by_top), 2.8, int(bar_h), 1, 1)

    def _paint_spinner_ring(self, p: QPainter, cx: float, cy: float, radius: float):
        # 12 dots around the perimeter; opacity fades tail-to-head.
        head = int((self._phase / (2 * math.pi)) * RING_DOT_COUNT) % RING_DOT_COUNT
        for i in range(RING_DOT_COUNT):
            angle = (i / RING_DOT_COUNT) * 2 * math.pi - math.pi / 2
            # Distance behind the head determines alpha.
            distance = (head - i) % RING_DOT_COUNT
            alpha = int(255 * (1.0 - distance / RING_DOT_COUNT) * 0.85 + 60)
            dot_color = QColor(255, 255, 255, max(60, min(255, alpha)))
            p.setBrush(QBrush(dot_color))
            p.setPen(Qt.NoPen)
            dx = cx + radius * math.cos(angle)
            dy = cy + radius * math.sin(angle)
            p.drawEllipse(QRectF(dx - 1.5, dy - 1.5, 3, 3))

    def _paint_checkmark(self, p: QPainter, cx: float, cy: float):
        # Two strokes: a short stroke down-right, then a long stroke up-right.
        # Scaled slightly for the 48px mic.
        p.setPen(QPen(QColor("white"), 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        short_start = (cx - 7, cy + 1)
        short_end = (cx - 1, cy + 7)
        long_end = (cx + 8, cy - 6)
        p.drawLine(int(short_start[0]), int(short_start[1]), int(short_end[0]), int(short_end[1]))
        p.drawLine(int(short_end[0]), int(short_end[1]), int(long_end[0]), int(long_end[1]))


# =====================================================================
# AudioBarRow — 6 reactive audio bars.
# =====================================================================
class AudioBarRow(QWidget):
    """Six vertical bars centered horizontally, heights driven by level."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0
        # Painted bars themselves are ~16px tall, but the widget reserves a
        # 20px slot so the bars sit visually centered inside the row.
        self.setFixedHeight(20)

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        bar_w = 2.5
        spacing = 4
        total_w = 6 * bar_w + 5 * spacing
        x0 = (w - total_w) / 2
        cy = self.height() / 2

        p.setBrush(QBrush(QColor(255, 255, 255, 220)))
        p.setPen(Qt.NoPen)
        for i in range(6):
            phase = (i * 0.37) % 1.0
            bar_h = 6 + (self._level * 14) * (0.55 + 0.45 * phase)
            bx = x0 + i * (bar_w + spacing)
            by_top = cy - bar_h / 2
            p.drawRoundedRect(int(bx), int(by_top), bar_w, int(bar_h), 1, 1)


# =====================================================================
# ProcessingChecklist — 4-row checklist with per-row status icons.
# =====================================================================
SPINNER_GLYPHS = ("◐", "◓", "◑", "◒")

CHECKLIST_ROWS = [
    ("transcribe", "Transcribing audio", "📊"),
    ("format",     "Formatting text",    "✨"),
    ("copy",       "Copying to clipboard","📋"),
    ("insert",     "Inserting text",     "📝"),
]


class ProcessingChecklist(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # status per row: "pending", "running", "done"
        self._statuses: list[str] = ["pending"] * 4
        self._phase = 0.0

    def reset(self):
        self._statuses = ["pending"] * 4
        self.update()

    def update_step(self, name: str, status: str):
        # Map name -> row index
        for i, (n, _, _) in enumerate(CHECKLIST_ROWS):
            if n == name:
                self._statuses[i] = status if status in ("started", "running") else status
                if status == "started":
                    self._statuses[i] = "running"
                elif status == "done":
                    self._statuses[i] = "done"
                self.update()
                return

    def tick(self, phase: float):
        self._phase = phase
        self.update()

    def sizeHint(self) -> QSize:
        # 20px per row, 4px gap between rows (matches paintEvent geometry).
        n = len(CHECKLIST_ROWS)
        return QSize(180, 20 * n + 4 * (n - 1))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = QFont(*FONT_CHECKLIST)
        p.setFont(font)
        fm = QFontMetrics(font)

        row_h = 20
        gap = 4
        x_icon = 0
        x_label = 24
        x_status = self.width() - 18
        cy0 = 0

        for i, (_, label, icon) in enumerate(CHECKLIST_ROWS):
            y = cy0 + i * (row_h + gap)
            cy = y + row_h / 2

            # Icon (state-colored)
            color = STATE_COLORS["processing"]
            if self._statuses[i] == "done":
                color = STATE_COLORS["ready"]
            elif self._statuses[i] == "pending":
                color = COLOR_TEXT_MUTED
            p.setPen(QColor(color))
            p.drawText(QRectF(x_icon, y, 20, row_h), Qt.AlignVCenter | Qt.AlignLeft, icon)

            # Label
            label_color = COLOR_TEXT_PRIMARY if self._statuses[i] != "pending" else COLOR_TEXT_MUTED
            p.setPen(QColor(label_color))
            p.drawText(QRectF(x_label, y, x_status - x_label, row_h),
                       Qt.AlignVCenter | Qt.AlignLeft, label)

            # Status glyph (right-aligned)
            status = self._statuses[i]
            if status == "done":
                glyph = "✓"
                status_color = STATE_COLORS["ready"]
            elif status == "running":
                idx = int((self._phase / (2 * math.pi)) * len(SPINNER_GLYPHS)) % len(SPINNER_GLYPHS)
                glyph = SPINNER_GLYPHS[idx]
                status_color = STATE_COLORS["processing"]
            else:
                glyph = "◌"
                status_color = COLOR_TEXT_MUTED
            p.setPen(QColor(status_color))
            p.drawText(QRectF(x_status, y, 18, row_h), Qt.AlignVCenter | Qt.AlignRight, glyph)


# =====================================================================
# ProgressCountdown — 2s linear fill used in the ready state.
# =====================================================================
class ProgressCountdown(QWidget):
    done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fraction = 0.0
        self._timer: QTimer | None = None
        self.setFixedHeight(4)

    def start(self):
        self._fraction = 0.0
        self.update()
        if self._timer is not None:
            self._timer.stop()
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._advance)
        self._start_time = time.monotonic()
        self._timer.start()

    def stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _advance(self):
        elapsed = time.monotonic() - self._start_time
        self._fraction = min(1.0, elapsed / 2.0)
        self.update()
        if self._fraction >= 1.0:
            self.stop()
            self.done.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        # Track
        p.setBrush(QBrush(QColor(255, 255, 255, 30)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, h // 2 - 1, w, 2, 1, 1)
        # Fill
        fill_w = max(2.0, w * self._fraction)
        p.setBrush(QBrush(STATE_COLORS["ready"]))
        p.drawRoundedRect(0, h // 2 - 1, int(fill_w), 2, 1, 1)


# =====================================================================
# KeyChipButton — button with a monospace key chip + label.
# =====================================================================
class KeyChipButton(QWidget):
    """Compact button that paints a rounded key chip on the left and a label
    on the right. Click signal: `clicked`. Background is set via `set_state_color`.
    """

    clicked = Signal()

    def __init__(self, key: str, label: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._label = label
        self._bg_color = STATE_COLORS["recording"]
        self._hover = False
        self._pressed = False
        self._enabled = True
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(BUTTON_HEIGHT)
        self.setMinimumWidth(self._compute_min_width())

    def _compute_min_width(self) -> int:
        font = QFont(*FONT_BUTTON_CHIP)
        chip_fm = QFontMetrics(font)
        font2 = QFont(*FONT_BUTTON_LABEL)
        label_fm = QFontMetrics(font2)
        return KEY_CHIP_WIDTH + 12 + label_fm.horizontalAdvance(self._label) + 16

    def set_state_color(self, color: QColor):
        self._bg_color = color
        self.update()

    def setEnabled(self, enabled: bool):  # type: ignore[override]
        self._enabled = enabled
        if not enabled:
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.PointingHandCursor)
        self.update()

    def isEnabled(self) -> bool:  # type: ignore[override]
        return self._enabled

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if not self._enabled:
            return
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, event):
        if not self._enabled:
            return
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        radius = BUTTON_HEIGHT // 2

        # Background fill
        r, g, b, _ = self._bg_color.getRgb()
        if not self._enabled:
            alpha = 0.55
        elif self._pressed:
            alpha = 1.0
            r = max(0, r - 20)
            g = max(0, g - 20)
            b = max(0, b - 20)
        elif self._hover:
            alpha = 1.0
        else:
            alpha = 0.95
        p.setBrush(QBrush(QColor(r, g, b, int(255 * alpha))))
        p.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(0, 0, rect.width(), rect.height(), radius, radius)
        p.drawPath(path)

        # Key chip on the left (centered vertically inside the 36px button)
        chip_x = 4
        chip_y = 5
        chip_w = KEY_CHIP_WIDTH
        chip_h = rect.height() - 10
        chip_path = QPainterPath()
        chip_path.addRoundedRect(chip_x, chip_y, chip_w, chip_h, 5, 5)
        chip_bg_alpha = 0 if self._pressed else 80
        chip_border_alpha = 0 if self._pressed else 60
        p.setBrush(QBrush(QColor(0, 0, 0, chip_bg_alpha)))
        p.setPen(QPen(QColor(255, 255, 255, chip_border_alpha), 1))
        p.drawPath(chip_path)

        chip_font = QFont(*FONT_BUTTON_CHIP)
        p.setFont(chip_font)
        p.setPen(QColor(255, 255, 255, 230))
        chip_rect = QRectF(chip_x, chip_y, chip_w, chip_h)
        p.drawText(chip_rect, Qt.AlignCenter, self._key)

        # Label
        label_font = QFont(*FONT_BUTTON_LABEL)
        p.setFont(label_font)
        if self._enabled:
            p.setPen(QColor(255, 255, 255, 255))
        else:
            p.setPen(QColor(255, 255, 255, int(255 * 0.85)))
        label_x = chip_x + chip_w + 6
        label_rect = QRectF(label_x, 0, rect.width() - label_x - 6, rect.height())
        p.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextSingleLine, self._label)


# =====================================================================
# SolidButton — single-label colored button (used for ready / error states).
# =====================================================================
class SolidButton(QWidget):
    clicked = Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._bg_color = STATE_COLORS["ready"]
        self._hover = False
        self._pressed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(BUTTON_HEIGHT)
        font = QFont(*FONT_BUTTON_LABEL)
        fm = QFontMetrics(font)
        self.setMinimumWidth(fm.horizontalAdvance(label) + 36)

    def set_label(self, label: str):
        self._label = label
        font = QFont(*FONT_BUTTON_LABEL)
        fm = QFontMetrics(font)
        self.setMinimumWidth(fm.horizontalAdvance(label) + 36)
        self.update()

    def set_state_color(self, color: QColor):
        self._bg_color = color
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        radius = BUTTON_HEIGHT // 2
        r, g, b, _ = self._bg_color.getRgb()
        if self._pressed:
            alpha = 1.0
            r = max(0, r - 20); g = max(0, g - 20); b = max(0, b - 20)
        elif self._hover:
            alpha = 1.0
        else:
            alpha = 0.95
        p.setBrush(QBrush(QColor(r, g, b, int(255 * alpha))))
        p.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(0, 0, rect.width(), rect.height(), radius, radius)
        p.drawPath(path)

        font = QFont(*FONT_BUTTON_LABEL)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(rect, Qt.AlignCenter, self._label)


# =====================================================================
# Overlay — the floating pill window.
# =====================================================================
class Overlay(QWidget):
    def __init__(self, socket_path: str = SOCKET_PATH):
        super().__init__()

        # Window flags
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # State
        self._state = "idle"
        self._target_level = 0.0
        self._smoothed_level = 0.0
        self._phase = 0.0
        self._recording_started_at: float | None = None
        self._paused_total = 0.0           # total seconds spent paused
        self._pause_started_at: float | None = None
        self._last_text = ""
        self._last_error = ""

        # Build child widgets
        self._build_ui()

        # Initial fixed size (will be re-sized per state)
        self.setFixedSize(WINDOW_WIDTH, STATE_HEIGHTS["recording"])

        # Daemon bridge + subscriber
        self.bridge = DaemonBridge()
        self.bridge.state_changed.connect(self._on_state)
        self.bridge.level_changed.connect(self._on_level)
        self.bridge.ready.connect(self._on_ready)
        self.bridge.error.connect(self._on_error)
        self.bridge.step_changed.connect(self._on_step)
        self.bridge.shutdown_requested.connect(self._on_shutdown)
        self._subscriber = Subscriber(socket_path, self.bridge.on_event)
        self.bridge.attach(self._subscriber)
        self._subscriber.start()

        # Auto-dismiss timer for the ready state
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(2000)
        self._dismiss_timer.timeout.connect(self.dismiss)

        # 30 fps tick for animation + recording timer
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self.tick)
        self._tick_timer.start(33)

        # Apply initial state (will hide if state is idle)
        self._apply_state()

    # ---- UI construction ----

    def _build_ui(self):
        # Root layout: [MicView | right column]
        root = QHBoxLayout(self)
        root.setContentsMargins(PILL_MARGIN_X, PILL_MARGIN_Y, PILL_MARGIN_X, PILL_MARGIN_Y)
        root.setSpacing(COLUMN_GAP)

        self.mic_view = MicView(self)
        root.addWidget(self.mic_view, 0, Qt.AlignVCenter)

        # Right column
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(ROW_GAP)

        # Row 1: title + timer
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.title_label = QLabel("")
        self.title_label.setFont(QFont(*FONT_TITLE))
        title_row.addWidget(self.title_label, 1)
        self.timer_label = QLabel("")
        self.timer_label.setFont(QFont(*FONT_TIMER))
        self.timer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.timer_label.setMinimumWidth(50)
        title_row.addWidget(self.timer_label, 0, Qt.AlignRight)
        right_col.addLayout(title_row)

        # Row 2: content stack (audio bars / checklist / progress / empty)
        self.content_stack = QStackedWidget(self)
        self.audio_bars = AudioBarRow(self.content_stack)
        self.content_stack.addWidget(self.audio_bars)             # 0: recording/paused
        self.checklist = ProcessingChecklist(self.content_stack)
        self.content_stack.addWidget(self.checklist)              # 1: processing
        self.progress = ProgressCountdown(self.content_stack)
        self.progress.done.connect(self.dismiss)
        self.content_stack.addWidget(self.progress)               # 2: ready
        self.content_stack.addWidget(QWidget(self.content_stack))  # 3: error / idle placeholder
        right_col.addWidget(self.content_stack)

        # Row 3: subtitle
        self.subtitle_label = QLabel("")
        self.subtitle_label.setFont(QFont(*FONT_SUBTITLE))
        right_col.addWidget(self.subtitle_label)

        # Row 4: helper text (only used in ready state)
        self.helper_label = QLabel("")
        self.helper_label.setFont(QFont(*FONT_HELPER))
        self.helper_label.setAlignment(Qt.AlignCenter)
        self.helper_label.setVisible(False)
        right_col.addWidget(self.helper_label)

        # Row 5: buttons
        self.button_row = QHBoxLayout()
        self.button_row.setContentsMargins(0, 0, 0, 0)
        self.button_row.setSpacing(BUTTON_ROW_GAP)
        # Buttons are created lazily per state
        self._current_buttons: list[QWidget] = []
        right_col.addLayout(self.button_row)

        right_col.addStretch(0)
        root.addLayout(right_col, 1)

    # ---- positioning ----

    def _position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + screen.height() - self.height() - BOTTOM_PADDING
        self.move(x, y)

    # ---- event handlers ----

    def _on_state(self, state: str):
        prev = self._state
        self._state = state
        # Track timer boundaries
        now = time.monotonic()
        if state == "recording":
            if prev == "paused" and self._pause_started_at is not None:
                # Resume: account for paused duration
                self._paused_total += now - self._pause_started_at
                self._pause_started_at = None
            elif prev == "idle":
                self._recording_started_at = now
                self._paused_total = 0.0
        elif state == "paused":
            self._pause_started_at = now
        elif state == "idle":
            self._recording_started_at = None
            self._paused_total = 0.0
            self._pause_started_at = None
        self._apply_state()

    def _on_level(self, level: float):
        self._target_level = max(0.0, min(1.0, level))

    def _on_ready(self, text: str):
        self._last_text = text
        self._state = "ready"
        self._apply_state()

    def _on_error(self, message: str):
        self._last_error = message
        self._state = "error"
        self._apply_state()

    def _on_step(self, name: str, status: str):
        self.checklist.update_step(name, status)

    def _on_shutdown(self):
        QApplication.instance().quit()

    # ---- 30 fps tick ----

    def tick(self):
        # Smooth level
        self._smoothed_level += (self._target_level - self._smoothed_level) * 0.25
        self._phase = (self._phase + 0.18) % (2 * math.pi)

        if self._state == "recording":
            self.mic_view.set_level(self._smoothed_level)
            self.audio_bars.set_level(self._smoothed_level)
            self.mic_view.update()
            self._update_timer_label()
        elif self._state == "paused":
            self.mic_view.update()
            self.audio_bars.set_level(self._smoothed_level)
            self._update_timer_label()
        elif self._state == "processing":
            self.mic_view.set_phase(self._phase)
            self.mic_view.update()
            self.checklist.tick(self._phase)

    def _update_timer_label(self):
        if self._recording_started_at is None:
            self.timer_label.setText("")
            return
        now = time.monotonic()
        paused_extra = self._paused_total
        if self._state == "paused" and self._pause_started_at is not None:
            paused_extra += now - self._pause_started_at
        elapsed = max(0, int(now - self._recording_started_at - paused_extra))
        mm = elapsed // 60
        ss = elapsed % 60
        self.timer_label.setText(f"{mm:02d}:{ss:02d}")

    # ---- state application ----

    def _apply_state(self):
        state = self._state
        self.mic_view.set_state(state)
        self.audio_bars.set_level(self._smoothed_level if state != "idle" else 0.0)

        if state == "idle":
            self.hide()
            return

        # Resize pill per state
        h = STATE_HEIGHTS.get(state, STATE_HEIGHTS["recording"])
        self.setFixedSize(WINDOW_WIDTH, h)

        # Title + color
        if state == "recording":
            self.title_label.setText("Recording")
            self.title_label.setStyleSheet(f"color: {COLOR_STATE_RECORDING.name()};")
            self.timer_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY.name()};")
            self.subtitle_label.setText("Speak clearly…")
            self.subtitle_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()};")
            self.helper_label.setVisible(False)
            self.content_stack.setCurrentIndex(0)
            self._rebuild_buttons([
                ("F8", "Stop",   self.bridge.trigger),
                ("F9", "Pause",  self.bridge.pause),
                ("Esc", "Cancel", self.bridge.cancel),
            ], COLOR_STATE_RECORDING)
        elif state == "paused":
            self.title_label.setText("Paused")
            self.title_label.setStyleSheet(f"color: {COLOR_STATE_PAUSED.name()};")
            self.timer_label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY.name()};")
            self.subtitle_label.setText("Recording paused")
            self.subtitle_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()};")
            self.helper_label.setVisible(False)
            self.content_stack.setCurrentIndex(0)
            self._rebuild_buttons([
                ("F8", "Resume", self.bridge.pause),  # toggle
                ("Esc", "Cancel", self.bridge.cancel),
            ], COLOR_STATE_PAUSED)
        elif state == "processing":
            self.title_label.setText("Processing…")
            self.title_label.setStyleSheet(f"color: {COLOR_STATE_PROCESSING.name()};")
            self.timer_label.setText("")
            self.subtitle_label.setText("Working on it…")
            self.subtitle_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()};")
            self.helper_label.setVisible(False)
            self.content_stack.setCurrentIndex(1)
            self.checklist.reset()
            self._clear_buttons()
        elif state == "ready":
            self.title_label.setText("Text inserted")
            self.title_label.setStyleSheet(f"color: {COLOR_STATE_READY.name()};")
            self.timer_label.setText("")
            self.subtitle_label.setText("Copied to clipboard")
            self.subtitle_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()};")
            self.helper_label.setText("Overlay will close in 2 seconds…")
            self.helper_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()};")
            self.helper_label.setVisible(True)
            self.content_stack.setCurrentIndex(2)
            self.progress.start()
            self._dismiss_timer.start()
            self._rebuild_solid_button("Copy to clipboard", COLOR_STATE_READY,
                                       self._on_copy_clicked)
        elif state == "error":
            self.title_label.setText("Error")
            self.title_label.setStyleSheet(f"color: {COLOR_STATE_ERROR.name()};")
            self.timer_label.setText("")
            msg = (self._last_error or "Something went wrong").strip()
            if len(msg) > 80:
                msg = msg[:77] + "…"
            self.subtitle_label.setText(msg)
            self.subtitle_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()};")
            self.helper_label.setVisible(False)
            self.content_stack.setCurrentIndex(3)
            self._rebuild_solid_button("Dismiss", COLOR_STATE_ERROR, self.dismiss)

        self._position()
        self.show()

    # ---- button management ----

    def _clear_buttons(self):
        # Remove existing buttons from layout and delete widgets
        while self.button_row.count():
            item = self.button_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._current_buttons = []

    def _rebuild_buttons(self, specs, color: QColor):
        self._clear_buttons()
        for key, label, slot in specs:
            btn = KeyChipButton(key, label, self)
            # When the row has multiple buttons, drop the per-button minimum
            # width so the layout can share the available 196px across them
            # equally. (KeyChipButton.__init__ sets a min width based on the
            # key chip + label that is wider than 196 / N for N >= 3.)
            if len(specs) > 1:
                btn.setMinimumWidth(0)
            btn.set_state_color(color)
            btn.clicked.connect(slot)
            # Let buttons share the row width equally so all three fit in
            # 280px. Without a stretch factor, each would only render at its
            # minimum width and clip the labels.
            self.button_row.addWidget(btn, 1)
            self._current_buttons.append(btn)

    def _rebuild_solid_button(self, label: str, color: QColor, slot):
        self._clear_buttons()
        btn = SolidButton(label, self)
        btn.set_state_color(color)
        btn.clicked.connect(slot)
        # Full width for the single button row.
        self.button_row.addWidget(btn, 1)
        self._current_buttons.append(btn)

    def _on_copy_clicked(self):
        self.bridge.copy()
        self.dismiss()

    # ---- dismissal / close ----

    def dismiss(self):
        self._state = "idle"
        self._dismiss_timer.stop()
        self.progress.stop()
        self.hide()

    def closeEvent(self, event):
        if self._subscriber:
            self._subscriber.close()
        super().closeEvent(event)

    # ---- window paint (rounded background) ----

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), CORNER_RADIUS, CORNER_RADIUS)
        p.fillPath(path, COLOR_BG_PILL)
        p.setPen(QPen(COLOR_BORDER_PILL, 1))
        p.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, CORNER_RADIUS, CORNER_RADIUS)


# =====================================================================
# Module entry point — used by main.py in the daemon-with-overlay branch.
# =====================================================================
def main():
    app = QApplication(sys.argv)
    overlay = Overlay()
    overlay.show()  # Will hide itself if state is idle on first sync.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
