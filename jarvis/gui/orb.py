"""Always-on floating orb. Frameless, translucent, click-through-free.

The orb reflects the agent state via color. Visual rendering is verified
manually; orb_color() holds the testable mapping.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from jarvis.gui.theme import IDLE, BUSY, ERROR

_DIAMETER = 64


def orb_color(state: str) -> str:
    return {"idle": IDLE, "busy": BUSY, "error": ERROR}.get(state, IDLE)


class Orb(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._state = "idle"
        self._pulse = 0.0
        self.setFixedSize(_DIAMETER, _DIAMETER)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._place_bottom_right()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def _place_bottom_right(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(screen.right() - _DIAMETER - 24, screen.bottom() - _DIAMETER - 24)

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.06) % 1.0
        if self._state != "idle":
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        radius = _DIAMETER / 2
        grad = QRadialGradient(center, radius)
        base = QColor(orb_color(self._state))
        glow = QColor(base)
        glow.setAlpha(90 if self._state == "idle" else int(120 + 100 * self._pulse))
        grad.setColorAt(0.0, glow)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(self.rect())
