"""Minimal thin-stroke SVG icon set — one size everywhere.

22 icons, 24px grid, 1.8px round strokes in near-white (#f4f4f5) for
contrast on the dark chrome. Text abbreviations (B/I/U, REC, RTL, …)
stay text — they are labels, not pictographs.
"""

import logging
import os

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon

logger = logging.getLogger(__name__)

ICON_PX = 16
_ICON_DIR = os.path.join(os.path.dirname(__file__), "assets", "icons")

_cache: dict[str, QIcon] = {}


def icon_path(name: str) -> str:
    """Filesystem path for an icon (empty if unknown)."""
    path = os.path.join(_ICON_DIR, f"{name}.svg")
    return path if os.path.isfile(path) else ""


def icon(name: str) -> QIcon:
    """Cached QIcon for a set member. Never raises: unknown names log
    once and yield an empty icon (caller keeps its text fallback)."""
    if name not in _cache:
        path = icon_path(name)
        if not path:
            logger.warning(f"Unknown icon: {name!r}")
            _cache[name] = QIcon()
        else:
            _cache[name] = QIcon(path)
    return _cache[name]


def apply_button(btn, name: str, px: int = ICON_PX, tooltip: str | None = None):
    """Put an icon on a button at the single standard size: clears the
    text label (tooltips/accessible names on the caller stay untouched)."""
    btn.setIcon(icon(name))
    btn.setIconSize(QSize(px, px))
    btn.setText("")
    if tooltip is not None:
        btn.setToolTip(tooltip)
