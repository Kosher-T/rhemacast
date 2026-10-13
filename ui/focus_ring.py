"""
ui/focus_ring.py

Themed focus indication for whole panels.

A panel is "focused" when it — or ANY of its descendants — holds the
keyboard focus. The app-wide focusChanged signal is the reliable source:
individual widgets only emit FocusIn/FocusOut for themselves, and focus
can land on a child created long after an event filter was installed.

The ring is a thin OVERLAY child, not a border on the panel itself, for
two reasons:
  * A QWidget subclass does not paint QSS background/border unless
    WA_StyledBackground is set — the panels never painted a panel border,
    and turning that on would restyle them app-wide.
  * An overlay can never reflow the panel's contents when focus toggles,
    and it swallows no mouse events.
"""

from PyQt6.QtCore import Qt, QEvent, QRectF, QObject
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QWidget
from PyQt6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
RING_WIDTH = 1
RING_RADIUS = 8
# Opaque accent reads as a heavy band on dark panels; a softened stroke
# keeps the full 2px footprint while sitting lighter on the background.
RING_ALPHA = 185


class FocusRingOverlay(QFrame):
    """Accent outline drawn just inside the panel's edge. Never a mouse
    target, never a layout item — it floats above the panel's content."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._color = QColor("#a855f7")
        self.hide()

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def sync(self):
        """Match the parent's rect and stay on top."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.raise_()

    def show_ring(self, on: bool):
        self.setVisible(bool(on))
        if on:
            self.sync()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)
        color.setAlpha(RING_ALPHA)
        pen = QPen(color)
        pen.setWidth(RING_WIDTH)
        painter.setPen(pen)
        inset = RING_WIDTH / 2.0
        painter.drawRoundedRect(
            QRectF(inset, inset,
                   self.width() - RING_WIDTH, self.height() - RING_WIDTH),
            RING_RADIUS, RING_RADIUS)


def _within(widget, root) -> bool:
    """True when widget is root or a descendant of it."""
    if widget is None or root is None:
        return False
    try:
        return widget is root or root.isAncestorOf(widget)
    except RuntimeError:  # C++ side already gone
        return False


def install_focus_ring(widget: QWidget, manual: bool = False) -> None:
    """Give `widget` a themed outline while it holds focus (self or child).

    `manual=True` installs the ring but leaves its visibility to a state
    machine via `set_focus_ring_visible` (used for the work-area/schedule
    rings whose visibility is about operator context, not the caret).
    """
    app = QApplication.instance()
    if app is None or widget is None:
        return
    if getattr(widget, "_focus_ring_installed", False):
        return
    try:
        from ui.styles import ACCENT
        overlay = FocusRingOverlay(widget)
        overlay.set_color(ACCENT)
        widget._focus_ring_overlay = overlay
    except Exception:
        return
    widget._focus_ring_installed = True
    widget._focus_ring_manual = bool(manual)

    def _on_focus_changed(_old, new):
        try:
            overlay = widget._focus_ring_overlay
            if overlay is None:
                return  # ring removed while still connected
            if getattr(widget, "_focus_ring_manual", False):
                return  # a state machine owns this ring's visibility
            focused = _within(new, widget)
            if overlay.isVisible() == focused:
                return
            overlay.show_ring(focused)
        except RuntimeError:
            pass  # panel torn down mid-signal

    def _on_resize(_obj=None, _event=None):
        try:
            widget._focus_ring_overlay.sync()
        except RuntimeError:
            pass

    try:
        app.focusChanged.connect(_on_focus_changed)
        widget.installEventFilter(_event_filter())
    except (RuntimeError, TypeError):
        return
    widget._focus_ring_disconnect = lambda: (
        app.focusChanged.disconnect(_on_focus_changed),
        widget.removeEventFilter(_event_filter()),
    )
    widget._focus_ring_refresh = lambda: _on_focus_changed(
        None, app.focusWidget())
    widget._focus_ring_resize = _on_resize
    overlay.sync()
    # Evaluate now rather than assuming "not focused": a panel can be
    # created while something inside it already holds focus (the navigator
    # refocuses on load), and the ring must be right on the first frame.
    # Skipped for manual rings — the owning state machine settles them, and
    # a focus-derived value here would flash the wrong region.
    if not widget._focus_ring_manual:
        _on_focus_changed(None, app.focusWidget())


class _RingEventFilter(QObject):
    """Keeps each ring overlay matched to its panel as the panel resizes.

    A single shared instance serves every ringed panel: ``eventFilter``
    receives the watched object, so per-panel state lives on the panel
    itself (``_focus_ring_overlay``), not here.

    This MUST be a QObject: PyQt6's ``installEventFilter`` rejects plain
    callables with ``TypeError``. (A module-level function was installed
    here before, which silently aborted every install halfway — the
    overlay was created but never synced past its first paint, so window
    resizes left a stale-sized ring on screen.)
    """

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            overlay = getattr(obj, "_focus_ring_overlay", None)
            if overlay is not None:
                try:
                    overlay.sync()
                except RuntimeError:
                    pass
        return False


_focus_ring_event_filter: QObject | None = None


def _event_filter() -> QObject:
    """The shared filter, created on first use (never at import: a QObject
    with no app yet has nowhere to live)."""
    global _focus_ring_event_filter
    if _focus_ring_event_filter is None:
        _focus_ring_event_filter = _RingEventFilter()
    return _focus_ring_event_filter


def refresh_focus_ring(widget: QWidget) -> None:
    """Re-evaluate a ring's state (after reparenting, e.g. tab switches)."""
    try:
        refresh = getattr(widget, "_focus_ring_refresh", None)
        if refresh is not None:
            refresh()
        sync_focus_ring(widget)
    except RuntimeError:
        pass


def sync_focus_ring(widget: QWidget) -> None:
    """Re-match the overlay to the panel's current rect."""
    try:
        overlay = getattr(widget, "_focus_ring_overlay", None)
        if overlay is not None:
            overlay.sync()
    except RuntimeError:
        pass


def remove_focus_ring(widget: QWidget) -> None:
    """Detach the ring (teardown)."""
    try:
        # Disconnect FIRST: a focus change during teardown must not reach
        # a handler whose overlay is already gone.
        disconnect = getattr(widget, "_focus_ring_disconnect", None)
        if disconnect is not None:
            disconnect()
        widget._focus_ring_installed = False
        widget._focus_ring_manual = False
        widget._focus_ring_refresh = None
        widget._focus_ring_resize = None
        overlay = getattr(widget, "_focus_ring_overlay", None)
        widget._focus_ring_overlay = None
        if overlay is not None:
            overlay.setParent(None)
            overlay.deleteLater()
    except (RuntimeError, AttributeError):
        pass


def _overlay(widget):
    return getattr(widget, "_focus_ring_overlay", None)


def set_focus_ring_visible(widget: QWidget, on: bool) -> None:
    """Show/hide `widget`'s ring without touching focus ownership.

    Companion to `install_focus_ring` for rings whose visibility is DECIDED
    elsewhere (a state machine) rather than derived from `focusChanged`.
    Marks the ring manual so the focus handler stops driving it.
    """
    try:
        widget._focus_ring_manual = True
        ov = _overlay(widget)
        if ov is not None:
            ov.show_ring(bool(on))
    except RuntimeError:
        pass


def is_within(widget, root) -> bool:
    """Public re-export of the ancestor test (state machines need it too)."""
    return _within(widget, root)


class FocusRingStateMachine:
    """One theme accent, two regions: the scripture work area (browser +
    themes/FTS/fuzzy queue) and the schedule — lit by what the operator is
    actually doing, not merely by which widget holds the caret.

    Two lights, one colour:
      * Work-area ring — on while scripture is displayed (the default
        browsing state). Off when a slide deck is on live (the operator is
        working slides) and while the caret is inside a search textbox.
      * Schedule ring — on only while schedule Alt+Left/Right navigation is
        armed: double-clicking a schedule item into live arms it (Alt+arrows
        continue from that item). Verse stepping (Left/Right hotkey or
        buttons) and focus leaving the schedule disarm it. Mere focus or a
        single click never arms it.

    Typing in a search box suppresses the work-area ring so the box reads
    as the target.

    Call `update()` whenever anything that feeds a predicate changes (live
    payload, focus, tab switch); it is cheap and idempotent.
    """

    def __init__(self, work_area: QWidget, schedule: QWidget | None = None,
                 work_area_of_schedule=None, arm_keep: tuple = ()):
        self.work_area = work_area
        self.schedule = schedule
        self.work_area_of_schedule = work_area_of_schedule
        # Widgets where focus does NOT disarm the schedule ring (e.g. the
        # Bible verse list: single-clicking a verse is preview navigation
        # inside the armed Alt+arrows workflow, not leaving it).
        self.arm_keep = tuple(arm_keep) if arm_keep else ()
        self._schedule_armed = False
        install_focus_ring(work_area, manual=True)
        if schedule is not None:
            install_focus_ring(schedule, manual=True)
        app = QApplication.instance()
        self._app = app
        if app is not None:
            self._on_focus_changed = self._handle_focus
            app.focusChanged.connect(self._on_focus_changed)
        self.update()  # settle the resting state on the first frame

    # ── predicates ────────────────────────────────────────────────────────

    def _search_box_focused(self) -> bool:
        """True when the caret is inside a work-area search textbox.

        Matched by type, not exact class name: navigator inputs subclass
        QLineEdit (BookInput, NumericInput), and an exact-name check goes
        blind the moment anyone subclasses. The name set stays as a net
        for exotic inputs that are not Qt text widgets.
        """
        if self._app is None:
            return False
        focused = self._app.focusWidget()
        if focused is None or not _within(focused, self.work_area):
            return False
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return True
        try:
            return focused.metaObject().className() in _SEARCH_INPUT_CLASSES
        except RuntimeError:
            return False

    def _scripture_displayed(self) -> bool:
        return bool(self.work_area_of_schedule()) if self.work_area_of_schedule else True

    # ── arm / disarm (schedule Alt+Left/Right context) ───────────────────

    def arm_schedule(self) -> None:
        """Double-click pushed a schedule item live: Alt+arrows continue
        from it, so the schedule ring lights (focus is inside already)."""
        self._schedule_armed = True
        self.update()

    def disarm_schedule(self) -> None:
        """Verse stepping or focus leaving the schedule ends the Alt+arrows
        context: the ring goes out and stays out until the next push."""
        if self._schedule_armed:
            self._schedule_armed = False
            self.update()

    # ── state ─────────────────────────────────────────────────────────────

    def state(self) -> dict:
        return {
            "schedule_armed": self._schedule_armed,
            "search_box_focused": self._search_box_focused(),
            "scripture_displayed": self._scripture_displayed(),
        }

    def update(self) -> None:
        st = self.state()
        set_focus_ring_visible(self.work_area, st["scripture_displayed"]
                               and not st["search_box_focused"])
        if self.schedule is not None:
            set_focus_ring_visible(self.schedule, st["schedule_armed"])

    def _handle_focus(self, _old, _new) -> None:
        try:
            # Clicks (or keys) outside the schedule end the Alt+arrows
            # context along with the focus — except moves into arm_keep
            # widgets (verse list), which belong to the workflow.
            # Focus moving inside changes nothing: only a double-click
            # push re-arms.
            if self.schedule is not None and not _within(_new, self.schedule):
                if not any(_within(_new, w) for w in self.arm_keep):
                    self._schedule_armed = False
            self.update()
        except RuntimeError:
            pass

    def dispose(self) -> None:
        if self._app is not None and self._on_focus_changed is not None:
            try:
                self._app.focusChanged.disconnect(self._on_focus_changed)
            except (RuntimeError, TypeError):
                pass
        self._on_focus_changed = None
        for widget in (self.work_area, self.schedule):
            if widget is not None:
                remove_focus_ring(widget)


_SEARCH_INPUT_CLASSES = {"QLineEdit", "SearchField", "QTextEdit", "QPlainTextEdit"}

