"""ui/theme_kit/backdrop_field.py

BackdropField — the ``backdrop_filter`` control.

The theme stores a CSS filter list (``"none"`` or a space-separated function
list). Blur is the one function the panel gives a control of its own: a px
radius the operator can type or drag. Any other function already in the
stored string is carried through untouched, so editing the blur never
silently rewrites a theme's saturation or brightness.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from ui import tokens
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import attach_tooltip

#: One plain sentence: what this does and what it needs to show.
HINT = ("Blurs whatever is behind this container. Needs a semi-transparent "
        "fill to be visible.")

_BLUR_RE = re.compile(r"blur\(\s*(-?\d+(?:\.\d+)?)\s*px\s*\)", re.I)
_OFF_VALUES = ("", "none", "off", "transparent")


class BackdropField(QWidget):
    """Blur radius in px, preserving the rest of the stored filter list.

    Signals
        changed(object) — committed filter string (or ``"none"``).
        preview(object) — live filter string while scrubbing.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = "none", parent=None):
        super().__init__(parent)
        self._rest = ""
        self._hint = HINT
        self._blur = NumberField(
            "", units=["px"], nullable=True, minimum=0, maximum=60,
            integer=True, label="Backdrop blur", placeholder="None")
        self._blur.changed.connect(self._on_changed)
        self._blur.preview.connect(self._on_preview)
        attach_tooltip(self._blur, HINT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._blur, 1)

        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(self._blur.sizePolicy())
        self.setToolTip(HINT)
        self.setAccessibleName("Backdrop blur")
        self.set_value(value)

    # ── public ──────────────────────────────────────────────────────────────
    def blur(self) -> Optional[float]:
        """The blur radius in px, or ``None`` when no blur is stored."""
        return self._blur.numeric_value()

    def set_blur(self, value: Optional[float], *, emit: bool = False) -> None:
        self._blur.set_value(None if value is None else f"{value:g}px",
                             emit=emit)

    def value(self) -> str:
        """The stored filter string this control represents."""
        parts: list[str] = []
        number = self._blur.numeric_value()
        if number is not None:
            parts.append(f"blur({number:g}px)")
        if self._rest:
            parts.append(self._rest)
        return " ".join(parts) if parts else "none"

    def set_value(self, value: Any) -> None:
        text = "" if value is None else str(value).strip()
        if text.casefold() in _OFF_VALUES:
            self._rest = ""
            self._blur.set_value(None)
            return
        match = _BLUR_RE.search(text)
        if match is not None:
            self._blur.set_value(f"{float(match.group(1)):g}px")
            text = _BLUR_RE.sub(" ", text)
        else:
            # The stored list has no blur (say only `saturate(1.2)`); the
            # control starts empty and keeps the rest verbatim.
            self._blur.set_value(None)
        self._rest = re.sub(r"\s+", " ", text).strip()

    # ── signals ─────────────────────────────────────────────────────────────
    def _on_changed(self, *_args) -> None:
        self.changed.emit(self.value())

    def _on_preview(self, *_args) -> None:
        self.preview.emit(self.value())


__all__ = ["BackdropField", "HINT"]
