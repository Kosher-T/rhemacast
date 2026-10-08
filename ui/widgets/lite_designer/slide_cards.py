"""
ui/widgets/lite_designer/slide_cards.py

Single slide card design matching the sketch exactly:
- Row 1: Index number (left) | Section textbox (wrapping, auto-growing) | Action pill (top-right)
- Row 2: Display textbox (indented under section textbox, wrapping, auto-growing)
- Dull colors when inactive, vibrant colors when in focus
- Zero size change upon highlight/activation
- No horizontal scrolling
"""

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QSizePolicy, QTextEdit, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSizeF, QPoint
from PyQt6.QtGui import QTextCursor, QTextOption

from ui.widgets.text_nav import (
    word_end_right_stop, word_span_at, smart_delete_extend,
)
from ui.widgets.lite_designer.rich_txt import txt_to_display_doc
from ui.styles import (
    SELECTION_BG, SELECTION_BORDER, SLATE_600,
    TEXT_PRIMARY, TEXT_FAINT, TEXT_MUTED, ACCENT, TEXT_SELECTION,
)

DISPLAY_TEXT_PX_DEFAULT = 13


def display_text_px() -> int:
    """Fixed edit-pane display size (settings-driven).

    Display textboxes (cards + live editor) render every run at this
    size — size params ride as metadata and only take effect on
    preview. Read live on each use; clamped to sanity.
    """
    try:
        from core.database import get_setting
        return max(6, min(72, int(get_setting(
            "slides.editor_font_size", str(DISPLAY_TEXT_PX_DEFAULT)))))
    except (TypeError, ValueError):
        return DISPLAY_TEXT_PX_DEFAULT


def move_to_word_end_right(cursor, keep_anchor=False) -> bool:
    """Custom Ctrl+Right: shared kernel (`text_nav.word_end_right_stop`),
    applied to the cursor. Returns True when handled (fall through to
    Qt default otherwise)."""
    block = cursor.block()
    offset = cursor.position() - block.position()
    stop = word_end_right_stop(block.text(), offset)
    if stop is None:
        return False
    mode = QTextCursor.MoveMode.KeepAnchor if keep_anchor \
        else QTextCursor.MoveMode.MoveAnchor
    cursor.setPosition(block.position() + stop, mode)
    return True


def word_ahead_stop(text: str, offset: int):
    """End-of-word stop for Ctrl+Delete: shared kernel
    (`text_nav.word_end_right_stop`). Punctuation clusters only —
    everything else is Qt default, same as every other textbox."""
    return word_end_right_stop(text, offset)


def select_word_at(cursor) -> bool:
    """Double-click word select: shared kernel (`text_nav.word_span_at`),
    applied to the cursor. Returns False (Qt default applies) when the
    cursor is not on word characters."""
    block = cursor.block()
    span = word_span_at(block.text(), cursor.position() - block.position())
    if span is None:
        return False
    base = block.position()
    cursor.setPosition(base + span[0])
    cursor.setPosition(base + span[1], QTextCursor.MoveMode.KeepAnchor)
    return True


def select_block(cursor):
    """Triple-click paragraph select: the whole block plus one trailing
    newline when one exists (last block: text only)."""
    block = cursor.block()
    doc = cursor.document()
    start = block.position()
    end = start + len(block.text())
    if end < doc.characterCount() - 1:
        end += 1  # swallow the block separator too
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)


class TripleTracker:
    """Counts rapid same-spot left presses: 1, 2, then 3 (triple-click).
    Any other button, timeout, or distance resets."""

    def __init__(self):
        self._count = 0
        self._at = 0.0
        self._pos = None

    def register(self, button, pos) -> int:
        import time
        from PyQt6.QtWidgets import QApplication
        if button != Qt.MouseButton.LeftButton:
            self._count = 0
            return 0
        now = time.monotonic()
        if self._count > 0 and self._pos is not None \
                and (now - self._at) * 1000.0 \
                <= QApplication.doubleClickInterval() \
                and (pos - self._pos).manhattanLength() \
                <= QApplication.startDragDistance():
            self._count += 1
        else:
            self._count = 1
        self._at = now
        self._pos = QPoint(pos)
        if self._count >= 3:
            self._count = 0
            return 3
        return self._count


# ── Stylesheets: Dull vs Vibrant ──────────────────────────────
_CARD_BASE = (
    "QFrame#SlideCard {{"
    "  background: {bg};"
    "  border: 1px solid {border};"
    "  border-radius: 8px;"
    "}}"
)
_CARD_NORMAL = _CARD_BASE.format(
    bg="rgba(161, 161, 170, 0.04)",
    border="rgba(255, 255, 255, 0.05)"
)
_CARD_ACTIVE = _CARD_BASE.format(
    bg=SELECTION_BG,
    border=SELECTION_BORDER
)

# Positional corners for the joined stack: touching edges are square
# (90°), outer edges keep the 8px round. Appended AFTER the state
# stylesheet AND carrying the same QFrame#SlideCard selector: a bare
# declaration would lose to the ID-selected base on specificity and
# silently never apply.
def _corner(which, px):
    return f"QFrame#SlideCard {{ border-{which}-radius: {px}px; }}"


_RADIUS_SINGLE = (_corner("top-left", 8) + _corner("top-right", 8)
                  + _corner("bottom-left", 8) + _corner("bottom-right", 8))
_RADIUS_TOP = (_corner("top-left", 8) + _corner("top-right", 8)
               + _corner("bottom-left", 0) + _corner("bottom-right", 0))
_RADIUS_MID = (_corner("top-left", 0) + _corner("top-right", 0)
               + _corner("bottom-left", 0) + _corner("bottom-right", 0))
_RADIUS_BOTTOM = (_corner("top-left", 0) + _corner("top-right", 0)
                  + _corner("bottom-left", 8) + _corner("bottom-right", 8))

# Index number (explicit QLabel selector: a bare rule would lose to an
# ancestor bare-QWidget rule on specificity)
_INDEX_NORMAL = (
    "QLabel {"
    "  color: " + SLATE_600 + "; font-size: 11px; font-weight: 700;"
    "  background: transparent; border: none;"
    "}"
)
_INDEX_ACTIVE = (
    "QLabel {"
    "  color: " + ACCENT + "; font-size: 11px; font-weight: 700;"
    "  background: transparent; border: none;"
    "}"
)

# Shared viewport rule: the textbox viewport is an unstyled QWidget child,
# so ancestor bare-QWidget borders would paint on it. Descendant selector
# outranks those rules.
_VIEWPORT_CLEAN = (
    "QTextEdit QWidget { background: transparent; border: none; }"
)

# Section textbox
_SECTION_NORMAL = (
    "QTextEdit {"
    "  background: transparent; color: " + TEXT_FAINT + ";"
    "  font-size: 12px; font-weight: 600;"
    "  border: none; padding: 0px;"
    "}"
    + _VIEWPORT_CLEAN
)
_SECTION_ACTIVE = (
    "QTextEdit {"
    "  background: transparent; color: " + ACCENT + ";"
    "  font-size: 12px; font-weight: 700;"
    "  border: none; padding: 0px;"
    "}"
    + _VIEWPORT_CLEAN
)

# Display textbox: glyph size comes ONLY from the interpolated font-size
# below (fixed via display_text_px). A bare-QWidget ancestor rule (the
# designer popup's 11px) would otherwise win over widget fonts, so the
# size must live in this QTextEdit-selected rule. Built per widget at
# creation (settings apply on next open — same contract as deck fonts).
def _display_box_style(active: bool, px: int) -> str:
    color = TEXT_PRIMARY if active else TEXT_FAINT
    sel = ("  selection-background-color: " + TEXT_SELECTION + ";"
           if active else "")
    return ("QTextEdit {"
            f"  background: transparent; color: {color};"
            f"  font-size: {px}px; border: none; padding: 0px;"
            f"{sel}" "}"
            + _VIEWPORT_CLEAN)

# Actions pill container
_ACTIONS_NORMAL = (
    "QFrame {"
    "  background: rgba(255, 255, 255, 0.03);"
    "  border: 1px solid rgba(255, 255, 255, 0.05);"
    "  border-radius: 11px;"
    "}"
)
_ACTIONS_ACTIVE = (
    "QFrame {"
    "  background: rgba(255, 255, 255, 0.06);"
    "  border: 1px solid rgba(255, 255, 255, 0.12);"
    "  border-radius: 11px;"
    "}"
)

# Action buttons
_BTN_NORMAL = (
    "QPushButton {"
    "  background: transparent; color: " + SLATE_600 + ";"
    "  border: none; border-radius: 4px;"
    "  padding: 1px 3px; font-size: 11px; font-weight: 700;"
    "}"
    "QPushButton:hover { color: " + TEXT_PRIMARY + "; background: rgba(255, 255, 255, 0.08); }"
)
_BTN_ACTIVE = (
    "QPushButton {"
    "  background: transparent; color: " + TEXT_MUTED + ";"
    "  border: none; border-radius: 4px;"
    "  padding: 1px 3px; font-size: 11px; font-weight: 700;"
    "}"
    "QPushButton:hover { color: " + TEXT_PRIMARY + "; background: rgba(255, 255, 255, 0.12); }"
)


class _SectionEdit(QTextEdit):
    """Auto-growing, wrapping single/multi-line textbox for slide section names."""

    def __init__(self, card: "SlideCard", parent=None):
        super().__init__(parent)
        self._card = card
        self._committed_text = ""
        self._triple = TripleTracker()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setPlaceholderText("Section…")
        self.textChanged.connect(self._on_text_changed)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _s: self._fit_height())

    def _fit_height(self):
        doc = self.document()
        if doc is None:
            return
        vp_w = self.viewport().width()
        if vp_w > 0 and doc.pageSize().width() != vp_w:
            doc.setPageSize(QSizeF(vp_w, -1))
        h = doc.documentLayout().documentSize().height()
        line_h = self.fontMetrics().height() + 2
        target_h = max(line_h, int(h) + 2)
        if self.height() != target_h:
            self.setFixedHeight(target_h)
            self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def _on_text_changed(self):
        self._fit_height()

    def set_section_text(self, text: str):
        val = (text or "").strip()
        if self.toPlainText() != val:
            self.blockSignals(True)
            self.setPlainText(val)
            self.blockSignals(False)
            self._committed_text = val
            self._fit_height()

    def focusInEvent(self, event):
        # Activate FIRST, take focus AFTER: the activation cascade
        # (host_editor show/raise, preview render) otherwise yanks focus
        # into the shared display editor and the section looks untypable.
        self._card.activated.emit(self._card._index)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._maybe_commit()

    def keyPressEvent(self, event):
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        mods = event.modifiers()
        # Ctrl+Enter (no Shift): commit first so the insert below cannot
        # shift indices under pending section text, then add a slide
        # after this one and continue typing there.
        if is_enter and (mods & Qt.KeyboardModifier.ControlModifier) \
                and not (mods & Qt.KeyboardModifier.ShiftModifier):
            self._maybe_commit()
            self._card.add_and_continue_requested.emit(self._card._index)
            return
        # Enter commits the section edit, Shift+Enter inserts newline
        if is_enter and not (mods & Qt.KeyboardModifier.ShiftModifier):
            self.clearFocus()
            return
        # Custom word-end hop onto punctuation clusters (Ctrl+Left stays Qt)
        if event.key() == Qt.Key.Key_Right and (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            cursor = self.textCursor()
            if move_to_word_end_right(
                    cursor,
                    keep_anchor=bool(event.modifiers()
                                     & Qt.KeyboardModifier.ShiftModifier)):
                self.setTextCursor(cursor)
                return
        # Smart Delete/Backspace (no Shift: Shift+Delete is cut and must
        # stay pristine). Selection rules extend the range, then fall
        # through so default deletion removes it in one undo step.
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) \
                and not (event.modifiers()
                         & (Qt.KeyboardModifier.ShiftModifier
                            | Qt.KeyboardModifier.AltModifier
                            | Qt.KeyboardModifier.MetaModifier)):
            mods = event.modifiers()
            cursor = self.textCursor()
            forward = event.key() == Qt.Key.Key_Delete
            if cursor.hasSelection():
                done = smart_delete_extend(
                    self.document(), cursor.selectionStart(),
                    cursor.selectionEnd(), forward)
                if done is not None:
                    cursor.setPosition(done[0])
                    cursor.setPosition(
                        done[1], QTextCursor.MoveMode.KeepAnchor)
                    self.setTextCursor(cursor)
            elif mods & Qt.KeyboardModifier.ControlModifier \
                    and event.key() == Qt.Key.Key_Delete:
                block = cursor.block()
                stop = word_ahead_stop(
                    block.text(), cursor.position() - block.position())
                if stop is not None:
                    cursor.setPosition(
                        block.position() + stop,
                        QTextCursor.MoveMode.KeepAnchor)
                    self.setTextCursor(cursor)
            # else: Qt default (incl. Ctrl+Backspace, which already
            # mirrors Ctrl+Left stops)
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # Explicit click-to-focus (same hardening as text_nav fields).
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.LeftButton \
                and self._triple.register(
                    event.button(), event.pos()) == 3:
            cursor = self.cursorForPosition(event.pos())
            select_block(cursor)
            self.setTextCursor(cursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._triple.register(event.button(), event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            cursor = self.cursorForPosition(event.pos())
            if select_word_at(cursor):
                self.setTextCursor(cursor)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _maybe_commit(self):
        raw = self.toPlainText().strip()
        flattened = " ".join(raw.splitlines()).strip()
        if flattened != self._committed_text:
            self._committed_text = flattened
            self._card.section_changed.emit(self._card._index, flattened)


class _DisplayBox(QTextEdit):
    """Auto-growing, read-only display textbox for inactive slide cards.

    Shows the restricted rich view (bold/italics/strike/underline only —
    see rich_txt.txt_to_display_doc); all other formatting renders as
    normal text here and fully on the preview screen. Never takes
    keyboard focus (no focus rect, no caret chrome); clicks route through
    `activated` and hand focus to the hosted live editor instead.
    """

    def __init__(self, card: "SlideCard", parent=None):
        super().__init__(parent)
        self._card = card
        self._raw = None  # last rendered slide txt (skip identical syncs)
        self._px = display_text_px()  # fixed at creation (see module note)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _s: self._fit_height())

    def _fit_height(self):
        doc = self.document()
        if doc is None:
            return
        vp_w = self.viewport().width()
        if vp_w > 0 and doc.pageSize().width() != vp_w:
            doc.setPageSize(QSizeF(vp_w, -1))
        h = doc.documentLayout().documentSize().height()
        line_h = self.fontMetrics().height() + 2
        if not doc.toPlainText().strip() and doc.blockCount() <= 1:
            target_h = line_h
        else:
            target_h = max(line_h, int(h) + 2)
        if self.height() != target_h:
            self.setFixedHeight(target_h)
            self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def set_content_text(self, text: str):
        val = (text or "").strip()
        if val == self._raw:
            return  # identical sync: zero churn (keeps tier selections)
        self._raw = val
        self.setDocument(txt_to_display_doc(val))
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _s: self._fit_height())
        self._fit_height()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._card.activated.emit(self._card._index)
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # NoFocus above means no caret/focus-rect chrome; hand focus
            # to the live editor hosted by the activation above.
            self._card.focus_editor()


class SlideCard(QFrame):
    """One slide card: index + section textbox + display textbox + action pill."""

    activated = pyqtSignal(int)
    section_changed = pyqtSignal(int, str)
    delete_requested = pyqtSignal(int)
    move_requested = pyqtSignal(int, int)
    add_after_requested = pyqtSignal(int)
    add_and_continue_requested = pyqtSignal(int)

    def __init__(self, index: int = 0, text: str = "", parent=None):
        super().__init__(parent)
        self._index = index
        self._active = False
        # Last painted visual state: re-polishing identical stylesheets
        # costs ~5ms a call (measured) with zero visual effect.
        self._painted_state = None
        self._joined_first = True
        self._joined_last = True
        self._editor = None
        self._editor_hosted = False

        self.setObjectName("SlideCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 2)
        root.setSpacing(6)

        # ── row 1: number | section textbox | controls ──
        r1 = QHBoxLayout()
        r1.setContentsMargins(0, 0, 0, 0)
        r1.setSpacing(8)

        self._idx_label = QLabel(str(index + 1))
        self._idx_label.setFixedWidth(18)
        self._idx_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        r1.addWidget(self._idx_label, 0, Qt.AlignmentFlag.AlignTop)

        self._chip = _SectionEdit(self)
        r1.addWidget(self._chip, 1, Qt.AlignmentFlag.AlignTop)

        self._actions = QFrame()
        self._actions.setFixedHeight(22)
        actions_layout = QHBoxLayout(self._actions)
        actions_layout.setContentsMargins(3, 1, 3, 1)
        actions_layout.setSpacing(2)

        self._btn_up = self._make_btn("\u2191")
        self._btn_up.clicked.connect(lambda: self.move_requested.emit(
            self._index, -1))
        actions_layout.addWidget(self._btn_up)

        self._btn_down = self._make_btn("\u2193")
        self._btn_down.clicked.connect(lambda: self.move_requested.emit(
            self._index, +1))
        actions_layout.addWidget(self._btn_down)

        self._btn_add = self._make_btn("+")
        self._btn_add.clicked.connect(
            lambda: self.add_after_requested.emit(self._index))
        actions_layout.addWidget(self._btn_add)

        self._btn_del = self._make_btn("\u00d7")
        self._btn_del.clicked.connect(
            lambda: self.delete_requested.emit(self._index))
        actions_layout.addWidget(self._btn_del)

        r1.addWidget(self._actions, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(r1)

        # ── row 2: display textbox (indented 26px under section textbox) ──
        r2 = QHBoxLayout()
        r2.setContentsMargins(0, 0, 0, 0)
        r2.setSpacing(0)
        r2.addSpacing(26)  # 18px (index width) + 8px (r1 spacing) = 26px indent

        self._display_container = QWidget()
        # Explicit selector: without it, an ancestor bare-QWidget rule
        # (e.g. the designer popup style) paints a border on this box.
        self._display_container.setStyleSheet(
            "QWidget { background: transparent; border: none; }")
        self._display_layout = QVBoxLayout(self._display_container)
        self._display_layout.setContentsMargins(0, 0, 0, 0)
        self._display_layout.setSpacing(0)

        self._display_box = _DisplayBox(self)
        self._display_layout.addWidget(self._display_box)

        r2.addWidget(self._display_container, 1)
        root.addLayout(r2)

        self.set_content_text(text)
        self._update_style()

    def _make_btn(self, symbol: str) -> QPushButton:
        btn = QPushButton(symbol)
        btn.setStyleSheet(_BTN_NORMAL)
        btn.setFixedSize(18, 18)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # ── public api ─────────────────────────────────────────────
    def set_index(self, index: int):
        self._index = index
        self._idx_label.setText(str(index + 1))

    def set_move_up_visible(self, visible: bool):
        self._btn_up.setVisible(visible)

    def set_move_down_visible(self, visible: bool):
        self._btn_down.setVisible(visible)

    def set_section(self, section: str):
        self._chip.set_section_text(section or "")

    def set_content_text(self, text: str):
        self._display_box.set_content_text(text or "")

    def set_active(self, active: bool):
        self._active = active
        self._update_style()

    def set_joined(self, first: bool, last: bool):
        """Position in the joined stack: outer edges stay rounded,
        touching edges go square. Single card = fully rounded."""
        self._joined_first = first
        self._joined_last = last
        self._update_style()

    def select_content(self):
        """Tier visualization: select all text in the chip + display box.

        Text only — cards never paint a selection state.
        """
        self._chip.selectAll()
        self._display_box.selectAll()

    def clear_content_selection(self):
        """Drop text selections in the chip + display box (keep carets)."""
        for box in (self._chip, self._display_box):
            cursor = box.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                box.setTextCursor(cursor)

    def host_editor(self, editor):
        if self._editor_hosted and self._editor is editor:
            return
        self.release_editor()
        self._editor = editor
        self._editor_hosted = True
        if self._display_box.height() > 0:
            editor.setFixedHeight(self._display_box.height())
        self._display_box.hide()
        self._display_layout.addWidget(editor)
        editor.show()
        editor.raise_()

    def release_editor(self):
        if self._editor is not None and self._editor_hosted:
            if self._editor.height() > 0:
                self._display_box.setFixedHeight(self._editor.height())
            self._display_layout.removeWidget(self._editor)
            self._editor.setParent(None)
            self._editor_hosted = False
            self._editor = None
            self._display_box.show()

    def focus_editor(self):
        """Focus the hosted live editor (after display-box clicks)."""
        if self._editor is not None and self._editor_hosted:
            self._editor.setFocus()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._index)
        super().mousePressEvent(event)

    def _update_style(self):
        # Selection tiers are text-only: cards paint active (focus) vs
        # idle and nothing else — there is no selected-card state.
        state = (bool(self._active),
                 bool(self._joined_first), bool(self._joined_last))
        if state == self._painted_state:
            return  # identical polish: skip, zero visual effect
        self._painted_state = state
        if self._active:
            base = _CARD_ACTIVE
            self._idx_label.setStyleSheet(_INDEX_ACTIVE)
            self._chip.setStyleSheet(_SECTION_ACTIVE)
            self._display_box.setStyleSheet(
                _display_box_style(True, self._display_box._px))
            self._actions.setStyleSheet(_ACTIONS_ACTIVE)
            for btn in (self._btn_up, self._btn_down, self._btn_add, self._btn_del):
                btn.setStyleSheet(_BTN_ACTIVE)
        else:
            base = _CARD_NORMAL
            self._idx_label.setStyleSheet(_INDEX_NORMAL)
            self._chip.setStyleSheet(_SECTION_NORMAL)
            self._display_box.setStyleSheet(
                _display_box_style(False, self._display_box._px))
            self._actions.setStyleSheet(_ACTIONS_NORMAL)
            for btn in (self._btn_up, self._btn_down, self._btn_add, self._btn_del):
                btn.setStyleSheet(_BTN_NORMAL)
        highlighted = self._active
        if self._joined_first and self._joined_last:
            radius = _RADIUS_SINGLE
        elif self._joined_first:
            radius = _RADIUS_TOP
        elif self._joined_last:
            radius = _RADIUS_BOTTOM
        else:
            radius = _RADIUS_MID
        # Unity seam: idle non-last cards drop the bottom edge so stacked
        # cards share a single 1px line; highlighted cards keep the full
        # outline so focus still traces the card shape. Same-selector rule
        # (see _corner): a bare declaration would lose to the base.
        seam = "" if (self._joined_last or highlighted) else \
            "QFrame#SlideCard { border-bottom: none; }"
        self.setStyleSheet(base + radius + seam)
