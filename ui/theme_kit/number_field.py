"""ui/theme_kit/number_field.py

NumberField — the dense scrubbable numeric control, with an optional unit
selector for lengths.

The caller owns min/max/step/units. The field clamps only to those values and
never substitutes a schema default of its own. Drag emits ``preview``; the
committed value emits ``changed`` once (release / Enter / unit change), so the
preview can be debounced without flooding the renderer.

Unit mode intentionally does not convert on unit change unless the caller
passes a converter. "24 px -> 24 %" is usually wrong, so the default is to
keep the number and let the caller decide.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from PyQt6.QtCore import (
    QEvent, QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, format_number, paint_focus_ring, parse_number_text,
)
from ui.theme_kit.dropdown import CompactDropdown
from ui.theme_kit.popup import attach_tooltip

_UNSET = object()


class _ClearButton(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Clear value")
        attach_tooltip(self, "Clear (not set)")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = tokens.TEXT_SECONDARY if self.underMouse() else tokens.TEXT_MUTED
        pen = QPen(QColor(color), 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        inset = 5
        painter.drawLine(inset, inset, self.width() - inset,
                         self.height() - inset)
        painter.drawLine(self.width() - inset, inset, inset,
                         self.height() - inset)
        painter.end()


class _ValueEdit(QLineEdit):
    def __init__(self, owner: "NumberField"):
        super().__init__(owner)
        self._owner = owner
        self.setFrame(False)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            "QLineEdit { background: transparent; border: none;"
            f" color: {tokens.TEXT_PRIMARY};"
            f" padding: 0px; font-size: {tokens.TYPE_CAPTION}px;"
            f" selection-background-color: {tokens.ACCENT};"
            f" selection-color: {tokens.TEXT_PRIMARY}; }}")
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def mousePressEvent(self, event) -> None:
        if self._owner._typing:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._owner._scrub_press(event.globalPosition().toPoint(),
                                     grabber=self)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._owner._scrub_candidate:
            self._owner._scrub_move(event.globalPosition().toPoint(),
                                    event.modifiers())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._owner._scrub_candidate:
            self._owner._scrub_release()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._owner._begin_typing()
        event.accept()

    def wheelEvent(self, event) -> None:
        self._owner._wheel(event)

    def keyPressEvent(self, event) -> None:
        if self._owner._typing:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._owner._commit_typing()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._owner._revert_typing()
                event.accept()
                return
            super().keyPressEvent(event)
            return
        if self._owner._key_step(event):
            event.accept()
            return
        super().keyPressEvent(event)


class NumberField(QWidget):
    """A compact scrubbable number, optionally a length with units.

    Signals
        changed(object) — committed value (number, string length, or None).
        preview(object) — live value while scrubbing.

    Args
        value: number, length string ("24px", "50%"), keyword, or None.
        minimum/maximum: inclusive bounds; tooltip shows them.
        step: base increment; Shift is coarse, Alt is fine.
        integer: emit ints and format without decimals.
        unit: a fixed suffix shown inside the field (plain mode).
        units: enables UnitField mode; e.g. ["px", "%", "em"].
        keywords: extra unit-selector choices that represent a bare value
            ("auto", "none", "inherit"). They are emitted as strings.
        nullable: shows the muted "not set" state and a clear button.
        unit_converter: optional ``(value, old_unit, new_unit) -> number``.
            Without it, switching units keeps the same number.
        inline_label: a short visible label drawn inside the field, left of
            the number. The kit rule: a NumberField mounted without a
            PropertyRow label (a keyframe grid cell, a paired two-up row)
            must pass one, so the value is never nameless. A field that
            already sits in a row-labelled PropertyRow must not pass one.

    ``label`` is accessibility/tooltip text only; ``inline_label`` is the
    visible short form. Both may be supplied (``label="Shadow blur"``,
    ``inline_label="Blur"``).
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = 0, *, minimum: Optional[float] = None,
                 maximum: Optional[float] = None, step: float = 1.0,
                 coarse_step: Optional[float] = None,
                 fine_step: Optional[float] = None,
                 integer: bool = False, decimals: Optional[int] = None,
                 unit: str = "", units: Optional[Iterable[str]] = None,
                 suffix: str = "",
                 keywords: Optional[Iterable[str]] = None,
                 nullable: bool = False,
                 placeholder: str = "Not set",
                 unit_converter: Optional[
                     Callable[[float, str, str], float]] = None,
                 unit_ranges: Optional[
                     dict[str, tuple[Optional[float], Optional[float],
                                     float]]] = None,
                 label: str = "", inline_label: str = "", parent=None):
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        #: Per-unit ``(minimum, maximum, step)``. When present it wins over the
        #: flat ``minimum``/``maximum``/``step`` for the active unit.
        self._unit_ranges: dict[
            str, tuple[Optional[float], Optional[float], float]] = {
                str(unit_name): (rng[0], rng[1], float(rng[2]))
                for unit_name, rng in (unit_ranges or {}).items()}
        self._step = float(step) if step else 1.0
        self._coarse = (float(coarse_step) if coarse_step is not None
                        else self._step * 10)
        self._fine = (float(fine_step) if fine_step is not None
                      else max(self._step / 10.0, 0.001))
        self._integer = bool(integer)
        self._decimals = decimals
        # ``unit`` is part of the emitted value ("24px"); ``suffix`` is a
        # display-only annotation ("600ms" shown, 600 emitted).
        self._fixed_unit = str(unit or "")
        self._display_suffix = str(suffix or "")
        self._units = [str(u) for u in (units or [])]
        self._keywords = [str(k) for k in (keywords or [])]
        self._nullable = bool(nullable)
        self._placeholder = placeholder
        self._converter = unit_converter
        self._label = label
        self._inline_label_text = str(inline_label or "")
        self._value: Optional[float] = None
        self._keyword = ""
        self._last_number = 0.0
        self._unit = (self._units[0] if self._units else
                      (self._fixed_unit or ""))
        self._typing = False
        self._typing_original: Any = None
        self._scrub_candidate = False
        self._scrub_moved = False
        self._scrub_start = QPoint()
        self._scrub_start_value: Any = None
        self._scrub_last_emitted: Any = None
        self._scrub_grabber: Optional[QWidget] = None
        self._hover = False
        self._warning = ""
        self._limit_hit = False
        self._limit_timer = QTimer(self)
        self._limit_timer.setSingleShot(True)
        self._limit_timer.setInterval(220)
        self._limit_timer.timeout.connect(self._clear_limit)
        self._accessible = label or self._inline_label_text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 3, 0)
        layout.setSpacing(3)
        self._edit = _ValueEdit(self)
        layout.addWidget(self._edit, 1)
        self._inline_label: Optional[QLabel] = None
        if self._inline_label_text:
            self._inline_label = QLabel(self._inline_label_text, self)
            self._inline_label.setStyleSheet(
                f"color: {tokens.TEXT_MUTED};"
                f"font-size: {tokens.TYPE_CAPTION}px;"
                f"font-weight: {tokens.WEIGHT_MEDIUM};"
                "background: transparent;")
            self._inline_label.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            self._inline_label.setCursor(Qt.CursorShape.SizeHorCursor)
            self._inline_label.setMouseTracking(True)
            self._inline_label.installEventFilter(self)
            attach_tooltip(self._inline_label, self._inline_label_text)
            layout.insertWidget(0, self._inline_label, 0)
        self._suffix = QLabel(self._suffix_text(), self)
        self._suffix.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            f"font-size: {tokens.TYPE_CAPTION}px; background: transparent;")
        self._suffix.setVisible(bool(self._suffix_text()) and not self._units)
        layout.addWidget(self._suffix)

        self._unit_button: Optional[CompactDropdown] = None
        self._unit_label: Optional[QLabel] = None
        if len(self._units) == 1 and not self._keywords:
            # A parameter with one mode has nothing to choose: show the unit as
            # plain text where the dropdown would sit, with no chevron and no
            # hover affordance.
            self._unit_label = QLabel(self._units[0], self)
            self._unit_label.setStyleSheet(
                f"color: {tokens.TEXT_MUTED};"
                f"font-size: {tokens.TYPE_CAPTION}px;"
                f"padding-right: 6px;"
                "background: transparent;")
            self._unit_label.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            layout.addWidget(self._unit_label)
        elif self._units or self._keywords:
            options = []
            options.extend(ChoiceOption(u, u) for u in self._units)
            options.extend(ChoiceOption(k, k, muted=True, group="Keywords")
                           for k in self._keywords)
            self._unit_button = CompactDropdown(
                options, self._unit, variant="bare", min_width=28,
                max_width=50, popup_width=96, popup_max_height=220)
            self._unit_button.setFixedHeight(tokens.CONTROL_HEIGHT - 2)
            self._unit_button.setAccessibleName("Unit")
            self._unit_button.changed.connect(self._on_unit_changed)
            layout.addWidget(self._unit_button)

        self._clear = _ClearButton(self)
        self._clear.clicked.connect(self._clear_value)
        layout.addWidget(self._clear)
        self._clear.setVisible(False)

        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFocusProxy(self._edit)
        self.setMouseTracking(True)
        self._edit.installEventFilter(self)
        self._edit.editingFinished.connect(self._on_edit_finished)
        attach_tooltip(self, lambda: self._tooltip_text())
        if label:
            self.setAccessibleName(label)
        self.set_value(value)

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        if self._keyword:
            return self._keyword
        if self._value is None:
            return None
        if self._units or self._fixed_unit:
            text = format_number(self._value, integer=self._integer,
                                 decimals=self._decimals)
            return f"{text}{self._unit}"
        return int(round(self._value)) if self._integer else self._value

    def numeric_value(self) -> Optional[float]:
        return self._value

    def unit(self) -> str:
        """The unit this field currently shows (``"px"``, ``"%"``, ``""``)."""
        return self._unit

    def keyword(self) -> str:
        """The active keyword (``"auto"``, ``"inherit"``), or ``""``."""
        return self._keyword

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        self._adopt(value)
        self._sync_display()
        if emit:
            self.changed.emit(self.value())

    def set_range(self, minimum: Optional[float],
                  maximum: Optional[float], *, emit: bool = True) -> None:
        self._minimum = minimum
        self._maximum = maximum
        if self._unit_ranges:
            self._unit_ranges = {
                unit: (minimum, maximum, rng[2])
                for unit, rng in self._unit_ranges.items()}
        if self._value is not None:
            clamped = self._clamp(self._value)
            if clamped != self._value:
                self._value = clamped
                self._sync_display()
                if emit:
                    self.changed.emit(self.value())

    def set_step(self, step: float, *, coarse: Optional[float] = None,
                 fine: Optional[float] = None) -> None:
        self._step = float(step) if step else 1.0
        self._coarse = float(coarse) if coarse is not None else step * 10
        self._fine = (float(fine) if fine is not None
                      else max(step / 10.0, 0.001))

    def set_unit_ranges(self, ranges: Optional[dict] = None, *,
                        minimum: Optional[float] = None,
                        maximum: Optional[float] = None) -> None:
        """Replace the per-unit ranges without rewriting the visible value.

        Loading a theme, or resizing the canvas, must not clamp an authored
        value: the field keeps showing what the document stores and only the
        next user edit applies the new bound.
        """
        self._unit_ranges = {
            str(unit_name): (rng[0], rng[1], float(rng[2]))
            for unit_name, rng in (ranges or {}).items()}
        self._minimum = minimum
        self._maximum = maximum
        self.update()

    def set_units(self, units: Iterable[str], *,
                  keywords: Iterable[str] = ()) -> None:
        self._units = [str(u) for u in units]
        self._keywords = [str(k) for k in keywords]
        if self._unit_button is not None:
            self._unit_button.set_options(
                [ChoiceOption(u, u) for u in self._units]
                + [ChoiceOption(k, k, muted=True, group="Keywords")
                   for k in self._keywords],
                value=self._unit, emit=False)
        if self._unit_label is not None:
            self._unit_label.setText(self._units[0] if self._units else "")
        self._sync_display()

    def set_warning(self, text: str) -> None:
        self._warning = str(text or "")
        if self._warning:
            attach_tooltip(self, lambda: self._warning)
        self.update()

    def set_accessible_label(self, text: str) -> None:
        self._accessible = str(text)
        self.setAccessibleName(self._accessible)

    def inline_label(self) -> str:
        """The visible short label, or "" when the field has none."""
        return self._inline_label_text

    def _suffix_text(self) -> str:
        return self._display_suffix or self._fixed_unit

    def set_suffix(self, suffix: str) -> None:
        """Set the display-only suffix (never part of the emitted value)."""
        self._display_suffix = str(suffix or "")
        self._suffix.setText(self._suffix_text())
        self._suffix.setVisible(bool(self._suffix_text()) and not self._units)

    def _tooltip_text(self) -> str:
        if self._warning:
            return self._warning
        low, high, _step = self._active_limits()
        if low is None and high is None:
            return self._accessible or "Any value"
        suffix = (self._unit if (self._units or self._fixed_unit)
                  else self._display_suffix)
        text_low = "−∞" if low is None else format_number(
            low, integer=self._integer, decimals=self._decimals)
        text_high = "∞" if high is None else format_number(
            high, integer=self._integer, decimals=self._decimals)
        name = f"{self._accessible}: " if self._accessible else ""
        return f"{name}{text_low} – {text_high}{suffix}"

    def _active_limits(self) -> tuple[Optional[float], Optional[float],
                                      Optional[float]]:
        """The bounds and step for the unit on screen right now."""
        low: Optional[float] = self._minimum
        high: Optional[float] = self._maximum
        step: Optional[float] = None
        unit = self._unit
        if unit in self._unit_ranges:
            low, high, step = self._unit_ranges[unit]
        return low, high, step

    def _clamp(self, value: float) -> float:
        low, high, _step = self._active_limits()
        requested = float(value)
        if low is not None:
            value = max(low, value)
        if high is not None:
            value = min(high, value)
        value = float(round(value, 6))
        if value != requested:
            self._flash_limit()
        return value

    def _flash_limit(self) -> None:
        """Tint the border for a moment when an edit hits a bound."""
        self._limit_hit = True
        self._limit_timer.start()
        self.update()

    def _clear_limit(self) -> None:
        self._limit_hit = False
        self.update()

    def _active_step(self) -> float:
        _low, _high, step = self._active_limits()
        return float(step) if step else self._step

    def _coarse_step(self) -> float:
        _low, _high, step = self._active_limits()
        return step * 10 if step else self._coarse

    def _fine_step(self) -> float:
        _low, _high, step = self._active_limits()
        return max(step / 10.0, 0.001) if step else self._fine

    def _coerce_commit(self, value: float) -> float:
        if self._integer:
            return float(int(round(value)))
        return float(round(value, 6))

    def _adopt(self, value: Any) -> None:
        self._typing = False
        self._scrub_candidate = False
        if value is None or value == "":
            self._value = None
            self._keyword = ""
            self._sync_clear()
            return
        if isinstance(value, bool):
            value = int(value)
        if isinstance(value, (int, float)):
            self._value = self._coerce_commit(float(value))
            self._last_number = self._value
            self._keyword = ""
            self._reset_unit()
            self._sync_clear()
            return
        text = str(value).strip()
        keyword = next((k for k in self._keywords
                        if k.lower() == text.lower()), None)
        if keyword is not None:
            self._keyword = keyword
            self._unit = keyword
            if self._unit_button is not None:
                self._unit_button.set_value(keyword, emit=False)
            self._sync_clear()
            return
        # Length / unit string. Keep the suffix only when it is one of the
        # caller's units; anything else is a caller error, not ours to fix.
        number_text = text
        unit = self._unit
        for candidate in sorted(set(self._units + ([self._fixed_unit]
                                                   if self._fixed_unit else [])),
                                key=len, reverse=True):
            if candidate and text.lower().endswith(candidate.lower()):
                number_text = text[:-len(candidate)].strip()
                unit = candidate
                break
        parsed = parse_number_text(number_text)
        if parsed is None:
            parsed = parse_number_text(text)
        if parsed is None:
            self._value = None
            self._keyword = ""
            self._sync_clear()
            return
        self._unit = unit
        if self._unit_button is not None:
            self._unit_button.set_value(unit, emit=False)
        self._value = self._coerce_commit(parsed)
        self._last_number = self._value
        self._keyword = ""
        self._sync_clear()

    def _sync_clear(self) -> None:
        self._clear.setVisible(
            self._nullable and (self._value is not None or bool(self._keyword)))
        self._suffix.setVisible(bool(self._suffix_text()) and not self._units)

    def _reset_unit(self) -> None:
        """A bare number has no authored unit; show it in the default one.

        Without this a document value loaded after a percentage one keeps
        displaying (and committing) ``%`` even though the schema value is a
        plain pixel number.
        """
        if not self._units:
            return
        self._unit = self._units[0]
        if self._unit_button is not None:
            self._unit_button.set_value(self._unit, emit=False)

    def _sync_display(self) -> None:
        if self._value is None and not self._keyword:
            self._edit.setText("")
            self._edit.setPlaceholderText(self._placeholder)
        elif self._keyword:
            self._edit.setText(self._keyword)
            self._edit.setPlaceholderText("")
        else:
            self._edit.setText(format_number(
                self._value, integer=self._integer, decimals=self._decimals))
            self._edit.setPlaceholderText("")
        self._sync_clear()
        self.update()

    # ── typing ──────────────────────────────────────────────────────────────
    def _begin_typing(self) -> None:
        if self._typing:
            return
        # A double-click opens the text editor from a press that already
        # began a scrub: drop the scrub and its pointer grab first.
        self._release_scrub_grab()
        self._scrub_candidate = False
        self._typing = True
        self._typing_original = self.value()
        self._edit.setReadOnly(False)
        self._edit.setCursor(Qt.CursorShape.IBeamCursor)
        if self._keyword:
            self._edit.setText(self._keyword)
        elif self._value is None:
            self._edit.setText("")
        else:
            self._edit.setText(format_number(
                self._value, integer=self._integer, decimals=self._decimals))
        self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
        self._edit.selectAll()

    def _commit_typing(self) -> None:
        text = self._edit.text().strip()
        self._typing = False
        self._edit.setReadOnly(True)
        self._edit.setCursor(Qt.CursorShape.SizeHorCursor)
        before = self.value()
        if not text:
            if self._nullable:
                self._value = None
                self._keyword = ""
            else:
                self._adopt(before)
        else:
            self._adopt(text)
        if self._value is not None:
            clamped = self._clamp(self._value)
            if clamped != self._value:
                self._value = self._coerce_commit(clamped)
        self._sync_display()
        after = self.value()
        if after != before:
            self.changed.emit(after)

    def _revert_typing(self) -> None:
        self._typing = False
        self._edit.setReadOnly(True)
        self._edit.setCursor(Qt.CursorShape.SizeHorCursor)
        self._adopt(self._typing_original)
        self._sync_display()
        self._edit.clearFocus()

    def _clear_value(self) -> None:
        if not self._nullable:
            return
        if self._value is None and not self._keyword:
            return
        self._value = None
        self._keyword = ""
        self._sync_display()
        self.changed.emit(None)

    # ── stepping / scrubbing ────────────────────────────────────────────────
    def _step_by(self, direction: int, modifiers=Qt.KeyboardModifier.NoModifier,
                 *, emit: bool = True) -> None:
        if self._keyword:
            return
        low, _high, _step = self._active_limits()
        base = self._value if self._value is not None else (
            low if low is not None else 0.0)
        step = self._active_step()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            step = self._coarse_step()
        elif modifiers & Qt.KeyboardModifier.AltModifier:
            step = self._fine_step()
        new_value = self._clamp(base + direction * step)
        before = self.value()
        self._value = self._coerce_commit(new_value)
        self._last_number = self._value
        self._sync_display()
        after = self.value()
        if emit and after != before:
            self.changed.emit(after)

    def _key_step(self, event) -> bool:
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Right):
            self._step_by(1, event.modifiers())
            return True
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Left):
            self._step_by(-1, event.modifiers())
            return True
        if key == Qt.Key.Key_Home and self._minimum is not None:
            self._set_numeric(self._minimum)
            return True
        if key == Qt.Key.Key_End and self._maximum is not None:
            self._set_numeric(self._maximum)
            return True
        return False

    def _set_numeric(self, value: float) -> None:
        before = self.value()
        self._value = self._coerce_commit(self._clamp(value))
        self._last_number = self._value
        self._keyword = ""
        self._sync_display()
        after = self.value()
        if after != before:
            self.changed.emit(after)

    def _ensure_numeric_unit(self) -> None:
        """Scrubbing a keyword must land on a real unit, not ``auto``."""
        if self._unit in self._keywords:
            self._unit = self._units[0] if self._units else ""
            if self._unit_button is not None:
                self._unit_button.set_value(self._unit, emit=False)

    def _scrub_press(self, global_pos: QPoint,
                     grabber: Optional[QWidget] = None) -> None:
        if self._keyword:
            # Scrubbing a keyword has no number to move; start from the last
            # numeric value so the control stays useful.
            self._keyword = ""
            self._value = self._last_number
            self._ensure_numeric_unit()
            self._sync_display()
        self._scrub_candidate = True
        self._scrub_moved = False
        self._scrub_start = global_pos
        # Anchor on the numeric value, not on the display string: the value
        # must be `start + travel * step` for the whole gesture. Using the
        # rendered text here re-anchored every move and compounded travel.
        self._scrub_start_value = self._value
        self._scrub_last_emitted = self.value()
        # Follow the pointer for the whole gesture, including the part that
        # leaves the field: the value is driven by horizontal travel from
        # this press point, never by where the pointer happens to be.
        self._release_scrub_grab()
        if grabber is not None:
            grabber.grabMouse()
            self._scrub_grabber = grabber

    def _release_scrub_grab(self) -> None:
        grabber = self._scrub_grabber
        self._scrub_grabber = None
        if grabber is None:
            return
        try:
            grabber.releaseMouse()
        except RuntimeError:
            # The grabber can be gone if the panel was rebuilt mid-drag.
            pass

    def begin_scrub(self) -> None:
        if self._keyword:
            self._keyword = ""
            self._value = self._last_number
            self._ensure_numeric_unit()
            self._sync_display()
        self._scrub_candidate = True
        self._scrub_moved = False
        self._scrub_start = QPoint(0, 0)
        self._scrub_start_value = self._value
        self._scrub_last_emitted = self.value()

    def _scrub_move(self, global_pos: QPoint,
                    modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        if not self._scrub_candidate:
            return
        delta = global_pos.x() - self._scrub_start.x()
        if abs(delta) < 3 and not self._scrub_moved:
            return
        self._scrub_moved = True
        self.scrub_to(delta, modifiers)

    def scrub_to(self, dx: int,
                 modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        if self._keyword:
            self._ensure_numeric_unit()
        if self._scrub_start_value is None:
            base = self._value if self._value is not None else 0.0
        else:
            base = float(self._scrub_start_value
                         if not isinstance(self._scrub_start_value, str)
                         else (self._value or 0.0))
        step = self._active_step()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            step = self._coarse_step()
        elif modifiers & Qt.KeyboardModifier.AltModifier:
            step = self._fine_step()
        units = dx / 3.0
        value = self._clamp(base + round(units) * step)
        self._value = self._coerce_commit(value)
        self._last_number = self._value
        self._keyword = ""
        self._sync_display()
        current = self.value()
        if current != self._scrub_last_emitted:
            self._scrub_last_emitted = current
            self.preview.emit(current)

    def _scrub_release(self) -> None:
        was_candidate = self._scrub_candidate
        self._scrub_candidate = False
        self._release_scrub_grab()
        if not was_candidate:
            return
        current = self.value()
        if self._scrub_moved and self._value != self._scrub_start_value:
            self.changed.emit(current)
        elif not self._scrub_moved:
            # A plain click on the field is a focus gesture.
            self._edit.setFocus(Qt.FocusReason.MouseFocusReason)

    def end_scrub(self) -> None:
        if not self._scrub_candidate:
            self._release_scrub_grab()
            return
        self._scrub_candidate = False
        self._release_scrub_grab()
        current = self.value()
        if self._value != self._scrub_start_value:
            self.changed.emit(current)
        elif not self._scrub_moved:
            self._edit.setFocus(Qt.FocusReason.MouseFocusReason)

    def _wheel(self, event) -> None:
        if not (self.hasFocus() or self._edit.hasFocus()
                or (self._unit_button is not None
                    and self._unit_button.hasFocus())):
            event.ignore()
            return
        self._step_by(1 if event.angleDelta().y() > 0 else -1,
                      event.modifiers())
        event.accept()

    # ── unit selector ───────────────────────────────────────────────────────
    def _on_unit_changed(self, unit: str) -> None:
        before = self.value()
        old_unit = self._unit
        old_value = self._value
        self._unit = unit
        if unit in self._keywords:
            if self._value is not None:
                self._last_number = self._value
            self._keyword = unit
        else:
            self._keyword = ""
            if self._converter is not None and self._value is not None:
                try:
                    converted = self._converter(
                        float(self._value), old_unit, unit)
                    if converted is not None:
                        self._value = self._coerce_commit(converted)
                except Exception:
                    pass
            if self._value is not None:
                clamped = self._clamp(self._value)
                if clamped != self._value:
                    self._value = self._coerce_commit(clamped)
        self._sync_display()
        after = self.value()
        if after == before:
            return
        # 0px and 0% render the same: switching units must not, by itself,
        # make the document dirty. The next real edit writes the new unit.
        if (old_unit != unit and self._keyword == ""
                and old_value == 0 and self._value == 0):
            return
        self.changed.emit(after)

    # ── painting ────────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        # The frame and the space around the text are part of the control:
        # pressing anywhere starts the same scrub, anchored at the press.
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._typing and self.isEnabled()):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._scrub_press(event.globalPosition().toPoint(), grabber=self)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._scrub_candidate:
            self._scrub_move(event.globalPosition().toPoint(),
                             event.modifiers())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._scrub_candidate:
            self._scrub_release()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def _on_edit_finished(self) -> None:
        if self._typing:
            self._commit_typing()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._edit:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self.update()
        elif obj is self._inline_label:
            # The label is part of the control: click/drag it like the value
            # text (PropertyRow labels scrub their NumberField the same way).
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    if not self._typing:
                        self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
                        self._scrub_press(
                            event.globalPosition().toPoint(), grabber=self)
                        return True
            elif event.type() == QEvent.Type.MouseMove:
                if self._scrub_candidate:
                    self._scrub_move(
                        event.globalPosition().toPoint(), event.modifiers())
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._scrub_candidate:
                    self._scrub_release()
                    return True
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        enabled = self.isEnabled()
        focused = self._edit.hasFocus() or self.hasFocus()
        if not enabled:
            surface = tokens.BG_PANEL
        else:
            surface = tokens.BG_FIELD
        painter.setBrush(QColor(surface))
        if not enabled:
            edge = tokens.BORDER_HAIRLINE
        elif self._limit_hit:
            edge = tokens.ACCENT_BORDER
        elif focused:
            edge = tokens.ACCENT
        elif self._warning:
            edge = tokens.WARNING
        elif self._hover:
            edge = tokens.BORDER_POPOVER
        else:
            edge = tokens.BORDER_HAIRLINE
        painter.setPen(QPen(QColor(edge), 1))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)
        if focused:
            paint_focus_ring(painter, QRectF(self.rect()),
                             tokens.RADIUS_SM)
        painter.end()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        hint.setHeight(tokens.CONTROL_HEIGHT)
        hint.setWidth(max(70, hint.width()))
        return hint


__all__ = ["NumberField"]
