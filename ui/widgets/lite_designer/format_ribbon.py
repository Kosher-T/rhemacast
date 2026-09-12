"""
ui/widgets/lite_designer/format_ribbon.py

Word-processor ribbon for the Lite Designer Freeform tab.

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
                             QTextEdit, QSizePolicy)
from PyQt6.QtGui import (QTextCharFormat, QTextCursor, QFont, QColor, QBrush,
                         QTextFormat, QAction)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.widgets.lite_designer.rich_txt import (
    OUTLINE_PROP, UL_PROP, SO_PROP, insert_hr_at)

_PT_PER_PX = 0.75
_SIZES_PX = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 44, 54, 62, 72]
_SPACINGS = [("Single", 1.0), ("1.15", 1.15), ("1.5", 1.5), ("Double", 2.0)]

_RIBBON_STYLE = (
    "QWidget { background: rgba(15, 23, 42, 0.6); color: #f8fafc; }"
    "QToolButton { background: transparent; border: 1px solid transparent;"
    "  border-radius: 4px; padding: 3px 7px; font-size: 12px; font-weight: 700;"
    "  color: #cbd5e1; }"
    "QToolButton:hover { background: rgba(255,255,255,0.08); color: #f8fafc; }"
    "QToolButton:checked { background: rgba(59,130,246,0.25);"
    "  border-color: rgba(59,130,246,0.5); color: #93c5fd; }"
    "QToolButton:disabled { color: #475569; }"
    "QComboBox { background: rgba(0,0,0,0.3); color: #f8fafc;"
    "  border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;"
    "  padding: 2px 6px; font-size: 11px; }"
    "QComboBox QAbstractItemView { background: #1e293b; color: #f8fafc;"
    "  selection-background-color: rgba(59,130,246,0.3); }"
)


class FormatRibbon(QWidget):
    """Two-row formatting ribbon bound to one active editor at a time."""

    format_applied = pyqtSignal()       # any text/block formatting change
    deck_format_changed = pyqtSignal(dict)  # e.g. {"spacing": 1.5}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit: QTextEdit | None = None
        self._outline_color = "#000000"
        self._deck_spacing: float | None = None
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

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal
                          if self._selection_weight_is_bold()
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
        cur = self._edit.textCursor().charFormat().fontStrikeOut()
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not cur)
        fmt.clearProperty(SO_PROP)  # direct edit wins over loaded txt value
        self._merge(fmt)

    def _toggle_underline(self):
        if self._edit is None:
            return
        cur = (self._edit.textCursor().charFormat().underlineStyle()
               != QTextCharFormat.UnderlineStyle.NoUnderline)
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not cur)
        fmt.clearProperty(UL_PROP)  # direct edit wins over loaded txt value
        self._merge(fmt)

    def _on_font_family(self, font: QFont):
        fmt = QTextCharFormat()
        fmt.setFontFamily(font.family())
        self._merge(fmt)

    def _current_size_px(self) -> int:
        if self._edit is None:
            return 20
        pt = self._edit.textCursor().charFormat().fontPointSize()
        if not pt:
            return 20
        return max(1, round(pt / _PT_PER_PX))

    def _apply_size_px(self, px: int):
        fmt = QTextCharFormat()
        fmt.setFontPointSize(max(1, px) * _PT_PER_PX)
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
            color = QColor(self._outline_color)
            fmt.setProperty(OUTLINE_PROP, self._outline_color)
            cue = QColor(color)
            cue.setAlpha(38)
            fmt.setBackground(QBrush(cue))
        else:
            fmt.clearProperty(OUTLINE_PROP)
            fmt.clearBackground()
        return fmt

    def _on_outline_toggled(self):
        on = self._btn_outline.isChecked()
        self._btn_outline_color.setVisible(on)
        self._merge(self._outline_fmt(on))

    def set_outline_color(self, hex_color: str):
        self._outline_color = hex_color
        self._btn_outline_color.setStyleSheet(f"color: {hex_color};")
        if self._btn_outline.isChecked():
            self._merge(self._outline_fmt(True))

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
            fmt.setForeground(QBrush(color))
            self._merge(fmt)

    def _on_clear(self):
        if self._edit is None:
            return
        fmt = QTextCharFormat()  # empty = all defaults
        fmt.clearProperty(UL_PROP)
        fmt.clearProperty(SO_PROP)
        fmt.clearProperty(OUTLINE_PROP)
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
        flag = {"left": Qt.AlignmentFlag.AlignLeft,
                "center": Qt.AlignmentFlag.AlignCenter,
                "right": Qt.AlignmentFlag.AlignRight,
                "justify": Qt.AlignmentFlag.AlignJustify}[key]
        self._edit.setAlignment(flag)
        self.format_applied.emit()
        self.refresh_state()

    def _on_spacing(self, value: float):
        self.set_deck_spacing(value)
        self.deck_format_changed.emit({"spacing": value})

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
        fmt.setFontCapitalization(
            QFont.Capitalization.AllUppercase if upper
            else QFont.Capitalization.AllLowercase)
        self._merge(fmt)

    def _on_direction(self, rtl: bool):
        if self._edit is None:
            return
        cursor = self._edit.textCursor()
        fmt = cursor.blockFormat()
        fmt.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl
                               else Qt.LayoutDirection.LeftToRight)
        cursor.mergeBlockFormat(fmt)
        self._edit.setTextCursor(cursor)
        self.format_applied.emit()
        self.refresh_state()

    def _on_hr(self):
        if self._edit is None:
            return
        insert_hr_at(self._edit.textCursor())
        self._edit.setFocus()
        self.format_applied.emit()

    # ─── cursor probing ─────────────────────────────────────────────────

    def refresh_state(self):
        """Mirror the cursor's formats onto the toggle buttons (cheap)."""
        if self._edit is None:
            for b in (self._btn_bold, self._btn_italic, self._btn_strike,
                      self._btn_underline, self._btn_outline, self._btn_super,
                      self._btn_sub, self._btn_upper, self._btn_lower,
                      self._btn_bullets, self._btn_numbers, self._btn_rtl,
                      self._btn_ltr, *self._align_btns.values()):
                b.setChecked(False)
            return
        cursor = self._edit.textCursor()
        cf = cursor.charFormat()
        self._btn_bold.setChecked(cf.fontWeight() >= 600)
        self._btn_italic.setChecked(bool(cf.fontItalic()))
        self._btn_strike.setChecked(bool(cf.fontStrikeOut()))
        self._btn_underline.setChecked(
            cf.underlineStyle() != QTextCharFormat.UnderlineStyle.NoUnderline)
        self._btn_outline.setChecked(cf.hasProperty(OUTLINE_PROP))
        self._btn_outline_color.setVisible(cf.hasProperty(OUTLINE_PROP))
        va = cf.verticalAlignment()
        self._btn_super.setChecked(
            va == QTextCharFormat.VerticalAlignment.AlignSuperScript)
        self._btn_sub.setChecked(
            va == QTextCharFormat.VerticalAlignment.AlignSubScript)
        cap = cf.fontCapitalization()
        self._btn_upper.setChecked(cap == QFont.Capitalization.AllUppercase)
        self._btn_lower.setChecked(cap == QFont.Capitalization.AllLowercase)
        align = self._edit.alignment()
        self._align_btns["left"].setChecked(bool(align & Qt.AlignmentFlag.AlignLeft))
        self._align_btns["center"].setChecked(bool(align & Qt.AlignmentFlag.AlignCenter))
        self._align_btns["right"].setChecked(bool(align & Qt.AlignmentFlag.AlignRight))
        self._align_btns["justify"].setChecked(bool(align & Qt.AlignmentFlag.AlignJustify))
        rtl = (cursor.blockFormat().layoutDirection()
               == Qt.LayoutDirection.RightToLeft)
        self._btn_rtl.setChecked(rtl)
        self._btn_ltr.setChecked(not rtl)
        text = cursor.block().text()
        self._btn_bullets.setChecked(text.startswith("• "))
        import re as _re
        self._btn_numbers.setChecked(bool(_re.match(r"^\d+\.\s+", text)))
        if cf.fontPointSize():
            self._size_combo.setCurrentText(
                str(max(1, round(cf.fontPointSize() / _PT_PER_PX))))
