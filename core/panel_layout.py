"""
core/panel_layout.py

Persist QSplitter layouts across launches (settings-backed).

Usage at build time (defaults apply on first run)::
    track_splitter("slides.outer", outer, [280, 900, 300])

Usage on tab show (re-applies the saved state once real sizes exist)::
    restore_splitter("slides.outer", outer)

Moves are saved debounced (500ms), so dragging never hammers the DB.
"""

import logging

from PyQt6.QtCore import QTimer

logger = logging.getLogger(__name__)


def _key(name: str) -> str:
    return f"layout.splitter.{name}"


def save_splitter(name: str, splitter) -> None:
    """Persist one splitter's state. Never raises."""
    if splitter is None:
        return
    try:
        from core.database import set_setting
        set_setting(_key(name), bytes(splitter.saveState()).hex())
    except Exception as e:
        logger.warning(f"Could not save splitter layout {name!r}: {e}")


def restore_splitter(name: str, splitter) -> bool:
    """Re-apply a saved splitter state. Returns True on success."""
    if splitter is None:
        return False
    try:
        from core.database import get_setting
        raw = get_setting(_key(name), "")
        if not raw:
            return False
        return bool(splitter.restoreState(bytes.fromhex(raw)))
    except Exception as e:
        logger.warning(f"Could not restore splitter layout {name!r}: {e}")
        return False


def _schedule_save(name: str, splitter) -> None:
    timer = getattr(splitter, "_layout_save_timer", None)
    if timer is None:
        timer = QTimer(splitter)
        timer.setSingleShot(True)
        timer.setInterval(500)
        timer.timeout.connect(lambda: save_splitter(name, splitter))
        splitter._layout_save_timer = timer
    timer.start()


def track_splitter(name: str, splitter, default_sizes: list | None = None):
    """Set defaults, best-effort restore, and persist future moves."""
    if default_sizes is not None:
        try:
            splitter.setSizes(default_sizes)
        except Exception:
            pass
    restore_splitter(name, splitter)
    if not getattr(splitter, "_layout_tracked", False):
        splitter._layout_tracked = True
        splitter.splitterMoved.connect(lambda *a: _schedule_save(name, splitter))
    return splitter
