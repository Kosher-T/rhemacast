"""
ui/panels/text_tabs.py

Borderless text tab rows for the operator sub-pages.

One implementation so every sub-page row reads the same: transparent
buttons, wide tracking, the active page marked with a 2px accent
underline (no box, no icon, no fill). Shared by the Bible panel's
Outputs | Keyword | Semantic row and the Decks panel's Decks | Outputs
row — same look, same keyboard behavior, one place to change it.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ui.styles import ACCENT, SLATE_500, WHITE

# 10px / 700 / tracked-out caps: quiet enough to read as navigation
# rather than controls, loud enough to hit on stage.
TEXT_TAB_QSS = f"""
    QPushButton {{
        background: transparent;
        border: none;
        color: {SLATE_500};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 2px 0px;
    }}
    QPushButton:hover {{ color: {WHITE}; }}
    QPushButton:checked {{
        color: {WHITE};
        border-bottom: 2px solid {ACCENT};
    }}
    QPushButton:focus {{
        color: {WHITE};
    }}
"""


def build_text_tab_row(entries, checked_key=None, *, spacing: int = 18,
                       margins=(8, 0, 8, 0)):
    """Build a horizontal row of text tabs.

    entries: [(key, label, tooltip), ...] — key is what _switch_tab takes.
    Returns (row_widget, QButtonGroup, {key: button}).
    """
    row = QWidget()
    row.setStyleSheet("background: transparent; border: none;")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)

    group = QButtonGroup(row)
    group.setExclusive(True)

    buttons: dict[str, QPushButton] = {}
    for index, (key, label, tooltip) in enumerate(entries):
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(TEXT_TAB_QSS)
        btn.setToolTip(tooltip)
        btn.setAccessibleName(label)
        btn.setAccessibleDescription(tooltip)
        btn.setChecked(key == checked_key)
        group.addButton(btn, index)
        layout.addWidget(btn)
        buttons[key] = btn

    layout.addStretch()
    return row, group, buttons