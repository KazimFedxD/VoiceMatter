"""PySide6 overlay window for VoiceMatter.

The overlay connects to the daemon as a persistent subscriber, listens for
state/audio-level events, and renders a small frameless pill in the lower
middle of the screen. It sends pause/resume/copy commands back on the same
socket.

States (driven by daemon events):
  idle        -> hidden
  recording   -> red mic with reactive audio bars + "Pause" button
  paused      -> amber mic with pause overlay + "Resume" button
  processing  -> blue disabled "Processing..." button
  ready       -> green "Copy to clipboard" button (re-copy last transcription)
  error       -> red "Error" button (click to dismiss)
"""

from __future__ import annotations

import sys
import math
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QFont
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QHBoxLayout

from .events import Subscriber

SOCKET_PATH = "/tmp/voicematter.sock"

# Layout constants
WINDOW_WIDTH = 280
WINDOW_HEIGHT = 64
MIC_SIZE = 40
BUTTON_HEIGHT = 36
CORNER_RADIUS = 22

# Colors
COLOR_BG_IDLE = QColor(31, 41, 55)        # gray-800
COLOR_BG_RECORDING = QColor(239, 68, 68)   # red-500
COLOR_BG_PAUSED = QColor(245, 158, 11)     # amber-500
COLOR_BG_PROCESSING = QColor(59, 130, 246) # blue-500
COLOR_BG_READY = QColor(16, 185, 129)      # emerald-500
COLOR_BG_ERROR = QColor(220, 38, 38)       # red-600


class DaemonBridge(QObject):
    """Marshals daemon events (background thread) onto the Qt main thread."""

    state_changed = Signal(str)
    level_changed = Signal(float)
    ready = Signal(str)
    error = Signal(str)

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


class MicView(QWidget):
    """Custom-painted mic icon with reactive audio bars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(MIC_SIZE, MIC_SIZE)
        self._level = 0.0
        self._bg_color = COLOR_BG_IDLE
        self._paused = False

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))

    def set_state(self, state: str):
        self._paused = state == "paused"
        if state == "recording":
            self._bg_color = COLOR_BG_RECORDING
        elif state == "paused":
            self._bg_color = COLOR_BG_PAUSED
        elif state == "processing":
            self._bg_color = COLOR_BG_PROCESSING
        elif state == "ready":
            self._bg_color = COLOR_BG_READY
        elif state == "error":
            self._bg_color = COLOR_BG_ERROR
        else:
            self._bg_color = COLOR_BG_IDLE
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # Background circle
        p.setBrush(QBrush(self._bg_color))
        p.setPen(Qt.NoPen)
        radius = 18
        p.drawEllipse(int(cx - radius), int(cy - radius), radius * 2, radius * 2)

        # Mic body
        p.setBrush(QBrush(QColor("white")))
        p.setPen(Qt.NoPen)
        body_w, body_h = 8, 14
        body_x = cx - body_w / 2
        body_y = cy - body_h / 2 - 1
        path = QPainterPath()
        path.addRoundedRect(int(body_x), int(body_y), int(body_w), int(body_h), 4, 4)
        p.drawPath(path)

        # Mic stand
        p.setPen(QPen(QColor("white"), 1.6))
        p.drawLine(int(cx), int(cy + 7), int(cx), int(cy + 10))
        p.drawArc(int(cx - 5), int(cy + 4), 10, 10, 200 * 16, 140 * 16)

        if self._paused:
            # Pause overlay: two vertical bars across the mic
            p.setBrush(QBrush(QColor("white")))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(cx - 3.5), int(cy - 4), 2.5, 8, 1, 1)
            p.drawRoundedRect(int(cx + 1), int(cy - 4), 2.5, 8, 1, 1)
        else:
            # Reactive audio bars to the sides (only meaningful during recording)
            level = self._level
            bar_color = QColor(255, 255, 255, 220)
            p.setBrush(QBrush(bar_color))
            p.setPen(Qt.NoPen)
            # 3 bars on each side, varying heights driven by level
            offsets = [-12, -7, -2, 2, 7, 12]
            for i, dx in enumerate(offsets):
                # Modulate so adjacent bars differ
                phase = (i * 0.37) % 1.0
                bar_h = 6 + (level * 14) * (0.55 + 0.45 * phase)
                bx = cx + dx - 1.25
                by_top = cy - bar_h / 2 + 18  # bars near the bottom of the circle
                p.drawRoundedRect(int(bx), int(by_top), 2.5, int(bar_h), 1, 1)


class Overlay(QWidget):
    """The floating overlay window."""

    def __init__(self, socket_path: str = SOCKET_PATH):
        super().__init__()

        # Window flags: frameless + always-on-top + tool (no taskbar entry)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._state = "idle"
        self._target_level = 0.0
        self._smoothed_level = 0.0
        self._phase = 0.0  # for spinner animation

        # Layout: mic + button side by side
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(12)

        self.mic_view = MicView(self)
        layout.addWidget(self.mic_view, 0, Qt.AlignVCenter)

        self.action_button = QPushButton(self)
        self.action_button.setFixedHeight(BUTTON_HEIGHT)
        self.action_button.setCursor(Qt.PointingHandCursor)
        self.action_button.setFont(QFont("Sans", 10, QFont.Medium))
        self.action_button.clicked.connect(self._on_button_clicked)
        layout.addWidget(self.action_button, 1, Qt.AlignVCenter)

        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # Connect to daemon
        self.bridge = DaemonBridge()
        self.bridge.state_changed.connect(self._on_state)
        self.bridge.level_changed.connect(self._on_level)
        self.bridge.ready.connect(self._on_ready)
        self.bridge.error.connect(self._on_error)
        self._subscriber = Subscriber(socket_path, self.bridge.on_event)
        self.bridge.attach(self._subscriber)
        self._subscriber.start()

        # Animation tick: smooth level + spinner phase
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(33)  # ~30 fps

        self._apply_state()

    # ---- positioning ----

    def _center_position(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        # Lower middle: ~62% down the screen
        y = screen.y() + int(screen.height() * 0.62) - self.height() // 2
        self.move(x, y)

    # ---- event handlers ----

    def _on_state(self, state: str):
        self._state = state
        self._apply_state()

    def _on_level(self, level: float):
        self._target_level = max(0.0, min(1.0, level))

    def _on_ready(self, text: str):
        self._state = "ready"
        self._last_text = text
        self._apply_state()

    def _on_error(self, message: str):
        self._state = "error"
        self._apply_state()

    def _tick(self):
        # Smooth level for nicer animation (low-pass)
        self._smoothed_level += (self._target_level - self._smoothed_level) * 0.25
        self.mic_view.set_level(self._smoothed_level)
        self._phase = (self._phase + 0.18) % (2 * math.pi)

        if self._state == "processing":
            # Refresh button text with spinner glyphs
            glyphs = ["◐", "◓", "◑", "◒"]
            idx = int((self._phase / (2 * math.pi)) * len(glyphs)) % len(glyphs)
            self.action_button.setText(f"{glyphs[idx]} Processing…")
        elif self._state == "recording" or self._state == "paused":
            self.mic_view.update()

    def _apply_state(self):
        self.mic_view.set_state(self._state)
        if self._state == "idle":
            self.hide()
            return

        self.show()
        self._center_position()

        if self._state == "recording":
            self.action_button.setText("Pause")
            self.action_button.setEnabled(True)
            self._style_button(COLOR_BG_RECORDING)
        elif self._state == "paused":
            self.action_button.setText("Resume")
            self.action_button.setEnabled(True)
            self._style_button(COLOR_BG_PAUSED)
        elif self._state == "processing":
            self.action_button.setText("◐ Processing…")
            self.action_button.setEnabled(False)
            self._style_button(COLOR_BG_PROCESSING)
        elif self._state == "ready":
            self.action_button.setText("Copy to clipboard")
            self.action_button.setEnabled(True)
            self._style_button(COLOR_BG_READY)
        elif self._state == "error":
            self.action_button.setText("Error — dismiss")
            self.action_button.setEnabled(True)
            self._style_button(COLOR_BG_ERROR)

    def _on_button_clicked(self):
        if self._state == "recording":
            self.bridge.pause()
        elif self._state == "paused":
            self.bridge.resume()
        elif self._state == "ready":
            self.bridge.copy()
            self._dismiss()
        elif self._state == "error":
            self._dismiss()

    def _dismiss(self):
        self._state = "idle"
        self.hide()

    def _style_button(self, color: QColor):
        r, g, b, _ = color.getRgb()
        css = f"""
            QPushButton {{
                background-color: rgba({r}, {g}, {b}, 0.95);
                color: white;
                border: none;
                border-radius: {BUTTON_HEIGHT // 2}px;
                padding: 0 18px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba({r}, {g}, {b}, 1.0);
            }}
            QPushButton:pressed {{
                background-color: rgba({max(0, r - 20)}, {max(0, g - 20)}, {max(0, b - 20)}, 1.0);
            }}
            QPushButton:disabled {{
                background-color: rgba({r}, {g}, {b}, 0.55);
                color: rgba(255, 255, 255, 0.85);
            }}
        """
        self.action_button.setStyleSheet(css)

    # ---- window paint (rounded background) ----

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Solid translucent pill background
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), CORNER_RADIUS, CORNER_RADIUS)
        p.fillPath(path, QColor(17, 24, 39, 235))  # gray-900 mostly opaque

        # Subtle border
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, CORNER_RADIUS, CORNER_RADIUS)

    def closeEvent(self, event):
        if self._subscriber:
            self._subscriber.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    overlay = Overlay()
    overlay.show()  # Will hide itself if state is idle on first sync.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()