"""
ui/styles.py

Central QSS stylesheet for the RhemaCast operator UI.

All color values resolve from ui.app_theme (the single source of truth).
The SLATE_*/BLUE_*/CYAN_* names are legacy aliases kept so existing
importers keep working — new code must use the semantic names (ACCENT_*,
SELECTION_*, BG_*) which track the active app theme's roles.
"""

from ui.app_theme import color as _theme_color
from ui.tokens import scrollbar_qss as _scrollbar_rule

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
ACCENT_TEXT = _theme_color("accent_text")
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

BLUE_400 = ACCENT_TEXT          # legacy alias: links follow the accent family
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
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 12px;
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

/* ── Scroll Bars (one spec, ui.tokens) ── */
{_scrollbar_rule()}

/* ── Push Buttons ── */
QPushButton {{
    background-color: {SLATE_700};
    color: {WHITE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 12px;
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
    font-size: 12px;
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
    font-size: 12px;
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

def panel_header_label_style() -> str:
    """All-caps panel header QSS — reads the "panel.labels" font group.

    Colour, case and tracking stay fixed; family/weight/size are
    settings-backed (defaults 13px / 600 — the pre-settings look).
    """
    from ui.app_theme import area_font, font_qss
    spec = area_font("panel.labels", 13, 600, size_min=8, size_max=28)
    return f"""
    color: {SLATE_400};
    {font_qss(spec)}
    text-transform: uppercase;
    letter-spacing: 0.8px;
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
        font-weight: 700;
        font-size: 13px;
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
        font-size: 12px;
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

# Bible panel verse font sizes — DEFAULTS only. The operator overrides them
# in Settings → Interface ("Bible verses" / "Bible reference"); a saved value
# is used as-is, at whatever size they picked.
VERSE_TEXT_SIZE = 13   # verse text (was 12; 10 before that)
VERSE_REF_SIZE = 12    # reference text (was 11; 9 before that)

# ─── Translation Bar Button ──────────────────────────────────────────────────
# One chip language (ui.tokens.chip_qss): the selected version wears the
# accent wash + 2px accent underline; the rest are quiet text until hover.
from ui.tokens import chip_qss as _chip_qss

TRANSLATION_BTN_INACTIVE = _chip_qss(False)
TRANSLATION_BTN_ACTIVE = _chip_qss(True)


def translation_btn_style(active: bool) -> str:
    """Translation-bar QSS — family/weight/size from the "panel.labels" group.

    Unset keeps this bar's original 12px / 700; a saved panel-label value
    applies to every translation button (the + Add button defaults 12/600).
    """
    from ui.app_theme import area_font, font_qss
    spec = area_font("panel.labels", 12, 700, size_min=8, size_max=28)
    return _chip_qss(active, font_css=font_qss(spec))

# ─── Show / Reject Buttons ───────────────────────────────────────────────────
SHOW_BTN_STYLE = f"""
    QPushButton {{
        background-color: rgba(16, 185, 129, 0.2);
        color: {EMERALD_400};
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 4px;
        padding: 3px 10px;
        font-size: 12px;
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
        font-size: 12px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background-color: rgba(239, 68, 68, 0.3);
    }}
"""

# ── Minimal scrollbar (token spec) ──
# One bar everywhere. The lane is still reserved (ScrollBarAlwaysOn) so a
# list never reflows the moment its content becomes scrollable; only the
# look and thickness come from ui.tokens, the single place to change them.
from ui.tokens import scrollbar_qss as _scrollbar_qss

MINIMAL_SCROLLBAR_CSS = _scrollbar_qss()


def apply_minimal_scrollbar(view):
    """Give any scroll area / item view the shared token scrollbar:
    permanently reserved lane (never pops in and shoves content), flat
    thumb, no arrows. Appends to the widget's own stylesheet."""
    from PyQt6.QtCore import Qt
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    existing = view.styleSheet() or ""
    if "QScrollBar:vertical" not in existing:
        view.setStyleSheet(existing + MINIMAL_SCROLLBAR_CSS)
