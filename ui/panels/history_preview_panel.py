"""
ui/panels/history_preview_panel.py

Right column of the History tab: one display screen (no label) plus a strip
below it listing context for the selected history item.

  Verse selected  → strip like the bible panel: that verse plus N verses
                    before/after it (N = history.context_verses setting),
                    main verse highlighted.
  Search selected → strip like search results: the stored top refs.
  Deck selected   → strip like the SLIDES tab: the deck's slides.

Plain click shows the row on the screen; Ctrl+click navigates to that verse
in the SCRIPTURE tab (History-tab-only gesture). Double-click never sends
anything live — history is read-only. Slide editing is disabled here.
"""

import logging
import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QFrame, QStackedWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    SLATE_950, SLATE_800, SLATE_500, SLATE_400, SLATE_300,
    WHITE, BLUE_500,
)
from ui.panels.slide_grid_panel import SlideGridPanel

logger = logging.getLogger(__name__)

_REF_RE = re.compile(r"^(?:\[([^\]]+)\]\s*)?(.+?)\s+(\d+)\s*:\s*(\d+)\s*$")
_ROW_ROLE = Qt.ItemDataRole.UserRole


def parse_ref(ref: str):
    """Split '[Trans] Book C:V' (or 'Book C:V') → (bracket, book, chapter, verse)."""
    m = _REF_RE.match((ref or "").strip())
    if not m:
        return None, None, None, None
    return m.group(1), m.group(2), m.group(3), m.group(4)


def resolve_translation(display_name: str) -> str:
    """Display name ('KJV') → canonical code for bible queries."""
    try:
        from core.bible_service import get_all_display_names
        inverted = {v: k for k, v in get_all_display_names().items()}
        if display_name in inverted:
            return inverted[display_name]
    except Exception:
        pass
    return (display_name or "KJV").upper()


def fetch_verse(display_translation: str, book: str, chapter, verse):
    """Tolerant verse fetch: exact book match, then prefix match, then KJV.

    Returns (row, canonical_code); row always carries book/chapter/verse/text
    (get_verse omits book, so it is attached here from the matched name).
    """
    from core.bible_service import get_verse, get_books
    try:
        chapter, verse = int(chapter), int(verse)
    except (TypeError, ValueError):
        return None, display_translation
    canon = resolve_translation(display_translation)
    for code in ([canon] if canon == "KJV" else [canon, "KJV"]):
        try:
            row = get_verse(code, book, chapter, verse)
            if row:
                row["book"] = book
                return row, code
            for b in get_books(code):
                if b.lower().startswith(book.lower()):
                    row = get_verse(code, b, chapter, verse)
                    if row:
                        row["book"] = b
                        return row, code
                    break
        except Exception:
            continue
    return None, canon


def default_translation() -> str:
    try:
        from core.database import get_setting
        return get_setting("bible.last_translation", "AMP")
    except Exception:
        return "AMP"


def context_count() -> int:
    try:
        from core.database import get_setting
        return max(0, min(10, int(get_setting("history.context_verses", "3"))))
    except (TypeError, ValueError):
        return 3


class _SixteenNineBox(QWidget):
    """Full width, exactly 16:9 tall — the screen never stretches or bands."""

    def __init__(self, child: QWidget, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QSizePolicy
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setFixedHeight(max(1, int(self.width() * 9 / 16)))


class _StripRow(QFrame):
    """One strip row: bold title + grey body, highlightable."""

    def __init__(self, title: str, body: str = "", highlighted: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {'rgba(59, 130, 246, 0.18)' if highlighted else SLATE_800}; "
            f"border: 1px solid {BLUE_500 if highlighted else 'transparent'}; "
            f"border-radius: 8px; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color: {WHITE}; font-size: 12px; font-weight: 700; background: transparent;")
        layout.addWidget(title_label)
        if body:
            body_label = QLabel(body)
            body_label.setWordWrap(True)
            body_label.setStyleSheet(
                f"color: {SLATE_400}; font-size: 11px; background: transparent;")
            layout.addWidget(body_label)


class HistoryPreviewPanel(QWidget):
    """History right column: screen + context strip."""

    navigate_verse_requested = pyqtSignal(str, str, str, str)  # book, chapter, verse, translation

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")
        self._screen = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 0, 0, 0)
        root.setSpacing(6)

        self._screen_wrap = QWidget()
        screen_layout = QVBoxLayout(self._screen_wrap)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._screen_wrap, 0)

        self._strip_stack = QStackedWidget()
        root.addWidget(self._strip_stack, 1)

        # Verse/search strip (custom rows)
        self._list_strip = QListWidget()
        self._list_strip.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: transparent; border: none; }")
        self._list_strip.setSpacing(4)
        self._list_strip.setVerticalScrollMode(
            self._list_strip.ScrollMode.ScrollPerPixel)
        self._list_strip.itemClicked.connect(self._on_strip_clicked)
        self._strip_stack.addWidget(self._list_strip)

        # Deck strip (reuses the chunked SLIDES strip; editing off, no live)
        self._slide_grid = SlideGridPanel("")
        self._slide_grid.edit_menu_enabled = False
        self._slide_grid.slide_clicked.connect(self._on_slide_clicked)
        self._strip_stack.addWidget(self._slide_grid)

        self._rows: list[dict] = []  # parallel to _list_strip rows
        self._slide_state: dict | None = None
        self.clear()

    # ── Screen ──────────────────────────────────────────────────────────

    def _ensure_screen(self):
        if self._screen is None:
            from ui.widgets.display_view import DisplayView
            self._screen = DisplayView(live_mode=False)
            # Exact 16:9 like the operator Preview/Live screens — the box
            # takes full column width and sizes its own height, so the strip
            # below gets all remaining space instead of black bands.
            self._screen_wrap.layout().addWidget(_SixteenNineBox(self._screen))
        return self._screen

    @staticmethod
    def _verse_payload(ref: str, text: str, translation: str, theme_name: str) -> dict:
        from core.theme_loader import get_theme
        return {"action": "display", "text": text, "ref": ref, "reference": ref,
                "translation": translation or "", "book": "", "chapter": "",
                "verse": "", "content": "verse", "theme": theme_name,
                "theme_data": get_theme(theme_name)}

    @staticmethod
    def _slide_payload(text: str, ref: str, theme_name: str, fmt) -> dict:
        from core.theme_loader import get_theme
        payload = {"action": "display", "text": text, "ref": "", "reference": "",
                   "translation": "", "book": "", "chapter": "", "verse": "",
                   "content": "slide", "theme": theme_name,
                   "theme_data": get_theme(theme_name)}
        if fmt:
            payload["slide_format"] = fmt
        return payload

    def _output_theme(self) -> str:
        try:
            from core.database import get_setting
            return get_setting("display.output_1_theme", "default")
        except Exception:
            return "default"

    def clear(self):
        if self._screen is not None:
            self._screen.clear()
        self._list_strip.clear()
        self._rows = []
        self._slide_state = None
        self._strip_stack.setCurrentWidget(self._list_strip)

    # ── Show entry points (called by the History tab) ───────────────────

    def show_verse(self, ref: str, text: str, translation: str, theme_name: str | None = None):
        """Render a logged verse push + its chapter context strip."""
        screen = self._ensure_screen()
        screen.display_verse(self._verse_payload(
            ref, text, translation, theme_name or self._output_theme()))
        _bracket, book, chapter, verse = parse_ref(ref)
        if book is None:
            self._show_strip_rows([{"title": ref, "body": text, "main": True,
                                    "ref": ref, "translation": translation}])
            return
        canon = resolve_translation(translation)
        anchor, _ = fetch_verse(canon, book, chapter, verse)
        n = context_count()
        rows = []
        if anchor is None:
            rows.append({"title": ref, "body": text, "main": True,
                         "ref": ref, "translation": translation})
        else:
            from core.bible_service import get_next_verse, get_prev_verse
            before, node = [], {"book": anchor["book"], "chapter": anchor["chapter"],
                                "verse": anchor["verse"], "text": anchor["text"]}
            for _ in range(n):
                prev = get_prev_verse(
                    canon, node["book"], node["chapter"], node["verse"])
                if prev is None:
                    break
                before.append(prev)
                node = prev
            after, node = [], {"book": anchor["book"], "chapter": anchor["chapter"],
                               "verse": anchor["verse"], "text": anchor["text"]}
            for _ in range(n):
                nxt = get_next_verse(
                    canon, node["book"], node["chapter"], node["verse"])
                if nxt is None:
                    break
                after.append(nxt)
                node = nxt
            for v in reversed(before):
                rows.append(self._verse_row(v, canon, main=False))
            rows.append(self._verse_row(anchor, canon, main=True))
            for v in after:
                rows.append(self._verse_row(v, canon, main=False))
        self._show_strip_rows(rows)

    @staticmethod
    def _verse_row(v: dict, translation: str, main: bool) -> dict:
        ref = f"{v.get('book', '')} {v.get('chapter', '')}:{v.get('verse', '')}"
        text = v.get("text", "")
        return {"title": ref, "body": (text[:120] + "…") if len(text) > 120 else text,
                "main": main, "ref": ref, "translation": translation,
                "full_text": text}

    def show_search(self, query: str, top_refs: list, chosen: str | None):
        """Render stored top refs like search results; screen shows chosen/first."""
        translation = default_translation()
        rows = []
        screen_shown = False
        for ref in (top_refs or [])[:5]:
            _bracket, book, chapter, verse = parse_ref(ref)
            body, full, canon = "", "", translation
            if book is not None:
                row, canon = fetch_verse(translation, book, chapter, verse)
                if row:
                    full = row.get("text", "")
                    body = (full[:120] + "…") if len(full) > 120 else full
            is_chosen = chosen is not None and ref == chosen
            rows.append({"title": ("→ " if is_chosen else "") + ref, "body": body,
                         "main": is_chosen, "ref": ref, "translation": canon,
                         "full_text": full})
            if not screen_shown and (is_chosen or (chosen is None and not rows[:-1])):
                if full:
                    self._ensure_screen().display_verse(self._verse_payload(
                        ref, full, canon, self._output_theme()))
                    screen_shown = True
        if not screen_shown:
            self._ensure_screen().clear()
        self._show_strip_rows(rows)

    def show_slide(self, deck_id, ref: str, text: str, theme_name: str | None):
        """Render a logged slide push + its deck strip (matched slide highlighted)."""
        from core.slide_service import get_deck
        deck = get_deck(deck_id) if deck_id is not None else None
        fmt = (deck or {}).get("format")
        self._ensure_screen().display_verse(self._slide_payload(
            text, ref, theme_name or "slides", fmt))
        if deck and deck.get("slides"):
            slides = deck["slides"]
            section = ref.rsplit(" · ", 1)[-1] if " · " in (ref or "") else None
            match = 0
            for i, s in enumerate(slides):
                if (s.get("text", "").strip() == (text or "").strip()
                        and (section is None or s.get("section") == section)):
                    match = i
                    break
            self._slide_grid.set_title(deck.get("title") or "(untitled)")
            self._slide_grid.set_deck(deck, select_index=match)
            self._slide_state = {"deck": deck, "theme": theme_name or "slides"}
        else:
            pseudo = {"id": None, "title": ref or "(untitled)",
                      "slides": [{"section": None, "text": text or ""}]}
            self._slide_grid.set_title(ref or "(untitled)")
            self._slide_grid.set_deck(pseudo, select_index=0)
            self._slide_state = {"deck": pseudo, "theme": theme_name or "slides"}
        self._strip_stack.setCurrentWidget(self._slide_grid)

    def show_clear(self):
        self._ensure_screen().clear()
        self._show_strip_rows([])

    # ── Strip mechanics ─────────────────────────────────────────────────

    def _show_strip_rows(self, rows: list[dict]):
        from PyQt6.QtWidgets import QListWidgetItem
        self._strip_stack.setCurrentWidget(self._list_strip)
        self._list_strip.clear()
        self._rows = rows
        for row in rows:
            item = QListWidgetItem()
            widget = _StripRow(row["title"], row.get("body", ""),
                               highlighted=row.get("main", False))
            item.setSizeHint(widget.sizeHint())
            self._list_strip.addItem(item)
            self._list_strip.setItemWidget(item, widget)
        for i, row in enumerate(rows):
            if row.get("main"):
                self._list_strip.setCurrentRow(i)
                break

    def _on_strip_clicked(self, item):
        from PyQt6.QtWidgets import QApplication
        row = self._list_strip.row(item)
        if not (0 <= row < len(self._rows)):
            return
        data = self._rows[row]
        if (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
                and data.get("ref")):
            _bracket, book, chapter, verse = parse_ref(data["ref"])
            if book is not None:
                self.navigate_verse_requested.emit(
                    book, str(chapter), str(verse),
                    data.get("translation") or default_translation())
            return
        full = data.get("full_text", "")
        if full:
            self._ensure_screen().display_verse(self._verse_payload(
                data.get("ref", ""), full,
                data.get("translation") or default_translation(),
                self._output_theme()))

    def _on_slide_clicked(self, index: int):
        state = getattr(self, "_slide_state", None)
        if not state:
            return
        deck = state["deck"]
        slides = deck.get("slides", [])
        if not (0 <= index < len(slides)):
            return
        slide = slides[index]
        title = deck.get("title") or "(untitled)"
        ref = f"{title} · {slide.get('section')}" if slide.get("section") else title
        self._ensure_screen().display_verse(self._slide_payload(
            slide.get("text", ""), ref, state["theme"], deck.get("format")))
