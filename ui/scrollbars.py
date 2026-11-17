"""Reserved scrollbar lanes for every scrollable surface.

A scroll area that only shows its bar when the content overflows changes its
viewport width at the exact moment overflow appears, which shifts the content
sideways. This module makes the lane permanent instead: the bar is always
laid out, and the application stylesheet (``ui.tokens.scrollbar_qss``) paints
an empty transparent lane when the bar has nothing to do.

The policy is applied in one place for new widgets (an application event
filter) and exported as ``reserve_scrollbar_lane`` for widget-local use.
``ScrollBarAlwaysOff`` surfaces are left alone: those panels page their
content or paint their own overlay bar, so no lane exists to reserve.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication


def _sync_lane_state(bar, span=None) -> None:
    """Mark a bar with no range so QSS can hide its handle.

    Always-on bars keep their lane, but Qt would otherwise paint a full
    handle across an empty lane. The dynamic property lets the stylesheet
    make the handle transparent while the bar has nothing to scroll.

    ``span`` comes from ``rangeChanged``: QScrollArea can emit the signal
    while ``maximum()`` still reads the old value, so the emitted numbers are
    the only reliable source during the signal.
    """
    if span is None:
        span = bar.maximum() - bar.minimum()
    value = "true" if span <= 0 else "false"
    if bar.property("rcLaneEmpty") == value:
        return
    bar.setProperty("rcLaneEmpty", value)
    style = bar.style()
    style.unpolish(bar)
    style.polish(bar)
    bar.update()


def _watch_lane(view: QAbstractScrollArea) -> None:
    for bar in (view.verticalScrollBar(), view.horizontalScrollBar()):
        if bar is None or bar.property("rcLaneWatched") == "true":
            continue
        bar.setProperty("rcLaneWatched", "true")
        # Bind the bar as a default argument: a closure over the loop
        # variable would point both bars at the horizontal one.
        bar.rangeChanged.connect(
            lambda minimum, maximum, target=bar:
            _sync_lane_state(target, maximum - minimum))
        _sync_lane_state(bar)


def reserve_scrollbar_lane(view: QAbstractScrollArea, *,
                           horizontal: bool = True) -> bool:
    """Reserve the bar lane(s) of one scroll area.

    Only ``ScrollBarAsNeeded`` policies change. Returns True when at least one
    policy moved, so callers can count or report the change.
    """
    changed = False
    if view.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded:
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        changed = True
    if (horizontal
            and view.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAsNeeded):
        view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        changed = True
    _watch_lane(view)
    return changed


def apply_to_tree(root) -> int:
    """Reserve lanes for ``root`` and every scroll area below it."""
    count = 1 if (isinstance(root, QAbstractScrollArea)
                  and reserve_scrollbar_lane(root)) else 0
    for area in root.findChildren(QAbstractScrollArea):
        if reserve_scrollbar_lane(area):
            count += 1
    return count


class ScrollbarLaneFilter(QObject):
    """Application event filter that reserves lanes as widgets appear.

    Polish fires during construction, before a widget can be shown, and Show
    covers views created lazily (combo popups, dialogs). A subclass that wants
    no bar sets ``ScrollBarAlwaysOff`` after that and keeps it.
    """

    def eventFilter(self, obj, event):
        if (event.type() in (QEvent.Type.Polish, QEvent.Type.Show)
                and isinstance(obj, QAbstractScrollArea)):
            reserve_scrollbar_lane(obj)
        return False


def install(app: QApplication) -> ScrollbarLaneFilter:
    """Install the filter once per application and cover existing widgets."""
    existing = getattr(app, "_rc_scrollbar_lane_filter", None)
    if existing is not None:
        return existing
    flt = ScrollbarLaneFilter(app)
    app._rc_scrollbar_lane_filter = flt
    app.installEventFilter(flt)
    for widget in app.allWidgets():
        if isinstance(widget, QAbstractScrollArea):
            reserve_scrollbar_lane(widget)
    return flt
