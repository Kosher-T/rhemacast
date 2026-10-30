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

from ui.tokens import ACCENT, TEXT_PRIMARY, TEXT_SECONDARY

# Tab-name type comes from the "tabs.names" font group (default 12px/700,
# tracked-out: quiet enough to read as navigation rather than controls,
# loud enough to hit on stage). Colour/tracking are fixed; family, weight
# and size are settings-backed.
def text_tab_qss() -> str:
    from ui.app_theme import area_font, font_qss
    spec = area_font("tabs.names", 12, 700, size_min=8, size_max=20)
    return f"""
    QPushButton {{
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        color: {TEXT_SECONDARY};
        {font_qss(spec)}
        letter-spacing: 1px;
        padding: 2px 0px;
    }}
    QPushButton:hover {{ color: {TEXT_PRIMARY}; }}
    QPushButton:checked {{
        color: {TEXT_PRIMARY};
        border-bottom: 2px solid {ACCENT};
    }}
    QPushButton:focus {{
        color: {TEXT_PRIMARY};
    }}
"""


class _TextTabRow(QWidget):
    """Row that re-reads the tab-name font group when Settings changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_buttons = []
        from ui.app_theme import subscribe_interface_font_changed
        subscribe_interface_font_changed(self._on_interface_font_changed)

    def add_font_button(self, button) -> None:
        self._font_buttons.append(button)

    def _on_interface_font_changed(self, prefix: str):
        if prefix == "tabs.names":
            self.apply_font()

    def apply_font(self) -> None:
        qss = text_tab_qss()
        for button in self._font_buttons:
            button.setStyleSheet(qss)


def build_text_tab_row(entries, checked_key=None, *, spacing: int = 18,
                       margins=(8, 0, 8, 0)):
    """Build a horizontal row of text tabs.

    entries: [(key, label, tooltip), ...] — key is what _switch_tab takes.
    Returns (row_widget, QButtonGroup, {key: button}).
    """
    row = _TextTabRow()
    row.setStyleSheet("background: transparent; border: none;")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)

    group = QButtonGroup(row)
    group.setExclusive(True)

    buttons: dict[str, QPushButton] = {}
    qss = text_tab_qss()
    for index, (key, label, tooltip) in enumerate(entries):
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(qss)
        btn.setToolTip(tooltip)
        btn.setAccessibleName(label)
        btn.setAccessibleDescription(tooltip)
        btn.setChecked(key == checked_key)
        group.addButton(btn, index)
        layout.addWidget(btn)
        buttons[key] = btn
        row.add_font_button(btn)

    layout.addStretch()
    return row, group, buttons