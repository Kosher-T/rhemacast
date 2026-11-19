"""ui/theme_kit/panel_state.py

Which groups are open, remembered per panel in the user's saved UI state.

A Designer panel is described by specs (``docs/PANEL_ORGANIZATION.md``), so
the open/closed state of a Tier-1 heading or a Tier-3 disclosure is a property
of the panel and a stable key, not of a widget instance. Keys look like
``"border"`` or ``"size.width"``.

State lives in the settings table under ``ui.designer.panel.<panel>`` as a
JSON object of ``{"group": expanded}``. A group with no saved entry uses its
spec default, so a new group appears open without a migration.

Every read and write is guarded: a missing table, a corrupt value or a
database error falls back to the default instead of breaking the panel.
"""

from __future__ import annotations

import json

_KEY_PREFIX = "ui.designer.panel"

#: panel → {group key: expanded}. Populated on first read.
_cache: dict[str, dict[str, bool]] = {}
_loaded: set[str] = set()


def _key(panel: str) -> str:
    return f"{_KEY_PREFIX}.{panel}"


def _read(panel: str) -> dict[str, bool]:
    try:
        from core.database import get_setting
        raw = get_setting(_key(panel), "")
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): bool(value) for name, value in data.items()}


def _write(panel: str, state: dict[str, bool]) -> None:
    try:
        from core.database import set_setting
        set_setting(_key(panel),
                    json.dumps({str(k): bool(v) for k, v in state.items()},
                               sort_keys=True))
    except Exception:
        pass


def load(panel: str) -> dict[str, bool]:
    """The saved open state for *panel* (a copy; never the cache itself)."""
    if panel not in _loaded:
        _loaded.add(panel)
        _cache[panel] = _read(panel)
    return dict(_cache.get(panel, {}))


def is_open(panel: str, group: str, default: bool = True) -> bool:
    """Whether *group* is open, falling back to the spec default."""
    return bool(load(panel).get(str(group), default))


def remember(panel: str, group: str, expanded: bool) -> None:
    """Persist one group's open state. No-op when nothing changed."""
    state = load(panel)
    if state.get(str(group)) == bool(expanded):
        return
    state[str(group)] = bool(expanded)
    _cache[panel] = state
    _write(panel, state)


def reset_cache() -> None:
    """Tests: forget in-memory state so the next read hits the store."""
    _cache.clear()
    _loaded.clear()


__all__ = ["is_open", "load", "remember", "reset_cache"]
