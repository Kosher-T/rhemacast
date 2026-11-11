"""ui/theme_kit/preview_manager.py

Preview replay policy for the Theme Designer.

The manager is the single place that decides *whether* the preview should
replay an animation phase. ``ThemePreview`` remains a read-only renderer view;
the Designer document remains the sole owner of theme data.

This module deliberately has no WebEngine dependency so its state machine can
be tested headlessly.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PyQt6.QtCore import QObject, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from core import constants

_PHASE_PRIORITY = ("entry", "transition_in", "transition_out", "out")


def _animation_slot_phases(animation: Any, name: str) -> list[str]:
    """Return the phases in *animation* that use the named library entry."""
    if not isinstance(animation, dict):
        return []
    found: list[str] = []

    def uses(value: Any) -> bool:
        if isinstance(value, str):
            return value == name
        if isinstance(value, dict):
            return value.get("use") == name
        return False

    if uses(animation.get("entry")):
        found.append("entry")
    transition = animation.get("transition")
    if isinstance(transition, dict):
        if uses(transition.get("in")):
            found.append("transition_in")
        if uses(transition.get("out")):
            found.append("transition_out")
    elif uses(transition):
        found.append("transition_in")
    if uses(animation.get("out")):
        found.append("out")
    return found


def _target_animations(theme: dict) -> Iterable[tuple[str, Any]]:
    """Yield ``(label, animation)`` for every container and block target."""
    containers = theme.get("containers")
    if isinstance(containers, list):
        for index, container in enumerate(containers):
            if not isinstance(container, dict):
                continue
            label = str(container.get("id") or index)
            animation = container.get("animation")
            if isinstance(animation, dict):
                yield label, animation
            blocks = container.get("blocks")
            if isinstance(blocks, dict):
                for block_name, block in blocks.items():
                    if isinstance(block, dict) and isinstance(
                            block.get("animation"), dict):
                        yield f"{label}.{block_name}", block["animation"]
    # Legacy v1 has a single top-level container.
    container = theme.get("container")
    if isinstance(container, dict) and isinstance(container.get("animation"), dict):
        yield "container", container["animation"]


def _phase_for_library(name: str, theme: dict) -> Optional[str]:
    for _label, animation in _target_animations(theme):
        phases = _animation_slot_phases(animation, name)
        if phases:
            return min(phases, key=_PHASE_PRIORITY.index)
    return None


def phase_for_paths(paths: Iterable[Any], theme: dict) -> Optional[str]:
    """Map a document change to the one phase the preview should replay.

    Returns ``None`` for style/geometry edits. Split edits map to the entry
    phase because a split belongs to an entry animation.
    """
    found: list[str] = []
    for raw_path in paths or ():
        path = tuple(raw_path)
        if path and path[0] == "animations" and len(path) > 1:
            phase = _phase_for_library(str(path[1]), theme)
            if phase:
                found.append(phase)
            continue
        if "animation" not in path:
            continue
        rest = path[path.index("animation") + 1:]
        if not rest:
            continue
        head = rest[0]
        if head == "split":
            found.append("entry")
        elif head == "transition":
            # Transition edits normally identify in/out. A change to the
            # transition object itself defaults to the in phase.
            found.append("transition_out" if len(rest) > 1 and rest[1] == "out"
                         else "transition_in")
        elif head in ("entry", "out"):
            found.append(head)
    if not found:
        return None
    return min(found, key=_PHASE_PRIORITY.index)


class PreviewManager(QObject):
    """Schedule animation replays for one live Theme Designer preview."""

    def __init__(self, preview, animation_root: Optional[QWidget] = None,
                 parent: Optional[QObject] = None, *,
                 debounce_ms: Optional[int] = None,
                 loop_ms: Optional[int] = None):
        super().__init__(parent)
        self._preview = preview
        self._animation_root = animation_root
        self._theme: dict = {}
        self._sample_id: Optional[str] = None
        self._pending_phase: Optional[str] = None
        self._last_phase: Optional[str] = None
        self._focus_inside = False
        self._visible = True
        self._active = True
        self._running = True

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(
            constants.THEME_PREVIEW_REPLAY_DEBOUNCE_MS
            if debounce_ms is None else max(0, int(debounce_ms)))
        self._debounce.timeout.connect(self._play_pending)

        self._loop = QTimer(self)
        self._loop.setInterval(
            constants.THEME_PREVIEW_REPLAY_LOOP_MS
            if loop_ms is None else max(1, int(loop_ms)))
        self._loop.timeout.connect(self._loop_tick)

        app = QApplication.instance()
        if app is not None and hasattr(app, "focusChanged"):
            app.focusChanged.connect(self._on_focus_changed)
        if app is not None and hasattr(app, "applicationStateChanged"):
            app.applicationStateChanged.connect(self._on_app_state)
            self._active = app.applicationState() == (
                Qt.ApplicationState.ApplicationActive)

    # ── public API ──────────────────────────────────────────────────────────
    def load_theme(self, theme: dict, sample_id: Optional[str] = None) -> None:
        """Load a theme and redraw the current sample through the normal path."""
        self._theme = theme if isinstance(theme, dict) else {}
        if sample_id is not None:
            self._sample_id = sample_id
        self._pending_phase = None
        self._last_phase = None
        self._stop_timers()
        try:
            self._preview.apply_theme(self._theme, sample_id=self._sample_id)
        except TypeError:
            # Lightweight preview stubs predate the sample_id keyword.
            self._preview.apply_theme(self._theme)
            if self._sample_id and hasattr(self._preview, "set_verse"):
                self._preview.set_verse(self._sample_id)

    def update_theme(self, theme: dict, paths: Iterable[Any] = ()) -> None:
        """Apply an edited theme, scheduling a phase only for animation paths."""
        if not self._running:
            return
        self._theme = theme if isinstance(theme, dict) else {}
        phase = phase_for_paths(paths, self._theme)
        if hasattr(self._preview, "apply_theme_in_place"):
            self._preview.apply_theme_in_place(self._theme)
        else:
            self._preview.apply_theme(self._theme)
        if phase is None:
            self._pending_phase = None
            self._last_phase = None
            self._stop_timers()
            return
        self._pending_phase = phase
        self._loop.stop()
        self._debounce.start()

    def set_sample(self, sample_id: str, theme: Optional[dict] = None) -> None:
        """Swap samples. The renderer's normal content transition is enough."""
        if not self._running:
            return
        if theme is not None:
            self._theme = theme if isinstance(theme, dict) else {}
        self._sample_id = sample_id
        self._pending_phase = None
        self._last_phase = None
        self._stop_timers()
        if hasattr(self._preview, "show_sample"):
            self._preview.show_sample(sample_id, self._theme)
        else:
            if hasattr(self._preview, "set_verse"):
                self._preview.set_verse(sample_id)
            self._preview.apply_theme(self._theme)

    def request_replay(self, phase: str) -> None:
        """Phase-card replay entry point; uses the same debounce as edits."""
        if not self._running or phase not in _PHASE_PRIORITY:
            return
        self._pending_phase = phase
        self._loop.stop()
        self._debounce.start()

    def set_visible(self, visible: bool) -> None:
        self._visible = bool(visible)
        if not self._visible:
            self._loop.stop()
        else:
            self._refresh_loop()

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        if not self._active:
            self._loop.stop()
        else:
            self._refresh_loop()

    def shutdown(self) -> None:
        self._running = False
        self._stop_timers()
        app = QApplication.instance()
        if app is not None:
            try:
                app.focusChanged.disconnect(self._on_focus_changed)
            except (TypeError, RuntimeError):
                pass
            try:
                app.applicationStateChanged.disconnect(self._on_app_state)
            except (TypeError, RuntimeError):
                pass

    # ── internals ───────────────────────────────────────────────────────────
    def _stop_timers(self) -> None:
        self._debounce.stop()
        self._loop.stop()

    def _set_focus_inside(self, inside: bool) -> None:
        self._focus_inside = bool(inside)
        if not self._focus_inside:
            self._last_phase = None
            self._loop.stop()
        else:
            self._refresh_loop()

    def _refresh_loop(self) -> None:
        if self._can_loop():
            if not self._loop.isActive():
                self._loop.start()
        else:
            self._loop.stop()

    def _can_loop(self) -> bool:
        return bool(self._running and self._visible and self._active
                    and self._focus_inside and self._last_phase)

    def _on_focus_changed(self, _old, new) -> None:
        root = self._animation_root
        inside = bool(root is not None and new is not None
                      and (new is root or root.isAncestorOf(new)))
        self._set_focus_inside(inside)

    def _on_app_state(self, state) -> None:
        self.set_active(state == Qt.ApplicationState.ApplicationActive)

    def _play_pending(self) -> None:
        if not self._running:
            return
        phase = self._pending_phase or self._last_phase
        self._pending_phase = None
        if phase is None:
            return
        if hasattr(self._preview, "replay_phase"):
            self._preview.replay_phase(phase)
        self._last_phase = phase
        self._refresh_loop()

    def _loop_tick(self) -> None:
        if not self._can_loop():
            self._loop.stop()
            return
        self._preview.replay_phase(self._last_phase)
