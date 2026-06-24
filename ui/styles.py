"""
ui/styles.py

Central QSS stylesheet for the RhemaCast operator UI.
All colours and geometry are derived from the HTML/Tailwind draft (global.css).
"""

# ─── Colour Tokens ───────────────────────────────────────────────────────────
SLATE_950 = "#020617"
SLATE_900 = "#0f172a"
SLATE_800 = "#1e293b"
SLATE_700 = "#334155"
SLATE_600 = "#475569"
SLATE_500 = "#64748b"
SLATE_400 = "#94a3b8"
SLATE_300 = "#cbd5e1"
SLATE_100 = "#f1f5f9"
WHITE = "#f8fafc"

CHROME_BG = "#1a1a1a"
CHROME_TAB_ACTIVE = "#2d2d2d"

BLUE_400 = "#60a5fa"
BLUE_500 = "#3b82f6"
CYAN_400 = "#22d3ee"
AMBER_500 = "#f59e0b"
AMBER_900 = "#78350f"
EMERALD_400 = "#34d399"
EMERALD_500 = "#10b981"
RED_500 = "#ef4444"
RED_600 = "#dc2626"

BORDER_SUBTLE = "rgba(255, 255, 255, 12)"   # white/5  ≈ 5% white
BORDER_LIGHT = "rgba(255, 255, 255, 25)"     # white/10
PANEL_BG = "rgba(15, 23, 42, 100)"           # slate-900/40


# ─── Main Application Stylesheet ─────────────────────────────────────────────
APP_STYLESHEET = f"""
/* ── Global Reset ── */
QWidget {{
    background-color: {SLATE_950};
    color: {WHITE};
    font-family: 'Nunito', 'Segoe UI', sans-serif;
    font-size: 12px;
    border: none;
}}

/* ── Splitter Handles (Resizers) ── */
QSplitter::handle:horizontal {{
    width: 6px;
    background: rgba(59, 130, 246, 0.15);
}}
QSplitter::handle:horizontal:hover {{
    background: rgba(59, 130, 246, 0.35);
}}
QSplitter::handle:vertical {{
    height: 6px;
    background: rgba(59, 130, 246, 0.15);
}}
QSplitter::handle:vertical:hover {{
    background: rgba(59, 130, 246, 0.35);
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
    padding: 4px 12px;
    font-weight: 600;
    font-size: 11px;
}}
QPushButton:hover {{
    background-color: {SLATE_600};
}}
QPushButton:pressed {{
    background-color: {SLATE_800};
}}

/* ── Line Edit ── */
QLineEdit {{
    background: rgba(0, 0, 0, 100);
    color: {WHITE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    selection-background-color: {BLUE_500};
}}
QLineEdit:focus {{
    border-color: {BLUE_500};
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
    padding: 6px 10px;
    font-size: 11px;
    border-radius: 6px;
}}
"""

# ─── Panel Header Style ──────────────────────────────────────────────────────
PANEL_HEADER_STYLE = f"""
    QWidget {{
        background-color: rgba(30, 41, 59, 130); /* bg-slate-800/50 */
        border-bottom: 1px solid rgba(255, 255, 255, 12); /* border-white/5 */
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
PANEL_BODY_STYLE = f"""
    QWidget.MainPanel {{
        background-color: rgba(15, 23, 42, 100); /* bg-slate-900/40 */
        border: 1px solid rgba(255, 255, 255, 12); /* border-white/5 */
        border-radius: 8px;
    }}
"""

# ─── Queue Item Styles ───────────────────────────────────────────────────────
QUEUE_ITEM_STYLE = f"""
    QFrame#QueueItem {{
        background: rgba(6, 182, 212, 12); /* bg-cyan-500/5 */
        border: 1px solid rgba(6, 182, 212, 50); /* border-cyan-500/20 */
        border-radius: 4px;
        padding: 8px;
    }}
    QFrame#QueueItem:hover {{
        border-color: {CYAN_400}; /* hover:border-cyan-400 */
    }}
"""

# ─── Macro Button Styles ─────────────────────────────────────────────────────
MACRO_BTN_AMBER = f"""
    QPushButton {{
        background-color: rgba(245, 158, 11, 0.9);
        color: {AMBER_900};
        border-radius: 4px;
        border-bottom: 3px solid rgb(180, 120, 0);
        font-weight: 800;
        font-size: 14px;
        padding: 4px 16px;
        margin-top: 0px;
    }}
    QPushButton:hover {{
        background-color: rgba(251, 191, 36, 0.95);
    }}
    QPushButton:pressed {{
        background-color: rgba(217, 119, 6, 0.9);
        border-bottom: 0px;
        margin-top: 3px;
    }}
"""

MACRO_BTN_CLEAR = f"""
    QPushButton {{
        background-color: rgba(51, 65, 85, 0.9);
        color: {WHITE};
        border-radius: 4px;
        border-bottom: 3px solid rgb(30, 41, 59);
        font-weight: 700;
        font-size: 12px;
        padding: 4px 16px;
        margin-top: 0px;
    }}
    QPushButton:hover {{
        background-color: rgba(71, 85, 105, 0.9);
    }}
    QPushButton:pressed {{
        background-color: rgba(30, 41, 59, 0.9);
        border-bottom: 0px;
        margin-top: 3px;
    }}
"""

# ─── Verse Row Styles ────────────────────────────────────────────────────────
VERSE_EVEN_BG = "rgba(255, 255, 255, 8)"
VERSE_ODD_BG = "transparent"
VERSE_SELECTED_BG = "rgba(59, 130, 246, 0.1)"
VERSE_HOVER_BG = "rgba(59, 130, 246, 0.15)"

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
        background-color: {AMBER_500};
        color: {SLATE_950};
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
        background-color: rgba(16, 185, 129, 0.35);
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
