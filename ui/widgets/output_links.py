"""
ui/widgets/output_links.py

Floating display-link cards for one output.

Two surfaces, two jobs:

* ``OutputLinksPreview`` — the hover card. It appears beside the cursor,
  shows the two addresses and nothing else (no buttons, no focus, no hit
  testing) and disappears the moment the pointer leaves the output name.
  It is a child overlay inside the output block, so it stays in the app
  window. It exists because a URL is far too long to read in a tooltip.
* ``OutputLinksPopup`` — the click card. The same links, but persistent
  and interactive: one copy button per address and a ghost close button,
  dismissed with Esc, a click outside, or the output-name button again.

The preview never needs to escape the window, so it is an ordinary child
widget (clipped by the panel, destroyed with it). The copy card is a
TOP-LEVEL window instead: it is centred on the screen and must stay above
the app while the operator clicks through its buttons. Neither ever takes
focus, so hovering or opening a card cannot pull focus out of a search
box.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QIcon
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
    QPushButton, QVBoxLayout, QWidget,
)

from ui.icons import apply_button
from ui.tokens import (
    BG_POPOVER, BORDER_POPOVER,
    RADIUS_MD, RADIUS_SM, SPACE_4, SPACE_8, SPACE_12, SPACE_16, SPACE_24,
    SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TYPE_BODY, TYPE_CAPTION, TYPE_TITLE,
    WEIGHT_MEDIUM, WEIGHT_REGULAR, WEIGHT_SEMIBOLD,
    ghost_button_qss,
)

_PREVIEW_DELAY_MS = 140
_COPY_FEEDBACK_MS = 1200

_CARD_QSS = f"""
QFrame#outputLinksCard, QFrame#outputLinksPreview {{
    background: {BG_POPOVER};
    border: 1px solid {BORDER_POPOVER};
    border-radius: {RADIUS_MD}px;
}}
"""

_COPIED_BUTTON_QSS = f"""
QPushButton#outputLinkCopy {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    color: {SUCCESS};
    font-size: {TYPE_BODY}px;
    font-weight: {WEIGHT_SEMIBOLD};
    padding: 0px;
}}
"""


def _role_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"color: {TEXT_MUTED}; background: transparent; border: none;"
        f" font-size: {TYPE_CAPTION}px;"
        f" font-weight: {WEIGHT_SEMIBOLD};"
        " letter-spacing: 0.8px;")
    return label


class _LinkRow(QWidget):
    """One role + address line with its own copy button."""

    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self._role = role
        self._url = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(SPACE_4)

        self.role_label = _role_label(role)
        top.addWidget(self.role_label)
        top.addStretch(1)

        self.copy_button = QPushButton()
        self.copy_button.setObjectName("outputLinkCopy")
        self.copy_button.setFixedSize(22, 22)
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_button.setStyleSheet(ghost_button_qss())
        apply_button(self.copy_button, "copy", px=13)
        self.copy_button.clicked.connect(self._copy)
        top.addWidget(self.copy_button)
        layout.addLayout(top)

        self.value_label = QLabel()
        self.value_label.setWordWrap(False)
        self.value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.value_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
            f" font-size: {TYPE_CAPTION}px; font-weight: {WEIGHT_MEDIUM};")
        layout.addWidget(self.value_label)

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._restore_copy_icon)

    # ── Data ─────────────────────────────────────────────────────────────
    def set_url(self, url: str | None):
        self._url = (url or "").strip()
        available = bool(self._url)
        self.value_label.setText(self._url or "Not connected")
        self.value_label.setStyleSheet(
            f"color: {TEXT_PRIMARY if available else TEXT_MUTED};"
            " background: transparent; border: none;"
            f" font-size: {TYPE_CAPTION}px;"
            f" font-weight: {WEIGHT_MEDIUM};")
        self.copy_button.setEnabled(available)
        self.copy_button.setToolTip(
            f"Copy {self._role.lower()} link" if available
            else "No network connection")
        self.copy_button.setAccessibleName(
            f"Copy {self._role.lower()} display link" if available
            else f"{self._role} display link unavailable")

    @property
    def url(self) -> str:
        return self._url

    # ── Clipboard ────────────────────────────────────────────────────────
    def _copy(self):
        if not self._url:
            return
        try:
            from core.clipboard import write_text
            ok = write_text(self._url)
        except Exception:
            ok = False
        if not ok:
            return
        self.copy_button.setText("\u2713")
        self.copy_button.setIcon(QIcon())
        self.copy_button.setStyleSheet(_COPIED_BUTTON_QSS)
        self.copy_button.setToolTip("Copied")
        self._copy_timer.start(_COPY_FEEDBACK_MS)

    def _restore_copy_icon(self):
        self.copy_button.setText("")
        self.copy_button.setStyleSheet(ghost_button_qss())
        apply_button(self.copy_button, "copy", px=13)
        self.copy_button.setToolTip(
            f"Copy {self._role.lower()} link" if self._url
            else "No network connection")


class OutputLinksPreview(QWidget):
    """Read-only hover card, anchored beside the cursor.

    A CHILD widget, not an OS window: it floats above the output block it
    belongs to, stays clipped to the app window, and goes away with the
    panel. That is the whole point — a tool window would be free to wander
    over other applications.

    Deliberately inert: ``WA_TransparentForMouseEvents`` means the card can
    never sit between the pointer and the output name, so moving the mouse
    away always fires the Leave that hides it. No copy buttons here — the
    click card owns those.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._point: QPoint | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self._card = QFrame()
        self._card.setObjectName("outputLinksPreview")
        self._card.setStyleSheet(_CARD_QSS)
        outer.addWidget(self._card)

        grid = QGridLayout(self._card)
        grid.setContentsMargins(SPACE_12, SPACE_8, SPACE_12, SPACE_8)
        grid.setHorizontalSpacing(SPACE_12)
        grid.setVerticalSpacing(SPACE_4)

        self.local_role = _role_label("Local")
        self.network_role = _role_label("Network")
        # Roles share one width so the two addresses start on the same
        # column, without a magic pixel value.
        role_width = max(self.local_role.sizeHint().width(),
                         self.network_role.sizeHint().width())
        for label in (self.local_role, self.network_role):
            label.setMinimumWidth(role_width)

        self.local_value = QLabel()
        self.network_value = QLabel()
        for label in (self.local_value, self.network_value):
            label.setStyleSheet(
                f"color: {TEXT_PRIMARY}; background: transparent;"
                " border: none;"
                f" font-size: {TYPE_CAPTION}px;"
                f" font-weight: {WEIGHT_MEDIUM};")

        grid.addWidget(self.local_role, 0, 0)
        grid.addWidget(self.local_value, 0, 1)
        grid.addWidget(self.network_role, 1, 0)
        grid.addWidget(self.network_value, 1, 1)

        self._anchor: QWidget | None = None
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._show_now)

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_application_state)

        # A child widget is shown together with its ancestors unless it is
        # explicitly hidden; without this every output would get a card in
        # its top-left corner the moment the panel is shown.
        self.hide()

    # ── Data ─────────────────────────────────────────────────────────────
    def set_links(self, local_url: str, network_url: str | None):
        self.local_value.setText(local_url or "")
        available = bool(network_url)
        self.network_value.setText((network_url or "").strip()
                                   or "Not connected")
        self.network_value.setStyleSheet(
            f"color: {TEXT_PRIMARY if available else TEXT_MUTED};"
            " background: transparent; border: none;"
            f" font-size: {TYPE_CAPTION}px;"
            f" font-weight: {WEIGHT_MEDIUM};")
        if self.isVisible():
            # Keep the card anchored where it was shown, not wherever the
            # pointer has drifted to. Some platforms report a stale cursor.
            self._place(self._point or QCursor.pos())

    # ── Hover lifecycle ──────────────────────────────────────────────────
    def schedule_show(self, anchor: QWidget, delay_ms: int = _PREVIEW_DELAY_MS):
        self._anchor = anchor
        self._show_timer.start(delay_ms)

    def _show_now(self):
        anchor = self._anchor
        if anchor is None or not anchor.isVisible():
            return
        point = QCursor.pos()
        window = anchor.window()
        if window is not None and not window.rect().contains(
                window.mapFromGlobal(point)):
            # Some platforms report a stale/global-less cursor position;
            # the button centre is always inside the window and is right
            # where the pointer is hovering.
            point = anchor.mapToGlobal(anchor.rect().center())
        self.show_at(point)

    def show_at(self, global_pos: QPoint):
        self._point = global_pos
        self._place(global_pos)
        self.show()
        self.raise_()

    def cancel_show(self):
        self._show_timer.stop()

    def _place(self, global_pos: QPoint):
        """Beside the point, never under it, always inside the parent."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        point = parent.mapFromGlobal(global_pos)
        origin = QPoint(point.x() + SPACE_16, point.y() + SPACE_16)
        bounds = parent.visibleRegion().boundingRect()
        if bounds.isEmpty():
            bounds = parent.rect()
        margin = SPACE_8
        if origin.x() + self.width() > bounds.right() - margin:
            origin.setX(point.x() - self.width() - SPACE_16)
        if origin.y() + self.height() > bounds.bottom() - margin:
            origin.setY(point.y() - self.height() - SPACE_16)
        origin.setX(max(bounds.left() + margin, origin.x()))
        origin.setY(max(bounds.top() + margin, origin.y()))
        self.move(origin)

    def _on_application_state(self, state):
        if state == Qt.ApplicationState.ApplicationInactive:
            self.hide()

    def hideEvent(self, event):
        self._show_timer.stop()
        super().hideEvent(event)


class OutputLinksPopup(QWidget):
    """Persistent card with a copy button per address.

    Opened by clicking an output name and centred on the screen the anchor
    lives on. Stays put until Esc, a click outside it, or the anchor button
    is clicked again — so the addresses can be selected or copied without
    racing a hover timeout.
    """

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self._card = QFrame()
        self._card.setObjectName("outputLinksCard")
        self._card.setStyleSheet(_CARD_QSS)
        self._card.setMinimumWidth(330)
        outer.addWidget(self._card)

        card = QVBoxLayout(self._card)
        card.setContentsMargins(
            SPACE_12 + 2, SPACE_12, SPACE_12 + 2, SPACE_12)
        card.setSpacing(SPACE_8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(SPACE_8)

        self._title = QLabel("Display links")
        self._title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
            f" font-size: {TYPE_TITLE}px; font-weight: {WEIGHT_SEMIBOLD};")
        header.addWidget(self._title)
        header.addStretch(1)

        self.close_button = QPushButton("\u00d7")
        self.close_button.setFixedSize(SPACE_24, SPACE_24)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.setStyleSheet(ghost_button_qss(
            font_css=(f"font-size: {TYPE_BODY}px;"
                      f" font-weight: {WEIGHT_MEDIUM};")))
        self.close_button.setToolTip("Close")
        self.close_button.setAccessibleName("Close display links")
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.close_button)
        card.addLayout(header)

        hint = QLabel("Copy a link for OBS or another device")
        hint.setStyleSheet(
            f"color: {TEXT_MUTED}; background: transparent; border: none;"
            f" font-size: {TYPE_CAPTION}px; font-weight: {WEIGHT_REGULAR};")
        card.addWidget(hint)

        self.local_row = _LinkRow("Local")
        self.network_row = _LinkRow("Network")
        card.addSpacing(SPACE_4)
        card.addWidget(self.local_row)
        card.addWidget(self.network_row)

        self._anchor: QWidget | None = None

        app = QApplication.instance()
        if app is not None:
            # Never leave the card floating over OBS/mail after Alt+Tab:
            # it is a stay-on-top tool window, so app deactivation is the
            # only reliable cue to get out of the way.
            app.applicationStateChanged.connect(self._on_application_state)

    # ── Data ─────────────────────────────────────────────────────────────
    def set_links(self, local_url: str, network_url: str | None, *,
                  title: str = ""):
        """Update in place (no child rebuild, so copy state survives)."""
        self._title.setText(title or "Display links")
        self.local_row.set_url(local_url)
        self.network_row.set_url(network_url)
        self.adjustSize()

    # ── Persistent lifecycle ─────────────────────────────────────────────
    def show_persistent(self, anchor: QWidget):
        self._anchor = anchor
        self.adjustSize()
        self._center_on_anchor()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.show()
        self.raise_()

    def _center_on_anchor(self):
        anchor = self._anchor
        if anchor is None:
            return
        point = anchor.mapToGlobal(anchor.rect().center())
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.move(available.center().x() - self.width() // 2,
                  available.center().y() - self.height() // 2)

    def _on_application_state(self, state):
        if state == Qt.ApplicationState.ApplicationInactive:
            self.hide()

    def eventFilter(self, obj, event):
        """Esc or a click anywhere outside the card dismisses it."""
        if not self.isVisible():
            return False
        kind = event.type()
        if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.hide()
            return True
        if kind == QEvent.Type.MouseButtonPress:
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                return False
            if self.frameGeometry().contains(global_pos):
                return False
            anchor = self._anchor
            if anchor is not None and anchor.isVisible():
                top_left = anchor.mapToGlobal(QPoint(0, 0))
                if anchor.rect().contains(global_pos - top_left):
                    # Let the anchor button's own click toggle it shut.
                    return False
            self.hide()
        return False

    def hideEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.closed.emit()
        super().hideEvent(event)
