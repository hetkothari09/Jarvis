"""Summoned command palette: a frameless centered input + result area.

Emits `submitted(str)` when the user presses Enter. Shows step lines and the
final result. `confirm(text)` shows a modal yes/no for dangerous tools.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QLabel, QLineEdit, QMessageBox,
                               QVBoxLayout, QWidget)

from jarvis.gui.theme import ACCENT, BG, MUTED, PANEL, TEXT


class Palette(QWidget):
    submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(680)

        card = QFrame(self)
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask JARVIS…   (Esc to dismiss)")
        self._input.returnPressed.connect(self._on_return)
        layout.addWidget(self._input)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setObjectName("status")
        layout.addWidget(self._status)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        self.setStyleSheet(f"""
            #card {{ background: {PANEL}; border: 1px solid {ACCENT};
                     border-radius: 14px; }}
            QLineEdit {{ background: {BG}; color: {TEXT}; border: 1px solid #1e2a38;
                         border-radius: 10px; padding: 12px 14px; font-size: 16px; }}
            #status {{ color: {MUTED}; font-size: 13px; }}
        """)

    def summon(self) -> None:
        self._input.clear()
        self._status.setText("")
        self._center_top()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def show_step(self, line: str) -> None:
        prev = self._status.text()
        self._status.setText((prev + "\n" + line).strip())

    def show_result(self, text: str) -> None:
        self._status.setText(text)

    def confirm(self, message: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Confirm action")
        box.setText(message)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    def _on_return(self) -> None:
        text = self._input.text().strip()
        if text:
            self.submitted.emit(text)

    def _center_top(self) -> None:
        screen = self.screen().availableGeometry()
        self.adjustSize()
        x = screen.center().x() - self.width() // 2
        y = screen.top() + int(screen.height() * 0.22)
        self.move(x, y)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
