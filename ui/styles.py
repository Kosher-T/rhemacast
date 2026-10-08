"""
ui/styles.py

Central QSS stylesheet for the RhemaCast operator UI.

All color values resolve from ui.app_theme (the single source of truth).
The SLATE_*/BLUE_*/CYAN_* names are legacy aliases kept so existing
importers keep working — new code must use the semantic names (ACCENT_*,
SELECTION_*, BG_*) which track the active app theme's roles.
"""

from ui.app_theme import color as _theme_color

# ─── Semantic tokens (track the active app theme) ──────────────────────────
BG_APP = _theme_color("bg_app")
BG_PANEL = _theme_color("bg_panel")
BG_RAISED = _theme_color("bg_raised")
BG_INPUT = _theme_color("bg_input")
BG_HOVER = _theme_color("bg_hover")

TEXT_PRIMARY = _theme_color("text_primary")
TEXT_MUTED = _theme_color("text_muted")
TEXT_FAINT = _theme_color("text_faint")
TEXT_SELECTED = _theme_color("text_selected")

ACCENT = _theme_color("accent")
ACCENT_HOVER = _theme_color("accent_hover")
ACCENT_LIGHT = _theme_color("accent_light")
ACCENT_SOFT = _theme_color("accent_soft")
ACCENT_BORDER = _theme_color("accent_border")

SELECTION_BG = _theme_color("selection_bg")
SELECTION_BORDER = _theme_color("selection_border")
SELECTION_TEXT = _theme_color("selection_text")
# Text highlight inside inputs/editors — deliberately NOT SELECTION_BG:
# a row wash tuned to keep grey text readable is invisible as a caret
# highlight on a dark card.
TEXT_SELECTION = _theme_color("text_selection")

FOCUS_RING = _theme_color("focus_ring")
MENU_BG = _theme_color("menu_bg")
CHROME_SOFT = _theme_color("chrome_soft")
CHROME_STRONG = _theme_color("chrome_strong")
TOOLBAR_BG = _theme_color("toolbar_bg")

# ─── Colour Tokens (legacy aliases — do not extend; use roles above) ───────
SLATE_950 = BG_APP
SLATE_900 = "#131316"
SLATE_800 = BG_RAISED
SLATE_700 = "#2e2e36"
SLATE_600 = "#52525b"
SLATE_500 = TEXT_FAINT
SLATE_400 = TEXT_MUTED
SLATE_300 = "#d4d4d8"
SLATE_100 = "#f4f4f5"
WHITE = TEXT_PRIMARY

CHROME_BG = _theme_color("chrome_bg")
CHROME_TAB_ACTIVE = _theme_color("chrome_tab_active")

BLUE_400 = "#c084fc"          # legacy alias: links follow the accent family
BLUE_500 = ACCENT             # legacy alias: was focus/selection blue
CYAN_400 = ACCENT             # legacy alias: was brand cyan
AMBER_500 = _theme_color("warning")
AMBER_900 = _theme_color("warning_text")
EMERALD_400 = "#34d399"
EMERALD_500 = _theme_color("success")
RED_500 = _theme_color("error")
RED_600 = "#dc2626"

BORDER_SUBTLE = _theme_color("border_subtle")
BORDER_LIGHT = _theme_color("border_light")
PANEL_BG = BG_PANEL


# ─── Main Application Stylesheet ─────────────────────────────────────────────
APP_STYLESHEET = f"""
/* ── Global Reset ── */
QWidget {{
    background-color: {SLATE_950};
    color: {WHITE};
    font-family: 'Nunito', 'Segoe UI', sans-serif;
    font-size: 10px;
    border: none;
}}

/* ── Splitter Handles (Resizers) ── */
QSplitter::handle:horizontal {{
    width: 6px;
    background: {ACCENT_SOFT};
}}
QSplitter::handle:horizontal:hover {{
    background: {ACCENT_BORDER};
}}
QSplitter::handle:vertical {{
    height: 6px;
    background: {ACCENT_SOFT};
}}
QSplitter::handle:vertical:hover {{
    background: {ACCENT_BORDER};
}}

/* ── Scroll Bars (Thin, dark) ── */
QScrollBar:vertical {{
    width: 5px;
    background: transparent;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 25);
    border-radius: 2px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255, 255, 255, 50);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
    background: transparent;
}}
QScrollBar:horizontal {{
    height: 5px;
    background: transparent;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: rgba(255, 255, 255, 25);
    border-radius: 2px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0px;
    background: transparent;
}}

/* ── Push Buttons ── */
QPushButton {{
    background-color: {SLATE_700};
    color: {WHITE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 10px;
}}
QPushButton:hover {{
    background-color: {SLATE_600};
}}
QPushButton:pressed {{
    background-color: {SLATE_800};
}}
QPushButton:focus {{
    border: 2px solid {BLUE_500};
    padding: 2px 9px;  /* compensate for border width */
}}
QPushButton:disabled {{
    color: {SLATE_500};
    background-color: {SLATE_800};
    border-color: transparent;
}}

/* ── Line Edit ── */
QLineEdit {{
    background: rgba(0, 0, 0, 100);
    color: {WHITE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
    padding: 3px 7px;
    font-size: 10px;
    selection-background-color: {TEXT_SELECTION};
}}
QLineEdit:focus {{
    border: 2px solid {BLUE_500};
    padding: 2px 6px;  /* compensate for border */
}}

/* ── List Widget ── */
QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    background: transparent;
    padding: 0;
    border: none;
}}
QListWidget::item:selected {{
    background: transparent;
}}
QListWidget::item:hover {{
    background: transparent;
}}
QListWidget::item:focus {{
    outline: 2px solid {BLUE_500};
    outline-offset: -2px;
}}
QListWidget::item:selected:focus {{
    outline: 2px solid {BLUE_500};
    outline-offset: -2px;
}}

/* ── Labels ── */
QLabel {{
    background: transparent;
    border: none;
}}

/* ── Tool Tips ── */
QToolTip {{
    background-color: {SLATE_800};
    color: {WHITE};
    border: 1px solid {BORDER_LIGHT};
    padding: 5px 8px;
    font-size: 10px;
    border-radius: 6px;
}}
"""

# ─── Panel Header Style ──────────────────────────────────────────────────────
PANEL_HEADER_STYLE = f"""
    QWidget {{
        background-color: rgba(29, 29, 34, 130);
        border-bottom: 1px solid rgba(255, 255, 255, 12);
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
"""

PANEL_HEADER_LABEL_STYLE = f"""
    color: {SLATE_400};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    background: transparent;
"""

# ─── Panel Body Style ────────────────────────────────────────────────────────
# NB: panels are QWidget *subclasses*, so Qt ignores QSS background/border
# here unless WA_StyledBackground is set — this rule mostly documents
# intent. The visible focus ring is a painted overlay (ui/focus_ring.py),
# not a border on the panel.
PANEL_BODY_STYLE = f"""
    QWidget.MainPanel {{
        background-color: {BG_PANEL};
        border: 1px solid rgba(255, 255, 255, 12);
        border-radius: 8px;
    }}
"""

# ─── Queue Item Styles ───────────────────────────────────────────────────────
QUEUE_ITEM_STYLE = f"""
    QFrame#QueueItem {{
        background: {ACCENT_SOFT};
        border: 1px solid {ACCENT_BORDER};
        border-radius: 4px;
        padding: 8px;
    }}
    QFrame#QueueItem:hover {{
        border-color: {ACCENT};
    }}
"""

# ─── Macro Button Styles ─────────────────────────────────────────────────────
MACRO_BTN_AMBER = f"""
    QPushButton {{
        background-color: rgba(245, 158, 11, 0.9);
        color: {AMBER_900};
        border: none;
        border-radius: 6px;
        font-weight: 800;
        font-size: 12px;
        padding: 4px 10px;
    }}
    QPushButton:hover {{
        background-color: rgba(251, 191, 36, 0.95);
    }}
    QPushButton:pressed {{
        background-color: rgba(217, 119, 6, 0.9);
    }}
"""

MACRO_BTN_CLEAR = f"""
    QPushButton {{
        background-color: rgba(46, 46, 54, 0.9);
        color: {WHITE};
        border: none;
        border-radius: 6px;
        font-weight: 700;
        font-size: 11px;
        padding: 4px 10px;
    }}
    QPushButton:hover {{
        background-color: rgba(62, 62, 72, 0.9);
    }}
    QPushButton:pressed {{
        background-color: rgba(20, 20, 23, 0.9);
    }}
    QPushButton[cloaked="true"] {{
        border: 1px solid rgba(251, 146, 60, 0.8);
        background-color: rgba(251, 146, 60, 0.2);
    }}
"""

# ─── Verse Row Styles ────────────────────────────────────────────────────────
VERSE_EVEN_BG = "rgba(255, 255, 255, 6)"  # Subtle even rows
VERSE_ODD_BG = "rgba(0, 0, 0, 0.35)"        # Dark grey for odd rows (more contrast)
VERSE_SELECTED_BG = SELECTION_BG
VERSE_HOVER_BG = ACCENT_SOFT
VERSE_SELECTED_TEXT = SELECTION_TEXT

# Bible panel verse font sizes (user-configurable via Settings → Display)
VERSE_TEXT_SIZE = 12   # verse text (was 10)
VERSE_REF_SIZE = 11    # reference text (was 9)

# ─── Translation Bar Button ──────────────────────────────────────────────────
TRANSLATION_BTN_INACTIVE = f"""
    QPushButton {{
        background: transparent;
        color: {SLATE_500};
        font-size: 10px;
        font-weight: 700;
        border: none;
        border-right: 1px solid {BORDER_SUBTLE};
        padding: 4px 8px;
    }}
    QPushButton:hover {{
        color: {SLATE_300};
    }}
"""

TRANSLATION_BTN_ACTIVE = f"""
    QPushButton {{
        background-color: {ACCENT};
        color: {TEXT_PRIMARY};
        font-size: 10px;
        font-weight: 700;
        border: none;
        padding: 4px 8px;
    }}
"""

# ─── Show / Reject Buttons ───────────────────────────────────────────────────
SHOW_BTN_STYLE = f"""
    QPushButton {{
        background-color: rgba(16, 185, 129, 0.2);
        color: {EMERALD_400};
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 4px;
        padding: 3px 10px;
        font-size: 10px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background-color: rgba(62, 62, 72, 0.9);
    }}
"""

REJECT_BTN_STYLE = f"""
    QPushButton {{
        background-color: rgba(239, 68, 68, 0.15);
        color: {RED_500};
        border: 1px solid rgba(239, 68, 68, 0.2);
        border-radius: 4px;
        padding: 3px 10px;
        font-size: 10px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background-color: rgba(239, 68, 68, 0.3);
    }}
"""

# ── Minimal scrollbar (lite-designer spec) ──
MINIMAL_SCROLLBAR_CSS = """
    QScrollBar:vertical {
        background: transparent; width: 6px; margin: 0px; border: none;
    }
    QScrollBar::handle:vertical {
        background: rgba(161, 161, 170, 0.35); min-height: 20px;
        border: none; border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(161, 161, 170, 0.6);
    }
    QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
        height: 0px; border: none; background: none;
    }
    QScrollBar::sub-page:vertical, QScrollBar::add-page:vertical {
        background: none; border: none;
    }
"""


def apply_minimal_scrollbar(view):
    """Give any scroll area / item view the lite-designer scrollbar:
    permanently reserved 6px lane (never pops in and shoves content),
    flat 2D thumb, no arrows. Appends to the widget's own stylesheet."""
    from PyQt6.QtCore import Qt
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    existing = view.styleSheet() or ""
    if "QScrollBar:vertical" not in existing:
        view.setStyleSheet(existing + MINIMAL_SCROLLBAR_CSS)
