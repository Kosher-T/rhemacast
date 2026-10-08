"""
ui/widgets/lite_designer/format_ribbon.py

Word-processor ribbon for the Lite Designer freeform page.

Row 1 (always visible): font · size −/+ · B I S U · outline + color ·
    text color · clear · undo redo
Row 2 (collapsible "¶"): alignment · spacing · bullets · numbers ·
    super/sub · UPPER/lower · RTL/LTR · HR

Operates on the active QTextEdit (set_editor). All character formatting goes
through _merge() so explicit txt props (UL_PROP/SO_PROP/OUTLINE_PROP) stay
consistent — see rich_txt module docstring for the contract.
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
                             QComboBox, QFontComboBox, QColorDialog, QMenu,
                             QTextEdit, QSizePolicy, QSpinBox)
from PyQt6.QtGui import (QTextCharFormat, QTextCursor, QTextBlockFormat,
                          QFont, QColor, QBrush, QTextFormat, QAction)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.widgets.lite_designer.rich_txt import (
    OUTLINE_PROP, OUTLINE_OFF, SHADOW_PROP, SHADOW_OFF,
    UL_PROP, SO_PROP, SIZE_PROP, COLOR_PROP,
    CASE_PROP,
    FONT_PROP, ALIGN_PROP, DIR_PROP, insert_hr_at)
from ui.styles import (
    TEXT_PRIMARY, TEXT_MUTED, SLATE_300, SLATE_600,
    BG_RAISED, ACCENT, SELECTION_BG, SELECTION_BORDER, CHROME_SOFT,
    TEXT_SELECTION,
)

_PT_PER_PX = 0.75
_SIZES_PX = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 44, 54, 62, 72]
_SPACINGS = [("Single", 1.0), ("1.15", 1.15), ("1.5", 1.5), ("Double", 2.0)]

_RIBBON_STYLE = (
    "QWidget { background: " + CHROME_SOFT + "; color: " + TEXT_PRIMARY + "; }"
    "QToolButton { background: transparent; border: 1px solid transparent;"
    "  border-radius: 4px; padding: 3px 7px; font-size: 12px; font-weight: 700;"
    "  color: " + SLATE_300 + "; }"
    "QToolButton:hover { background: rgba(255,255,255,0.08); color: " + TEXT_PRIMARY + "; }"
    "QToolButton:checked { background: " + SELECTION_BG + ";"
    "  border-color: " + SELECTION_BORDER + "; color: " + ACCENT + "; }"
    "QToolButton:disabled { color: " + SLATE_600 + "; }"
    "QComboBox { background: rgba(0,0,0,0.3); color: " + TEXT_PRIMARY + ";"
    "  border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;"
    "  padding: 2px 6px; font-size: 11px; }"
    "QComboBox QAbstractItemView { background: " + BG_RAISED + "; color: " + TEXT_PRIMARY + ";"
    "  selection-background-color: " + TEXT_SELECTION + "; }"
)


def _parse_outline_value(value) -> tuple[str, int]:
    """Parse OUTLINE_PROP's stored value into (hex color, width px).

    Newer runs store "Npx #rrggbb"; legacy runs are bare "#rrggbb"
    (width assumed 1).
    """
    raw = str(value or "").strip()
    if not raw:
        return "#000000", 1
    if "px" in raw.lower():
        first, _, rest = raw.partition("px")
        try:
            width = max(1, min(25, int(float(first.strip()))))
        except ValueError:
            width = 1
        color = rest.strip()
        if color.startswith("#"):
            return color, width
        return "#000000", width
    return raw, 1


def _parse_shadow_value(value) -> tuple[int, int, int, str, int] | None:
    """A stored shadow value -> (size, opacity, distance, color, angle).

    Mirrors core.slide_parser._parse_shadow (which already normalized what the
    document holds); kept local so the ribbon can read a char format without
    re-importing the parser on every keystroke.
    """
    from core.slide_parser import _parse_shadow
    parsed = _parse_shadow(str(value or ""))
    if not parsed or parsed == "none":
        return None
    size, rest = parsed.split(" ", 1)
    opacity, rest = rest.split(" ", 1)
    distance, rest = rest.split(" ", 1)
    color, _, angle = rest.rpartition(" ")
    return (int(size[:-2]), int(opacity[:-1]), int(distance[:-2]), color,
            int(angle))


def set_outline_off(doc, start: int = 0, end: int | None = None):
    """Write the explicit outline-off marker over [start, end).

    mergeCharFormat (not setCharFormat) is deliberate: it *sets* the sentinel
    value instead of unsetting the property, so the run overrides a theme
    baseline instead of falling back to it.
    """
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, OUTLINE_OFF)
    cursor = QTextCursor(doc)
    if start == 0 and (end is None or end >= max(0, doc.characterCount() - 1)):
        cursor.select(QTextCursor.SelectionType.Document)
    else:
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(fmt)


class FormatRibbon(QWidget):
    """Two-row formatting ribbon bound to one active editor at a time."""

    format_applied = pyqtSignal()       # any text/block formatting change
    deck_format_changed = pyqtSignal(dict)  # e.g. {"spacing": 1.5}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit: QTextEdit | None = None
        # Deck-wide fan-out (set by the designer while the whole deck is
        # selected): _merge routes char formats here instead of the editor.
        self.fan_out = None
        self.fan_out_remove_outline = None
        self._outline_color = "#000000"
        self._outline_width = 1
        self._shadow_color = "#000000"
        self._shadow_size_px = 8
        self._shadow_opacity_pct = 100
        self._shadow_distance_px = 0
        self._shadow_angle_deg = 45
        self._deck_spacing: float | None = None
        # Theme baseline (core.theme_loader.display_format_defaults):
        # what the DISPLAY already applies. A run's own props win; these
        # only fill the gaps, so the ribbon shows effective formatting
        # instead of reading empty until the operator clicks something.
        self._theme_defaults: dict = {}
        self.setStyleSheet(_RIBBON_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(2)
        self._build_row1(row1)
        root.addLayout(row1)

        self._more_toggle = QToolButton()
        self._more_toggle.setText("¶ More")
        self._more_toggle.setCheckable(True)
        self._more_toggle.setChecked(False)
        self._more_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_toggle.toggled.connect(self._on_more_toggled)
        row1.addWidget(self._more_toggle)

        self._row2 = QWidget()
        row2 = QHBoxLayout(self._row2)
        row2.setContentsMargins(0, 2, 0, 0)
        row2.setSpacing(2)
        self._build_row2(row2)
        row2.addStretch()
        root.addWidget(self._row2)
        self._row2.setVisible(False)

    # ─── construction ───────────────────────────────────────────────────

    def _btn(self, text: str, tip: str, checkable=False) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _spin(self, lo: int, hi: int, value: int, suffix: str, tip: str) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        s.setSuffix(suffix)
        s.setToolTip(tip)
        s.setMaximumWidth(72)
        return s

    def _build_row1(self, row: QHBoxLayout):
        self._font_combo = QFontComboBox()
        self._font_combo.setToolTip("Font family")
        self._font_combo.setMaximumWidth(150)
        self._font_combo.currentFontChanged.connect(self._on_font_family)
        row.addWidget(self._font_combo)

        self._size_minus = self._btn("−", "Decrease size")
        self._size_minus.clicked.connect(lambda: self._step_size(-1))
        row.addWidget(self._size_minus)
        self._size_combo = QComboBox()
        self._size_combo.setEditable(True)
        self._size_combo.setToolTip("Font size (px)")
        self._size_combo.setMaximumWidth(58)
        for s in _SIZES_PX:
            self._size_combo.addItem(str(s))
        self._size_combo.setCurrentText("20")
        self._size_combo.activated.connect(self._on_size_combo)
        self._size_combo.lineEdit().returnPressed.connect(self._on_size_typed)
        row.addWidget(self._size_combo)
        self._size_plus = self._btn("+", "Increase size")
        self._size_plus.clicked.connect(lambda: self._step_size(1))
        row.addWidget(self._size_plus)

        self._btn_bold = self._btn("B", "Bold (Ctrl+B)", True)
        self._btn_bold.clicked.connect(lambda: self._toggle_bold())
        row.addWidget(self._btn_bold)
        self._btn_italic = self._btn("I", "Italic (Ctrl+I)", True)
        self._btn_italic.clicked.connect(lambda: self._toggle_italic())
        row.addWidget(self._btn_italic)
        self._btn_strike = self._btn("S", "Strikethrough", True)
        self._btn_strike.clicked.connect(lambda: self._toggle_strike())
        row.addWidget(self._btn_strike)
        self._btn_underline = self._btn("U", "Underline (Ctrl+U)", True)
        self._btn_underline.clicked.connect(lambda: self._toggle_underline())
        row.addWidget(self._btn_underline)

        self._btn_outline = self._btn("O", "Outline (uses outline color)", True)
        self._btn_outline.clicked.connect(self._on_outline_toggled)
        row.addWidget(self._btn_outline)
        self._btn_outline_color = self._btn("■", "Outline color")
        self._btn_outline_color.clicked.connect(self._on_outline_color)
        self._btn_outline_color.setVisible(False)
        row.addWidget(self._btn_outline_color)
        self._outline_size = QSpinBox()
        self._outline_size.setRange(1, 25)
        self._outline_size.setValue(self._outline_width)
        self._outline_size.setSuffix(" px")
        self._outline_size.setToolTip("Outline thickness (1–25 px)")
        self._outline_size.setMaximumWidth(76)
        self._outline_size.valueChanged.connect(self._on_outline_size_changed)
        self._outline_size.setVisible(False)
        row.addWidget(self._outline_size)

        # Shadow: a hard ring drawn in shadow rather than stroke, so it can be
        # pulled away from the letters (distance) and faded (opacity).
        self._btn_shadow = self._btn("Sh", "Shadow (size / opacity / distance / angle)", True)
        self._btn_shadow.clicked.connect(self._on_shadow_toggled)
        row.addWidget(self._btn_shadow)
        self._btn_shadow_color = self._btn("\u25a0", "Shadow color")
        self._btn_shadow_color.clicked.connect(self._on_shadow_color)
        self._btn_shadow_color.setVisible(False)
        row.addWidget(self._btn_shadow_color)
        self._shadow_size = self._spin(1, 25, self._shadow_size_px, " px",
                                      "Shadow size (1\u201325 px)")
        self._shadow_opacity = self._spin(0, 100, self._shadow_opacity_pct, " %",
                                          "Shadow opacity (0\u2013100 %)")
        self._shadow_distance = self._spin(0, 60, self._shadow_distance_px, " px",
                                           "Shadow distance from the letters")
        self._shadow_angle = self._spin(0, 359, self._shadow_angle_deg, "\u00b0",
                                        "Shadow direction (degrees, 0 = east, 90 = down)")
        for s in (self._shadow_size, self._shadow_opacity, self._shadow_distance,
                  self._shadow_angle):
            s.setVisible(False)
            row.addWidget(s)
        self._shadow_size.valueChanged.connect(self._on_shadow_size_changed)
        self._shadow_opacity.valueChanged.connect(self._on_shadow_opacity_changed)
        self._shadow_distance.valueChanged.connect(self._on_shadow_distance_changed)
        self._shadow_angle.valueChanged.connect(self._on_shadow_angle_changed)

        self._btn_color = self._btn("A", "Text color")
        self._btn_color.clicked.connect(self._on_text_color)
        row.addWidget(self._btn_color)

        self._btn_clear = self._btn("⌫", "Clear formatting")
        self._btn_clear.clicked.connect(self._on_clear)
        row.addWidget(self._btn_clear)

        self._btn_undo = self._btn("↩", "Undo (Ctrl+Z)")
        self._btn_undo.clicked.connect(self._do_undo)
        row.addWidget(self._btn_undo)
        self._btn_redo = self._btn("↪", "Redo (Ctrl+Shift+Z)")
        self._btn_redo.clicked.connect(self._do_redo)
        row.addWidget(self._btn_redo)
        row.addStretch()

    def _build_row2(self, row: QHBoxLayout):
        self._align_btns = {}
        for key, label, tip in (("left", "≡", "Align left"),
                                ("center", "≣", "Align center"),
                                ("right", "≡", "Align right"),
                                ("justify", "☰", "Justify")):
            b = self._btn(label, tip, True)
            b.clicked.connect(lambda _=False, k=key: self._on_align(k))
            row.addWidget(b)
            self._align_btns[key] = b

        self._spacing_btn = self._btn("↕", "Paragraph spacing")
        self._spacing_menu = QMenu(self)
        self._spacing_actions = {}
        for label, value in _SPACINGS:
            act = QAction(label, self, checkable=True)
            act.triggered.connect(lambda _=False, v=value: self._on_spacing(v))
            self._spacing_menu.addAction(act)
            self._spacing_actions[value] = act
        self._spacing_menu.addSeparator()
        custom = QAction("Custom…", self)
        custom.triggered.connect(self._on_spacing_custom)
        self._spacing_menu.addAction(custom)
        self._spacing_btn.setMenu(self._spacing_menu)
        self._spacing_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(self._spacing_btn)

        self._btn_bullets = self._btn("•", "Bullet list", True)
        self._btn_bullets.clicked.connect(self._on_bullets)
        row.addWidget(self._btn_bullets)
        self._btn_numbers = self._btn("1.", "Numbered list", True)
        self._btn_numbers.clicked.connect(self._on_numbers)
        row.addWidget(self._btn_numbers)

        self._btn_super = self._btn("x²", "Superscript", True)
        self._btn_super.clicked.connect(lambda: self._toggle_script(True))
        row.addWidget(self._btn_super)
        self._btn_sub = self._btn("x₂", "Subscript", True)
        self._btn_sub.clicked.connect(lambda: self._toggle_script(False))
        row.addWidget(self._btn_sub)

        self._btn_upper = self._btn("AA", "UPPERCASE", True)
        self._btn_upper.clicked.connect(lambda: self._on_case(True))
        row.addWidget(self._btn_upper)
        self._btn_lower = self._btn("aa", "lowercase", True)
        self._btn_lower.clicked.connect(lambda: self._on_case(False))
        row.addWidget(self._btn_lower)

        self._btn_rtl = self._btn("RTL", "Right-to-left block", True)
        self._btn_rtl.clicked.connect(lambda: self._on_direction(True))
        row.addWidget(self._btn_rtl)
        self._btn_ltr = self._btn("LTR", "Left-to-right block", True)
        self._btn_ltr.clicked.connect(lambda: self._on_direction(False))
        row.addWidget(self._btn_ltr)

        self._btn_hr = self._btn("―", "Horizontal line")
        self._btn_hr.clicked.connect(self._on_hr)
        row.addWidget(self._btn_hr)

    # ─── editor binding ─────────────────────────────────────────────────

    def set_editor(self, edit: QTextEdit | None):
        if self._edit is not None:
            try:
                self._edit.cursorPositionChanged.disconnect(self.refresh_state)
                self._edit.undoAvailable.disconnect(self._btn_undo.setEnabled)
                self._edit.redoAvailable.disconnect(self._btn_redo.setEnabled)
            except (RuntimeError, TypeError):
                pass
        self._edit = edit
        if edit is not None:
            edit.cursorPositionChanged.connect(self.refresh_state)
            edit.undoAvailable.connect(self._btn_undo.setEnabled)
            edit.redoAvailable.connect(self._btn_redo.setEnabled)
            self._btn_undo.setEnabled(edit.document().isUndoAvailable())
            self._btn_redo.setEnabled(edit.document().isRedoAvailable())
        self.refresh_state()

    def _merge(self, fmt: QTextCharFormat):
        """Apply char format to selection (or typing format when none)."""
        if self._edit is None:
            return
        if self.fan_out is not None:
            self.fan_out(fmt)  # designer fans out; keeps deck selection
            self.refresh_state()
            return
        cursor = self._edit.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self._edit.mergeCurrentCharFormat(fmt)
        self.format_applied.emit()
        self.refresh_state()

    # ─── row 1 slots ────────────────────────────────────────────────────

    def _selection_weight_is_bold(self) -> bool:
        if self._edit is None:
            return False
        return self._edit.textCursor().charFormat().fontWeight() >= 600

    def _effective_bold(self) -> bool:
        """Bold as DISPLAYED right now: the run's own weight when it has
        one, else the theme baseline. This is the pre-click state, so the
        toggle flips away from what the operator saw lit."""
        if self._edit is None:
            return bool(self._theme_defaults.get("bold"))
        cf = self._edit.textCursor().charFormat()
        if cf.hasProperty(QTextFormat.Property.FontWeight):
            return cf.fontWeight() >= 600
        return bool(self._theme_defaults.get("bold"))

    def _toggle_bold(self):
        # NB: `clicked` fires AFTER Qt flips the button, so the button
        # state is the POST-click value — reading it would apply the
        # format the operator just turned off. Use the pre-click
        # effective state instead.
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal
                          if self._effective_bold()
                          else QFont.Weight.Bold)
        self._merge(fmt)

    def _toggle_italic(self):
        if self._edit is None:
            return
        cur = self._edit.textCursor().charFormat().fontItalic()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not cur)
        self._merge(fmt)

    def _toggle_strike(self):
        if self._edit is None:
            return
        new = not self._edit.textCursor().charFormat().fontStrikeOut()
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(new)
        # Record, don't clear: a loaded strike=false must flip to true in
        # the txt (a cleared prop would keep serializing false).
        fmt.setProperty(SO_PROP, new)
        self._merge(fmt)

    def _toggle_underline(self):
        if self._edit is None:
            return
        new = (self._edit.textCursor().charFormat().underlineStyle()
               == QTextCharFormat.UnderlineStyle.NoUnderline)
        fmt = QTextCharFormat()
        fmt.setFontUnderline(new)
        # Same as strike: Qt6 never marks the bool, so the prop IS the txt.
        fmt.setProperty(UL_PROP, new)
        self._merge(fmt)

    def _on_font_family(self, font: QFont):
        fmt = QTextCharFormat()
        # Metadata only: families render on preview, never in the pane.
        fmt.setProperty(FONT_PROP, font.family())
        self._merge(fmt)

    def _current_size_px(self) -> int:
        if self._edit is None:
            return 20
        cf = self._edit.textCursor().charFormat()
        if cf.hasProperty(SIZE_PROP):
            try:
                return max(1, int(cf.property(SIZE_PROP)))
            except (TypeError, ValueError):
                pass
        pt = cf.fontPointSize()
        if not pt:
            return 20
        return max(1, round(pt / _PT_PER_PX))

    def _apply_size_px(self, px: int):
        fmt = QTextCharFormat()
        # Metadata only: the edit pane renders one fixed size; the
        # nominal px rides along for serialization + preview.
        fmt.setProperty(SIZE_PROP, max(1, px))
        self._merge(fmt)

    def _step_size(self, delta: int):
        px = self._current_size_px()
        steps = sorted(set(_SIZES_PX + [px]))
        idx = steps.index(px)
        self._apply_size_px(steps[min(len(steps) - 1, max(0, idx + delta))])

    def _on_size_combo(self):
        try:
            self._apply_size_px(int(self._size_combo.currentText()))
        except ValueError:
            pass

    def _on_size_typed(self):
        self._on_size_combo()
        if self._edit is not None:
            self._edit.setFocus()

    def _outline_fmt(self, on: bool) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if on:
            # Prop only (no tint cue): outlines render on preview, never
            # in the pane.
            fmt.setProperty(OUTLINE_PROP, f"{self._outline_width}px {self._outline_color}")
        else:
            fmt.clearProperty(OUTLINE_PROP)
            fmt.clearBackground()
        return fmt

    def _on_outline_toggled(self):
        on = self._btn_outline.isChecked()
        self._btn_outline_color.setVisible(on)
        self._outline_size.setVisible(on)
        if on:
            self._merge(self._outline_fmt(True))
        else:
            self._remove_outline_property()

    def set_outline_color(self, hex_color: str):
        self._outline_color = hex_color
        self._btn_outline_color.setStyleSheet(f"color: {hex_color};")
        if self._btn_outline.isChecked():
            self._merge(self._outline_fmt(True))

    # ── shadow ──────────────────────────────────────────────────────────
    def _shadow_value(self, on: bool = True) -> str:
        if not on:
            return SHADOW_OFF
        return (f"{self._shadow_size_px}px {self._shadow_opacity_pct}% "
                f"{self._shadow_distance_px}px {self._shadow_color} "
                f"{self._shadow_angle_deg}")

    def _shadow_fmt(self, on: bool = True) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setProperty(SHADOW_PROP, self._shadow_value(on))
        return fmt

    def _current_shadow(self) -> str | None:
        """The shadow actually in effect at the caret, else None."""
        if self._edit is None:
            return None
        cf = self._edit.textCursor().charFormat()
        if cf.hasProperty(SHADOW_PROP):
            raw = cf.property(SHADOW_PROP)
            if raw and raw != SHADOW_OFF:
                return raw
        return None

    def _apply_shadow_keeper(self, moving: str = ""):
        """Size/opacity/distance/angle changes must not drop the run's own
        color or angle. `moving` names the knob just turned, which keeps its
        new value instead of being read back from the run."""
        current = self._current_shadow()
        if current:
            parsed = _parse_shadow_value(current)
            if parsed:
                self._shadow_color = parsed[3]
                if moving != "angle":
                    self._shadow_angle_deg = parsed[4]

    def _on_shadow_toggled(self):
        on = self._btn_shadow.isChecked()
        for w in (self._btn_shadow_color, self._shadow_size,
                  self._shadow_opacity, self._shadow_distance,
                  self._shadow_angle):
            w.setVisible(on)
        self._merge(self._shadow_fmt(on))

    def set_shadow_color(self, hex_color: str):
        self._shadow_color = hex_color
        self._btn_shadow_color.setStyleSheet(f"color: {hex_color};")
        if self._btn_shadow.isChecked():
            self._merge(self._shadow_fmt(True))

    def _on_shadow_color(self):
        color = QColorDialog.getColor(QColor(self._shadow_color), self,
                                      "Shadow color")
        if color.isValid():
            self.set_shadow_color(color.name())

    def _on_shadow_size_changed(self, px: int):
        self._shadow_size_px = max(1, min(25, int(px)))
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper("angle")
            self._merge(self._shadow_fmt(True))

    def _on_shadow_opacity_changed(self, pct: int):
        self._shadow_opacity_pct = max(0, min(100, int(pct)))
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper("angle")
            self._merge(self._shadow_fmt(True))

    def _on_shadow_distance_changed(self, px: int):
        self._shadow_distance_px = max(0, min(60, int(px)))
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper("angle")
            self._merge(self._shadow_fmt(True))

    def _on_shadow_angle_changed(self, deg: int):
        self._shadow_angle_deg = int(deg) % 360
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper("angle")
            self._merge(self._shadow_fmt(True))

    def _current_outline_color(self) -> str:
        if self._edit is None:
            return self._outline_color
        cf = self._edit.textCursor().charFormat()
        try:
            if cf.hasProperty(OUTLINE_PROP):
                raw = cf.property(OUTLINE_PROP)
                if raw and raw != OUTLINE_OFF:
                    return _parse_outline_value(raw)[0]
        except Exception:
            pass
        return self._outline_color

    def _on_outline_size_changed(self, px: int):
        self._outline_width = max(1, min(25, int(px)))
        if self._btn_outline.isChecked():
            # Keep the run's existing color; only the width changed.
            self._outline_color = self._current_outline_color()
            self._merge(self._outline_fmt(True))

    def _remove_outline_property(self):
        """Turn outline off for the selection (or the caret's run).

        Writes the OUTLINE_OFF sentinel rather than clearing the property:
        a theme whose `text_shadow` outlines text would otherwise re-assert
        the outline on the very next refresh, and the toggle would look
        broken. mergeCharFormat *sets* the sentinel, so the operator's
        selection survives.
        """
        if self.fan_out_remove_outline is not None:
            self.fan_out_remove_outline()
            self.format_applied.emit()
            self.refresh_state()
            return
        if self._edit is None:
            return
        cursor = self._edit.textCursor()
        if cursor.hasSelection():
            set_outline_off(cursor.document(),
                            cursor.selectionStart(), cursor.selectionEnd())
        else:
            fmt = QTextCharFormat(cursor.charFormat())
            fmt.setProperty(OUTLINE_PROP, OUTLINE_OFF)
            self._edit.setCurrentCharFormat(fmt)
        self.format_applied.emit()
        self.refresh_state()

    def _on_outline_color(self):
        color = QColorDialog.getColor(QColor(self._outline_color), self,
                                      "Outline color")
        if color.isValid():
            self.set_outline_color(color.name())

    def _on_text_color(self):
        if self._edit is None:
            return
        cur = self._edit.textCursor().charFormat().foreground()
        start = cur.color() if isinstance(cur, QBrush) else QColor("#ffffff")
        color = QColorDialog.getColor(start, self, "Text color")
        if color.isValid():
            fmt = QTextCharFormat()
            # Metadata only: colors render on preview, never in the pane.
            fmt.setProperty(COLOR_PROP, color.name())
            self._merge(fmt)

    def _on_clear(self):
        if self._edit is None:
            return
        fmt = QTextCharFormat()  # empty = all defaults
        fmt.clearProperty(UL_PROP)
        fmt.clearProperty(SO_PROP)
        fmt.clearProperty(OUTLINE_PROP)
        fmt.clearProperty(SHADOW_PROP)
        cursor = self._edit.textCursor()
        if cursor.hasSelection():
            # mergeCharFormat with defaults won't unset; select+reset instead.
            cursor.setCharFormat(QTextCharFormat())
            self._edit.setTextCursor(cursor)
        else:
            self._edit.setCurrentCharFormat(QTextCharFormat())
        self.format_applied.emit()
        self.refresh_state()

    def _do_undo(self):
        if self._edit is not None:
            self._edit.undo()

    def _do_redo(self):
        if self._edit is not None:
            self._edit.redo()

    def _on_more_toggled(self, on: bool):
        self._row2.setVisible(on)

    # ─── row 2 slots ────────────────────────────────────────────────────

    def _on_align(self, key: str):
        if self._edit is None:
            return
        # Metadata only: alignment renders on preview, never in the pane.
        self._merge_block_prop(ALIGN_PROP, key)
        self.format_applied.emit()
        self.refresh_state()

    def _on_spacing(self, value: float):
        self.set_deck_spacing(value)
        self.deck_format_changed.emit({"spacing": value})

    def set_theme_defaults(self, defaults: dict | None):
        """Adopt the active theme's baseline formatting (see _theme_defaults)."""
        self._theme_defaults = dict(defaults or {})
        self.refresh_state()

    def set_deck_spacing(self, value: float | None):
        """Reflect the deck's spacing in the menu (no signal)."""
        self._deck_spacing = value
        for v, act in self._spacing_actions.items():
            act.setChecked(v == value)

    def _on_spacing_custom(self):
        from PyQt6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getDouble(self, "Custom spacing",
                                           "Line spacing (0.5 – 3.0):",
                                           self._deck_spacing or 1.0,
                                           0.5, 3.0, 2)
        if ok:
            self._on_spacing(round(value, 2))

    def _toggle_list_prefix(self, ordered: bool):
        """Toggle a literal • / N. prefix on each selected block."""
        if self._edit is None:
            return
        cursor = self._edit.textCursor()
        doc = self._edit.document()
        start = doc.findBlock(cursor.selectionStart())
        end = doc.findBlock(cursor.selectionEnd())
        cursor.beginEditBlock()
        n = 0
        b = start
        while True:
            n += 1
            text = b.text()
            bcursor = QTextCursor(b)
            if ordered:
                import re as _re
                m = _re.match(r"^\d+\.\s+", text)
                if m:
                    bcursor.setPosition(b.position() + len(m.group(0)),
                                        QTextCursor.MoveMode.KeepAnchor)
                    bcursor.removeSelectedText()
                else:
                    bcursor.setPosition(b.position())
                    bcursor.insertText(f"{n}. ")
            else:
                if text.startswith("• "):
                    bcursor.setPosition(b.position())
                    bcursor.setPosition(b.position() + 2,
                                        QTextCursor.MoveMode.KeepAnchor)
                    bcursor.removeSelectedText()
                else:
                    bcursor.setPosition(b.position())
                    bcursor.insertText("• ")
            if b == end:
                break
            b = b.next()
            if not b.isValid():
                break
        cursor.endEditBlock()
        self.format_applied.emit()
        self.refresh_state()

    def _on_bullets(self):
        self._toggle_list_prefix(ordered=False)

    def _on_numbers(self):
        self._toggle_list_prefix(ordered=True)

    def _toggle_script(self, super_: bool):
        if self._edit is None:
            return
        from PyQt6.QtGui import QTextCharFormat as _CF
        want = (_CF.VerticalAlignment.AlignSuperScript if super_
                else _CF.VerticalAlignment.AlignSubScript)
        cur = self._edit.textCursor().charFormat().verticalAlignment()
        fmt = QTextCharFormat()
        fmt.setVerticalAlignment(
            _CF.VerticalAlignment.AlignNormal if cur == want else want)
        self._merge(fmt)

    def _on_case(self, upper: bool):
        fmt = QTextCharFormat()
        # Metadata only: case renders on preview, never in the pane.
        fmt.setProperty(CASE_PROP, "upper" if upper else "lower")
        self._merge(fmt)

    def _on_direction(self, rtl: bool):
        if self._edit is None:
            return
        self._merge_block_prop(
            DIR_PROP, "rtl" if rtl else "ltr")
        self.format_applied.emit()
        self.refresh_state()

    def _merge_block_prop(self, prop_id, value):
        """Merge one block metadata prop across the selection (or the
        cursor block when there is none). Native block metrics stay
        untouched, so the edit pane stays inviolable."""
        if self._edit is None:
            return
        cursor = self._edit.textCursor()
        doc = self._edit.document()
        if cursor.hasSelection():
            start = doc.findBlock(cursor.selectionStart())
            end = doc.findBlock(cursor.selectionEnd())
        else:
            start = end = cursor.block()
        cursor.beginEditBlock()
        try:
            block = start
            while True:
                fmt = QTextBlockFormat()
                fmt.setProperty(prop_id, value)
                bcursor = QTextCursor(block)
                bcursor.mergeBlockFormat(fmt)
                if block == end or not block.next().isValid():
                    break
                block = block.next()
        finally:
            cursor.endEditBlock()

    def _on_hr(self):
        if self._edit is None:
            return
        insert_hr_at(self._edit.textCursor())
        self._edit.setFocus()
        self.format_applied.emit()

    # ─── cursor probing ─────────────────────────────────────────────────

    def refresh_state(self):
        """Mirror the effective formats onto the toggle buttons (cheap).

        Precedence: the run's own props (what the deck stores) first,
        then the theme baseline (what display already applies), so the
        ribbon shows what the operator will actually see on output.
        """
        theme = self._theme_defaults
        if self._edit is None:
            for b in (self._btn_bold, self._btn_italic, self._btn_strike,
                      self._btn_underline, self._btn_outline, self._btn_shadow,
                      self._btn_super,
                      self._btn_sub, self._btn_bullets, self._btn_numbers,
                      self._btn_rtl, self._btn_ltr,
                      *self._align_btns.values()):
                b.setChecked(False)
            self._btn_upper.setChecked(theme.get("case") == "upper")
            self._btn_lower.setChecked(theme.get("case") == "lower")
            self._btn_bold.setChecked(bool(theme.get("bold")))
            theme_outline = theme.get("outline")
            self._btn_outline.setChecked(bool(theme_outline))
            self._btn_outline_color.setVisible(False)
            self._outline_size.setVisible(False)
            self._btn_shadow.setChecked(False)
            self._btn_shadow_color.setVisible(False)
            for s in (self._shadow_size, self._shadow_opacity,
                      self._shadow_distance, self._shadow_angle):
                s.setVisible(False)
            if theme_outline:
                color, width = _parse_outline_value(theme_outline)
                self._outline_color = color
                self._outline_width = width
                self._btn_outline_color.setStyleSheet(
                    f"color: {self._outline_color};")
                self._outline_size.blockSignals(True)
                self._outline_size.setValue(width)
                self._outline_size.blockSignals(False)
            for key, btn in self._align_btns.items():
                btn.setChecked(key == theme.get("align"))
            return
        cursor = self._edit.textCursor()
        cf = cursor.charFormat()
        # Bold: an explicit run weight wins; otherwise the theme's.
        if cf.hasProperty(QTextFormat.Property.FontWeight):
            self._btn_bold.setChecked(cf.fontWeight() >= 600)
        else:
            self._btn_bold.setChecked(bool(theme.get("bold")))
        self._btn_italic.setChecked(bool(cf.fontItalic()))
        self._btn_strike.setChecked(bool(cf.fontStrikeOut()))
        self._btn_underline.setChecked(
            cf.underlineStyle() != QTextCharFormat.UnderlineStyle.NoUnderline)
        # Outline: an explicit run prop wins; OUTLINE_OFF is the operator
        # switching an inherited (theme) outline off; otherwise the theme's
        # text-shadow is the display's equivalent, so it shows as active.
        outline_raw = cf.property(OUTLINE_PROP) if cf.hasProperty(OUTLINE_PROP) else None
        outline_on = bool(outline_raw) and outline_raw != OUTLINE_OFF
        if not outline_on and outline_raw is None:
            outline_on = bool(theme.get("outline"))
        self._btn_outline.setChecked(outline_on)
        self._btn_outline_color.setVisible(outline_on)
        self._outline_size.setVisible(outline_on)
        # The swatch/size follow whatever actually renders: the run's own prop
        # when set, else the theme's outline value ("2px #000000"), so the
        # size box shows the thickness `outline=Npx` will broaden.
        effective = outline_raw if (outline_raw and outline_raw != OUTLINE_OFF) \
            else (theme.get("outline") if outline_on else None)
        if effective:
            color, width = _parse_outline_value(effective)
            self._outline_color = color
            self._outline_width = width
            self._btn_outline_color.setStyleSheet(f"color: {self._outline_color};")
            self._outline_size.blockSignals(True)
            self._outline_size.setValue(width)
            self._outline_size.blockSignals(False)
        # Shadow: an explicit SHADOW_PROP wins; SHADOW_OFF is the operator
        # switching it off; no prop and no theme value means inactive.
        shadow_raw = (cf.property(SHADOW_PROP)
                      if cf.hasProperty(SHADOW_PROP) else None)
        shadow_on = bool(shadow_raw) and shadow_raw != SHADOW_OFF
        self._btn_shadow.setChecked(shadow_on)
        self._btn_shadow_color.setVisible(shadow_on)
        for s in (self._shadow_size, self._shadow_opacity,
                  self._shadow_distance, self._shadow_angle):
            s.setVisible(shadow_on)
        if shadow_on:
            parsed = _parse_shadow_value(shadow_raw)
            if parsed:
                (self._shadow_size_px, self._shadow_opacity_pct,
                 self._shadow_distance_px, self._shadow_color,
                 self._shadow_angle_deg) = parsed
                self._btn_shadow_color.setStyleSheet(
                    f"color: {self._shadow_color};")
                for s, v in ((self._shadow_size, self._shadow_size_px),
                             (self._shadow_opacity, self._shadow_opacity_pct),
                             (self._shadow_distance,
                              self._shadow_distance_px),
                             (self._shadow_angle, self._shadow_angle_deg)):
                    s.blockSignals(True)
                    s.setValue(v)
                    s.blockSignals(False)
        va = cf.verticalAlignment()
        self._btn_super.setChecked(
            va == QTextCharFormat.VerticalAlignment.AlignSuperScript)
        self._btn_sub.setChecked(
            va == QTextCharFormat.VerticalAlignment.AlignSubScript)
        cap = cf.fontCapitalization()
        if cf.hasProperty(CASE_PROP):
            case_prop = cf.property(CASE_PROP)
            self._btn_upper.setChecked(case_prop == "upper")
            self._btn_lower.setChecked(case_prop == "lower")
        elif cap in (QFont.Capitalization.AllUppercase,
                     QFont.Capitalization.SmallCaps):
            self._btn_upper.setChecked(True)
            self._btn_lower.setChecked(False)
        elif cap == QFont.Capitalization.AllLowercase:
            self._btn_upper.setChecked(False)
            self._btn_lower.setChecked(True)
        else:
            self._btn_upper.setChecked(theme.get("case") == "upper")
            self._btn_lower.setChecked(theme.get("case") == "lower")
        bfmt = cursor.blockFormat()
        if bfmt.hasProperty(ALIGN_PROP):
            align_key = bfmt.property(ALIGN_PROP)
            for key, btn in self._align_btns.items():
                btn.setChecked(key == align_key)
        else:
            align = bfmt.alignment()
            if align and align != Qt.AlignmentFlag.AlignLeft:
                self._align_btns["left"].setChecked(
                    bool(align & Qt.AlignmentFlag.AlignLeft))
                self._align_btns["center"].setChecked(
                    bool(align & Qt.AlignmentFlag.AlignCenter))
                self._align_btns["right"].setChecked(
                    bool(align & Qt.AlignmentFlag.AlignRight))
                self._align_btns["justify"].setChecked(
                    bool(align & Qt.AlignmentFlag.AlignJustify))
            else:
                # No block alignment stored: the theme's alignment is what
                # display renders (center for the freeform slides theme).
                for key, btn in self._align_btns.items():
                    btn.setChecked(key == theme.get("align"))
        if bfmt.hasProperty(DIR_PROP):
            rtl = bfmt.property(DIR_PROP) == "rtl"
        else:
            rtl = (bfmt.layoutDirection() == Qt.LayoutDirection.RightToLeft)
        self._btn_rtl.setChecked(rtl)
        self._btn_ltr.setChecked(not rtl)
        text = cursor.block().text()
        self._btn_bullets.setChecked(text.startswith("• "))
        import re as _re
        self._btn_numbers.setChecked(bool(_re.match(r"^\d+\.\s+", text)))
        self._size_combo.setCurrentText(str(self._current_size_px()))
