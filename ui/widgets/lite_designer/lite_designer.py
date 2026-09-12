"""
ui/widgets/lite_designer/lite_designer.py

The one Lite Designer popup: [ Freeform | Theme ] tabs under a shared
title bar (Reset / Save / x), built on the ThemeQuickEditor shell language.

Entry rules (plan section 9):
  - Deck context menu (later: schedule items) -> Freeform default, Theme open.
  - Theme context menu (Quick Edit) -> Theme default, Freeform GREYED OUT.

Freeform tab: FormatRibbon + slide cards (single shared live editor) +
  live DisplayView preview. Save is STRICTLY preview (same contract as
  Edit-as-Text): preview strip refreshes, live untouched.
Theme tab: today's quick-editor look verbatim (properties + preview).
"""

import copy

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QTextEdit, QLineEdit,
                             QScrollArea, QMessageBox, QStackedWidget)
from PyQt6.QtGui import QTextCursor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from ui.widgets.theme_properties_panel import ThemePropertiesPanel
from ui.widgets.theme_preview import ThemePreview
from ui.widgets.display_view import DisplayView
from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.widgets.lite_designer.format_ribbon import FormatRibbon
from ui.widgets.lite_designer.slide_cards import SlideCard
from ui.widgets.lite_designer.rich_txt import (
    txt_to_doc, doc_to_txt, apply_spacing_to_doc)
from ui.styles import BLUE_500
import core.theme_loader
from core.slide_parser import deck_to_txt, parse_slide_txt, inline_markup_to_html

_POPUP_STYLE = (
    "QWidget {"
    "  background: rgba(15, 23, 42, 0.97);"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 16px;"
    "  color: #f8fafc;"
    "  font-family: 'Nunito', sans-serif;"
    "  font-size: 11px;"
    "}"
)
_TITLE_BAR_STYLE = ("QFrame { background: transparent;"
                    "  border-bottom: 1px solid rgba(255,255,255,0.06); }")
_TITLE_LABEL_STYLE = ("background: transparent; border: none; color: #f8fafc;"
                      "font-size: 12px; font-weight: 700;")
_BADGE_STYLE = ("background: rgba(6, 182, 212, 0.15); color: #22d3ee;"
                "border: 1px solid rgba(6, 182, 212, 0.3); border-radius: 4px;"
                "padding: 1px 8px; font-size: 10px; font-weight: 700;")
_LIVE_BADGE_STYLE = ("background: rgba(239, 68, 68, 0.15); color: #f87171;"
                     "border: 1px solid rgba(239,68,68,0.4); border-radius: 4px;"
                     "padding: 1px 8px; font-size: 10px; font-weight: 700;")
_ICON_STYLE = ("background: transparent; border: none; color: #22d3ee;"
               "font-size: 14px;")
_BTN_GHOST = ("QPushButton { background: transparent; color: #94a3b8;"
              "  border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;"
              "  padding: 4px 12px; font-size: 10px; font-weight: 600; }"
              "QPushButton:hover { background: rgba(255,255,255,0.06);"
              "  color: #f8fafc; }")
_BTN_PRIMARY = ("QPushButton { background: " + BLUE_500 + "; color: #ffffff;"
                "  border: none; border-radius: 4px; padding: 4px 16px;"
                "  font-size: 10px; font-weight: 700; }"
                "QPushButton:hover { background: #2563eb; }"
                "QPushButton:pressed { background: #1d4ed8; }")
_BTN_EXPAND = ("QPushButton { background: rgba(6,182,212,0.15); color: #22d3ee;"
               "  border: 1px solid rgba(6,182,212,0.3); border-radius: 4px;"
               "  padding: 4px 14px; font-size: 10px; font-weight: 700; }"
               "QPushButton:hover { background: rgba(6,182,212,0.25); }")
_BTN_CLOSE = ("QPushButton { background: transparent; color: #64748b;"
              "  border: none; border-radius: 4px; padding: 4px 8px;"
              "  font-size: 13px; font-weight: 700; }"
              "QPushButton:hover { background: rgba(239,68,68,0.15);"
              "  color: #ef4444; }")
_TAB_ACTIVE = ("QPushButton { background: rgba(59,130,246,0.2); color: #60a5fa;"
               "  border: none; border-radius: 4px; font-size: 11px;"
               "  font-weight: 700; padding: 4px 18px; }")
_TAB_INACTIVE = ("QPushButton { background: transparent; color: #64748b;"
                 "  border: none; border-radius: 4px; font-size: 11px;"
                 "  font-weight: 700; padding: 4px 18px; }"
                 "QPushButton:hover { color: #94a3b8; }"
                 "QPushButton:disabled { color: #334155; }")
_TITLE_FIELD_STYLE = ("QLineEdit { background: rgba(0,0,0,0.3); color: #f8fafc;"
                      "  border: 1px solid rgba(255,255,255,0.1);"
                      "  border-radius: 6px; padding: 4px 10px; font-size: 13px;"
                      "  font-weight: 700; }")
_EDITOR_STYLE = ("QTextEdit { background: rgba(255,255,255,0.05); color: #f1f5f9;"
                 "  border: none; border-radius: 4px;"
                 "  padding: 6px; font-size: 13px; selection-background-color:"
                 "  rgba(59,130,246,0.4); }")
_STATUS_STYLE = ("background: transparent; border: none; color: #64748b;"
                 "font-size: 10px;")


class LiteDesigner(QWidget):
    """Single-popup editor with Freeform + Theme tabs."""

    deck_saved = pyqtSignal(int)
    theme_saved = pyqtSignal(str)
    edit_full_requested = pyqtSignal(str)

    def __init__(self, parent=None, deck_id=None, theme_name="slides",
                 default_tab="freeform", freeform_enabled=True, live=False):
        super().__init__(parent)
        self._deck_id = deck_id
        self._theme_name = theme_name
        self._live = live
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(1280, 720)
        self.setStyleSheet(_POPUP_STYLE)

        self._slides = []
        self._title = ""
        self._format = {}
        self._docs = {}
        self._active = 0
        self._dirty = False
        self._splitting = False
        self._cards = []

        self._original_theme = {}
        self._working_theme = {}
        self._theme_dirty = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_title_bar())
        root.addWidget(self._build_tab_bar())

        self._stack = QStackedWidget()
        self._freeform_page = self._build_freeform_page()
        self._theme_page = self._build_theme_page()
        self._stack.addWidget(self._freeform_page)
        self._stack.addWidget(self._theme_page)
        root.addWidget(self._stack, 1)

        self._tab_freeform.setEnabled(freeform_enabled)
        if not freeform_enabled:
            self._tab_freeform.setToolTip(
                "Freeform editing needs a deck (theme Quick Edit has none)")
        if default_tab == "theme" or not freeform_enabled or deck_id is None:
            self._switch_tab("theme")
        else:
            self._switch_tab("freeform")

        if deck_id is not None:
            self._load_deck()
        self._load_theme()

    def _build_title_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(_TITLE_BAR_STYLE)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(8)
        icon = QLabel("PNG")
        icon.setStyleSheet(_ICON_STYLE)
        icon.setFixedWidth(20)
        lay.addWidget(icon)
        title = QLabel("Lite Designer")
        title.setStyleSheet(_TITLE_LABEL_STYLE)
        lay.addWidget(title)
        self._badge = QLabel("")
        self._badge.setStyleSheet(_BADGE_STYLE)
        lay.addWidget(self._badge)
        if self._live:
            live = QLabel("LIVE - preview only")
            live.setStyleSheet(_LIVE_BADGE_STYLE)
            lay.addWidget(live)
        lay.addStretch()
        self._status = QLabel("")
        self._status.setStyleSheet(_STATUS_STYLE)
        lay.addWidget(self._status)
        btn_full = QPushButton("Edit in Full Designer")
        btn_full.setStyleSheet(_BTN_EXPAND)
        btn_full.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_full.clicked.connect(
            lambda: self.edit_full_requested.emit(self._theme_name))
        lay.addWidget(btn_full)
        btn_reset = QPushButton("Reset")
        btn_reset.setStyleSheet(_BTN_GHOST)
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._on_reset)
        lay.addWidget(btn_reset)
        btn_save = QPushButton("Save")
        btn_save.setToolTip("Apply to preview (stays open)")
        btn_save.setStyleSheet(_BTN_PRIMARY)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._on_save)
        lay.addWidget(btn_save)
        btn_close = QPushButton("X")
        btn_close.setStyleSheet(_BTN_CLOSE)
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self._on_close)
        lay.addWidget(btn_close)
        return bar

    def _build_tab_bar(self):
        bar = QFrame()
        bar.setFixedHeight(34)
        bar.setStyleSheet("QFrame { background: rgba(15,23,42,0.6);"
                          "  border-bottom: 1px solid rgba(255,255,255,0.06); }")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(4)
        self._tab_freeform = QPushButton("Freeform")
        self._tab_freeform.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_freeform.clicked.connect(lambda: self._switch_tab("freeform"))
        lay.addWidget(self._tab_freeform)
        self._tab_theme = QPushButton("Theme")
        self._tab_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_theme.clicked.connect(lambda: self._switch_tab("theme"))
        lay.addWidget(self._tab_theme)
        lay.addStretch()
        return bar

    def _switch_tab(self, which):
        is_free = which == "freeform"
        self._tab_freeform.setStyleSheet(_TAB_ACTIVE if is_free else _TAB_INACTIVE)
        self._tab_theme.setStyleSheet(_TAB_ACTIVE if not is_free else _TAB_INACTIVE)
        self._stack.setCurrentIndex(0 if is_free else 1)
        badge_text = (self._title or "(untitled)") if is_free else self._theme_name
        self._badge.setText(badge_text)

    def _build_freeform_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._ribbon = FormatRibbon()
        self._ribbon.format_applied.connect(self._on_content_edited)
        self._ribbon.deck_format_changed.connect(self._on_deck_format_patch)
        lay.addWidget(self._ribbon)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        left = QFrame()
        left.setFixedWidth(440)
        left.setStyleSheet("QFrame { background: transparent;"
                           "  border-right: 1px solid rgba(255,255,255,0.06); }")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 8, 10, 8)
        ll.setSpacing(6)
        self._title_field = QLineEdit()
        self._title_field.setStyleSheet(_TITLE_FIELD_STYLE)
        self._title_field.setPlaceholderText("Deck title...")
        self._title_field.editingFinished.connect(self._on_title_finished)
        ll.addWidget(self._title_field)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._cards_host = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch()
        scroll.setWidget(self._cards_host)
        ll.addWidget(scroll, 1)

        add_btn = QPushButton("+ Add slide")
        add_btn.setStyleSheet(_BTN_GHOST)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_last)
        ll.addWidget(add_btn)
        body.addWidget(left)

        self._edit = QTextEdit()
        self._edit.setStyleSheet(_EDITOR_STYLE)
        self._edit.textChanged.connect(self._on_editor_text)
        self._ribbon.set_editor(self._edit)

        right = QFrame()
        right.setStyleSheet("QFrame { background: transparent; }")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(4)
        lbl = QLabel("Preview")
        lbl.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 700;"
                          "letter-spacing: 1px; background: transparent;")
        rl.addWidget(lbl)
        frame = QFrame()
        frame.setStyleSheet("background: black;"
                            "border: 1px solid rgba(255,255,255,0.08);"
                            "border-radius: 8px;")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        self._preview = DisplayView(live_mode=False)
        self._preview.setMinimumHeight(1)
        fl.addWidget(self._preview)
        self._ar = AspectRatioWidget(frame, aspect_ratio=16.0 / 9.0,
                                     min_width=160, max_width=800)
        rl.addWidget(self._ar, 1)
        body.addWidget(right, 1)

        lay.addLayout(body, 1)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._refresh_preview)
        return page

    def _build_theme_page(self):
        page = QWidget()
        body = QHBoxLayout(page)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        left = QFrame()
        left.setFixedWidth(380)
        left.setStyleSheet("QFrame { background: transparent;"
                           "  border-right: 1px solid rgba(255,255,255,0.06); }")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        self._props = ThemePropertiesPanel()
        self._props.theme_changed.connect(self._on_theme_changed)
        ll.addWidget(self._props)
        body.addWidget(left)
        right = QFrame()
        right.setStyleSheet("QFrame { background: transparent; }")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(0)
        self._theme_preview = ThemePreview(verse_key="popup", label="Preview",
                                           min_width=160, max_width=800)
        rl.addWidget(self._theme_preview, 1)
        body.addWidget(right, 1)
        return page

    # ─── deck load / serialize ──────────────────────────────────────

    def _load_deck(self):
        from core.slide_service import get_deck
        deck = get_deck(self._deck_id) if self._deck_id is not None else None
        if not deck:
            return
        self._slides = [dict(s) for s in deck.get("slides", [])] or [
            {"section": None, "text": ""}]
        self._title = deck.get("title") or ""
        self._format = dict(deck.get("format") or {})
        self._docs = {}
        self._active = 0
        self._dirty = False
        self._title_field.setText(self._title)
        self._ribbon.set_deck_spacing(self._format.get("spacing"))
        self._rebuild_cards()
        self._activate(0)
        self._refresh_preview()

    def _base_spacing(self):
        return self._format.get("spacing")

    def _doc_for(self, index):
        doc = self._docs.get(index)
        if doc is None:
            doc = txt_to_doc(self._slides[index].get("text", ""))
            if self._format.get("spacing") is not None:
                apply_spacing_to_doc(doc, self._format["spacing"])
            self._docs[index] = doc
        return doc

    def _store_active(self):
        if self._slides and 0 <= self._active < len(self._slides):
            self._slides[self._active]["text"] = doc_to_txt(
                self._edit.document(), base_spacing=self._base_spacing())

    # ─── cards ──────────────────────────────────────────────────────

    def _rebuild_cards(self):
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        for i, slide in enumerate(self._slides):
            card = SlideCard(i, slide.get("section"))
            card.activated.connect(self._activate)
            card.section_changed.connect(self._on_section_changed)
            card.delete_requested.connect(self._delete_slide)
            card.move_requested.connect(self._move_slide)
            card.add_after_requested.connect(
                lambda idx: self._add_slide(idx + 1))
            if i != self._active:
                card.set_static_html(
                    inline_markup_to_html(slide.get("text", "")))
            self._cards_layout.insertWidget(len(self._cards), card)
            self._cards.append(card)
        self._refresh_card_states()

    def _refresh_card_states(self):
        for i, card in enumerate(self._cards):
            card.set_index(i)
            card.set_active(i == self._active)
            if i != self._active and i < len(self._slides):
                card.set_static_html(
                    inline_markup_to_html(self._slides[i].get("text", "")))

    def _activate(self, index):
        if not (0 <= index < len(self._slides)):
            return
        if index != self._active:
            self._store_active()
        prev = self._active if 0 <= self._active < len(self._cards) else None
        self._active = index
        if prev is not None and prev != index and prev < len(self._cards):
            old = self._cards[prev]
            old.release_editor()
            if prev < len(self._slides):
                old.set_static_html(
                    inline_markup_to_html(self._slides[prev].get("text", "")))
        card = self._cards[index]
        self._edit.blockSignals(True)
        self._edit.setDocument(self._doc_for(index))
        self._edit.blockSignals(False)
        card.host_editor(self._edit)
        self._refresh_card_states()
        self._ribbon.refresh_state()

    # ─── structural ops ─────────────────────────────────────────────

    def _renumber_docs(self, start, delta):
        new = {}
        for k, doc in self._docs.items():
            if delta > 0 and k >= start:
                new[k + 1] = doc
            elif delta < 0 and k > start:
                new[k - 1] = doc
            elif delta < 0 and k == start:
                continue
            else:
                new[k] = doc
        self._docs = new

    def _add_slide(self, index):
        self._store_active()
        index = max(0, min(index, len(self._slides)))
        section = (self._slides[index - 1].get("section")
                   if 0 <= index - 1 < len(self._slides) else None)
        self._slides.insert(index, {"section": section, "text": ""})
        self._renumber_docs(index, +1)
        self._dirty = True
        self._rebuild_cards()
        self._activate(index)
        self._schedule_preview()

    def _on_add_last(self):
        self._add_slide(len(self._slides))

    def _confirm(self, text):
        return QMessageBox.question(self, "Lite Designer", text) == \
            QMessageBox.StandardButton.Yes

    def _delete_slide(self, index):
        if len(self._slides) <= 1:
            self._slides[0]["text"] = ""
            self._docs.pop(0, None)
            self._rebuild_cards()
            self._activate(0)
            self._dirty = True
            self._schedule_preview()
            return
        if (self._slides[index].get("text", "").strip()
                and not self._confirm("Delete this slide?")):
            return
        self._store_active()
        del self._slides[index]
        self._renumber_docs(index, -1)
        if self._active >= len(self._slides):
            self._active = len(self._slides) - 1
        elif self._active > index:
            self._active -= 1
        self._dirty = True
        self._rebuild_cards()
        self._activate(self._active)
        self._schedule_preview()

    def _move_slide(self, index, delta):
        j = index + delta
        if not (0 <= index < len(self._slides) and 0 <= j < len(self._slides)):
            return
        self._store_active()
        self._slides[index], self._slides[j] = \
            self._slides[j], self._slides[index]
        di = self._docs.pop(index, None)
        dj = self._docs.pop(j, None)
        if di is not None:
            self._docs[j] = di
        if dj is not None:
            self._docs[index] = dj
        if self._active == index:
            self._active = j
        elif self._active == j:
            self._active = index
        self._dirty = True
        self._rebuild_cards()
        self._activate(self._active)
        self._schedule_preview()

    def _on_section_changed(self, index, section):
        if 0 <= index < len(self._slides):
            self._slides[index]["section"] = section or None
            self._cards[index].set_section(section)
            self._dirty = True
            self._schedule_preview()

    def _on_title_finished(self):
        text = self._title_field.text().strip()
        if text != self._title:
            self._title = text
            self._dirty = True
            if self._stack.currentIndex() == 0:
                self._badge.setText(self._title or "(untitled)")
            self._schedule_preview()

    # ─── editing events ─────────────────────────────────────────────

    def _on_content_edited(self):
        self._dirty = True
        self._schedule_preview()

    def _on_deck_format_patch(self, patch):
        self._format.update(patch)
        self._ribbon.set_deck_spacing(self._format.get("spacing"))
        for doc in self._docs.values():
            if self._format.get("spacing") is not None:
                apply_spacing_to_doc(doc, self._format["spacing"])
        self._dirty = True
        self._schedule_preview()

    def _on_editor_text(self):
        if self._splitting:
            return
        self._dirty = True
        self._maybe_split()
        self._schedule_preview()

    def _maybe_split(self):
        """Double-Enter (two consecutive empty blocks) splits the slide."""
        if self._splitting:
            return
        doc = self._edit.document()
        count = doc.blockCount()
        at = -1
        for i in range(count - 1):
            a = doc.findBlockByNumber(i)
            b = doc.findBlockByNumber(i + 1)
            if (a.text() == "" and b.text() == ""
                    and not self._block_tagged(a) and not self._block_tagged(b)):
                at = i
                break
        if at < 0:
            return
        self._splitting = True
        try:
            self._store_active()
            # Clone blocks after the break into a fresh document.
            from PyQt6.QtGui import QTextDocument, QTextCursor
            new_doc = QTextDocument()
            new_cursor = QTextCursor(new_doc)
            first_new = True
            for i in range(at + 2, count):
                src = doc.findBlockByNumber(i)
                if not first_new:
                    new_cursor.insertBlock(src.blockFormat())
                else:
                    new_cursor.setBlockFormat(src.blockFormat())
                    first_new = False
                it = src.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        # Qt stores block breaks as U+2029 — drop them.
                        text = frag.text().replace(" ", "")
                        if text:
                            new_cursor.insertText(text, frag.charFormat())
                    it += 1
            # Remove the break + moved content from the source doc.
            cursor = QTextCursor(doc)
            cursor.setPosition(doc.findBlockByNumber(at).position())
            last = doc.lastBlock()
            cursor.setPosition(last.position() + last.length() - 1,
                               QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            if self._format.get("spacing") is not None:
                apply_spacing_to_doc(new_doc, self._format["spacing"])
            self._slides[self._active]["text"] = doc_to_txt(
                doc, base_spacing=self._base_spacing())
            section = self._slides[self._active].get("section")
            self._slides.insert(self._active + 1,
                                {"section": section, "text": ""})
            self._renumber_docs(self._active + 1, +1)
            self._docs[self._active + 1] = new_doc
            self._dirty = True
            self._rebuild_cards()
            self._activate(self._active + 1)
            self._edit.moveCursor(QTextCursor.MoveOperation.Start)
        finally:
            self._splitting = False
        self._schedule_preview()

    @staticmethod
    def _block_tagged(block):
        from ui.widgets.lite_designer.rich_txt import HR_BLOCK_PROP, GAP_BLOCK_PROP
        bfmt = block.blockFormat()
        return (bfmt.hasProperty(HR_BLOCK_PROP)
                or bfmt.hasProperty(GAP_BLOCK_PROP))

    # ─── preview ────────────────────────────────────────────────────

    def _schedule_preview(self):
        if self._deck_id is not None and self._stack.currentIndex() == 0:
            self._preview_timer.start()

    def _refresh_preview(self):
        if self._deck_id is None:
            return
        slides = [dict(s) for s in self._slides]
        if 0 <= self._active < len(slides):
            slides[self._active]["text"] = doc_to_txt(
                self._edit.document(), base_spacing=self._base_spacing())
        raw = deck_to_txt(self._title, slides, self._format or None)
        parsed = parse_slide_txt(raw)
        if not (0 <= self._active < len(parsed["slides"])):
            return
        slide = parsed["slides"][self._active]
        ref = (f"{parsed['title'] or '(untitled)'} · {slide['section']}"
               if slide.get("section") else (parsed["title"] or "(untitled)"))
        payload = {
            "action": "display",
            "text": slide.get("text", ""),
            "ref": ref,
            "reference": ref,
            "translation": "",
            "book": "",
            "chapter": "",
            "verse": "",
            "content": "slide",
            "theme": self._theme_name,
            "theme_data": core.theme_loader.get_theme(self._theme_name),
            "slide_format": parsed.get("format"),
        }
        self._preview.display_verse(payload)

    # ─── save / reset / close ───────────────────────────────────────

    def _flash(self, text):
        self._status.setText(text)
        QTimer.singleShot(2500, lambda: self._status.setText(""))

    def _save_freeform(self):
        if self._deck_id is None:
            return
        from core.slide_service import update_deck
        self._store_active()
        raw = deck_to_txt(self._title, self._slides, self._format or None)
        if not parse_slide_txt(raw)["slides"]:
            QMessageBox.warning(self, "Lite Designer",
                                "Nothing to save — the deck has no slides.")
            return
        update_deck(self._deck_id, raw_text=raw)
        self._dirty = False
        self._flash("Saved to preview")
        self.deck_saved.emit(self._deck_id)

    def _on_save(self):
        if self._stack.currentIndex() == 0:
            self._save_freeform()
        else:
            self._save_theme()

    def _on_reset(self):
        if self._stack.currentIndex() == 0:
            if self._deck_id is not None:
                self._load_deck()
        else:
            fresh = core.theme_loader.get_theme(self._theme_name)
            if fresh is not None:
                self._original_theme = copy.deepcopy(fresh)
                self._working_theme = copy.deepcopy(fresh)
                self._theme_dirty = False
                self._props.load_theme(self._working_theme)
                self._theme_preview.apply_theme(self._working_theme)

    def _on_close(self):
        if (self._dirty or self._theme_dirty) and not self._confirm(
                "Discard unsaved changes?"):
            return
        self.close()

    # ─── theme tab (quick-editor behavior) ──────────────────────────

    def _load_theme(self):
        theme_data = core.theme_loader.get_theme(self._theme_name)
        self._original_theme = copy.deepcopy(theme_data) if theme_data else {}
        self._working_theme = copy.deepcopy(self._original_theme)
        self._theme_dirty = False
        self._props.load_theme(self._working_theme)
        self._theme_preview.apply_theme(self._working_theme)

    def _on_theme_changed(self, theme_dict):
        self._working_theme = theme_dict
        self._theme_dirty = True
        self._theme_preview.apply_theme(theme_dict)

    def _save_theme(self):
        core.theme_loader.save_theme(self._theme_name, self._working_theme)
        self._original_theme = copy.deepcopy(self._working_theme)
        self._theme_dirty = False
        self._flash("Theme saved")
        self.theme_saved.emit(self._theme_name)
