"""
ui/widgets/theme_preview.py

Reusable theme preview widget — identical pattern to LivePreviewPanel viewports.
QFrame (black bg, border) → DisplayView, wrapped in AspectRatioWidget (16:9).
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, pyqtSignal

from ui.widgets.display_view import DisplayView
from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.styles import TEXT_MUTED

SAMPLE_VERSES = {
    "shortest": {
        "text": "Jesus wept.",
        "reference": "JOHN 11:35",
        "translation": "KJV",
        "book": "John", "chapter": "11", "verse": "35",
    },
    "longest": {
        "text": (
            'So the king called Haman the son of Hammedatha the Agagite, the Jew, and said: '
            '"The law has given Esther the house of Haman, and they have hanged him on the gallows, '
            'because he sought to lay a hand on the Jews. You yourself may write concerning the Jews, '
            'as you please, in the king\'s name, and seal it with the king\'s signet ring; for whatever '
            'is written in the king\'s name and sealed with the king\'s signet ring no one can revoke."'
        ),
        "reference": "ESTHER 8:9",
        "translation": "KJV",
        "book": "Esther", "chapter": "8", "verse": "9",
    },
    "medium": {
        "text": (
            "I indeed baptize you with water unto repentance: but he that cometh after me "
            "is mightier than I, whose shoes I am not worthy to bear: he shall baptize you "
            "with the Holy Ghost, and with fire:"
        ),
        "reference": "MATTHEW 3:11",
        "translation": "KJV",
        "book": "Matthew", "chapter": "3", "verse": "11",
    },
    "popup": {
        "text": "Enter his gates with thanksgiving, and into his courts with praise.",
        "reference": "PSALM 100:4",
        "translation": "KJV",
        "book": "Psalms", "chapter": "100", "verse": "4",
    },
    "freeform": {
        "text": "Sunday morning, we gather in Your presence.\n"
                "Every heart is open; every voice is raised.",
        "title": "Sunday Morning",
        "reference": "",
        "translation": "",
        "book": "", "chapter": "", "verse": "",
    },
}


class ThemePreview(QWidget):
    """A 16:9 theme preview — identical viewport to LivePreviewPanel.

    Structure: QFrame (black bg) → DisplayView, wrapped in AspectRatioWidget.
    Header label sits above the viewport.

    Signals:
        clicked() — when the preview viewport is clicked
    """

    clicked = pyqtSignal()

    def __init__(self, verse_key: str = "popup", label: str = "",
                 min_width: int = 320, max_width: int = 840, parent=None):
        super().__init__(parent)
        self._verse_key = verse_key
        self._theme_data: dict | None = None

        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header label
        if label:
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "color: " + TEXT_MUTED + "; font-size: 12px; font-weight: 700; "
                "letter-spacing: 1px; text-transform: uppercase; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(lbl)

        # Viewport frame — same as LivePreviewPanel
        self._frame = QFrame()
        self._frame.setStyleSheet(
            "background: black;"
            "border: 1px solid rgba(255, 255, 255, 0.08);"
            "border-radius: 8px;"
        )

        self._view = DisplayView(live_mode=False)
        self._view.setMinimumHeight(1)

        frame_inner = QVBoxLayout(self._frame)
        frame_inner.setContentsMargins(0, 0, 0, 0)
        frame_inner.addWidget(self._view)

        # AspectRatioWidget wraps the frame — same as LivePreviewPanel
        self._ar = AspectRatioWidget(
            self._frame, aspect_ratio=16.0 / 9.0,
            min_width=min_width, max_width=max_width
        )
        layout.addWidget(self._ar, 1)

    def _resolved_theme(self, theme_data: dict) -> dict:
        """Resolve a raw v2 theme for display without mutating the document."""
        if not isinstance(theme_data, dict):
            return theme_data
        from core.theme_compat import looks_v2
        if not looks_v2(theme_data):
            return theme_data
        from core.theme_schema import normalize_theme
        from core.theme_loader import FREEFORM, SCRIPTURE
        kind = theme_data.get("kind")
        if kind not in (SCRIPTURE, FREEFORM):
            kind = FREEFORM if isinstance(theme_data.get("slide"), dict) else SCRIPTURE
        resolved, _report = normalize_theme(
            theme_data, kind=kind, name=theme_data.get("name"))
        return resolved

    def _payload(self, verse_key: str, theme_data: dict | None = None) -> dict:
        verse = SAMPLE_VERSES.get(verse_key, SAMPLE_VERSES["popup"])
        theme = (self._theme_data if theme_data is None
                 else theme_data)
        resolved = (self._resolved_theme(theme)
                    if theme is not None else None)
        # Designer samples are scripture verses unless the theme is
        # freeform: the pairing rule uses this label, not the theme name.
        kind = (resolved or {}).get("kind") if isinstance(resolved, dict) else None
        if kind not in ("scripture", "freeform"):
            kind = "scripture"
        return {
            "action": "display",
            "kind": kind,
            "text": verse["text"],
            "reference": verse["reference"],
            "translation": verse["translation"],
            "title": verse.get("title", ""),
            "book": verse.get("book", ""),
            "chapter": verse.get("chapter", ""),
            "verse": verse.get("verse", ""),
            "theme_data": resolved,
        }

    def apply_theme(self, theme_data: dict, *, sample_id: str | None = None):
        """Load a theme and redraw the selected sample.

        This is the normal content payload path: the renderer may play an
        entry for the first payload or a transition for a content change. The
        Designer's non-animation edits use ``apply_theme_in_place`` instead.
        """
        if sample_id is not None:
            self._verse_key = sample_id
        self._theme_data = theme_data
        self._view.display_verse(self._payload(self._verse_key))

    def apply_theme_in_place(self, theme_data: dict):
        """Restyle the current payload without running entry or exit.

        The page's ``applyTheme`` updates CSS variables and container
        geometry from the payload already on screen. Unknown document keys
        never reach this path: the caller passes a resolved display theme and
        the Designer document remains the sole owner of raw data.
        """
        self._theme_data = theme_data
        self._view.apply_theme(self._resolved_theme(theme_data))

    def show_sample(self, verse_key: str, theme_data: dict | None = None):
        """Swap the preview sample through the normal content-change path."""
        if theme_data is not None:
            self._theme_data = theme_data
        self._verse_key = verse_key
        self._view.display_verse(self._payload(verse_key))

    def replay_phase(self, phase: str):
        """Ask the page to replay one Designer animation phase."""
        alternate = "shortest" if self._verse_key != "shortest" else "medium"
        self._view.replay_preview(
            phase, self._payload(self._verse_key), self._payload(alternate))

    def animation_state(self, callback):
        """Read the page-side animation state (tests and diagnostics)."""
        self._view.preview_animation_state(callback)

    def clear(self):
        """Clear the viewport."""
        self._view.clear()

    def set_verse(self, verse_key: str):
        """Switch to a different sample verse and redraw it."""
        self._verse_key = verse_key
        if self._theme_data is not None:
            self.show_sample(verse_key)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
