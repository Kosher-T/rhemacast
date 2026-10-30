"""
ui/dialogs/__init__.py

One dialog language for the operator UI: token surface, painted state icon,
text-only buttons in a fixed order, native window frame.

Why this module exists
----------------------
``QMessageBox`` borrows its icon from the platform style and its button
order from ``SH_DialogButtonLayout``. On Linux that gave a blue desktop
info icon and an icon on the OK button; on Windows it gives a different
size, order and chrome. These helpers mirror the ``QMessageBox`` static
API (same names, arguments and return values) so call sites only change
their import, while every pixel of the client area is painted from
``ui.tokens``.

The window frame/title bar stays native on purpose: it keeps drag, the
system menu and accessibility, and it is the same OS chrome the file
pickers use. ``center_on`` positions the dialog explicitly over its parent
for Windows and X11; Wayland compositors ignore top-level ``move()`` and
place the transient child themselves, which is expected.

Nothing here calls ``QStyle.standardIcon`` or ``QIcon.fromTheme``; the
four state icons are painted with QPainter in token colours. Tests enforce
both facts, and that no other module calls QMessageBox/QInputDialog/
QErrorMessage directly.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QLineF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui import tokens

logger = logging.getLogger(__name__)

# ─── Qt enum aliases ────────────────────────────────────────────────────────
# Call sites use these instead of importing QMessageBox themselves, so the
# "no direct QMessageBox outside this module" rule stays true.
StandardButton = QMessageBox.StandardButton
ButtonRole = QMessageBox.ButtonRole
Icon = QMessageBox.Icon

Ok = StandardButton.Ok
Save = StandardButton.Save
Discard = StandardButton.Discard
Cancel = StandardButton.Cancel
Yes = StandardButton.Yes
No = StandardButton.No
Close = StandardButton.Close
NoButton = StandardButton.NoButton

# ─── The one button-order line ──────────────────────────────────────────────
# Windows convention: affirmative actions left of the dismissive ones.
# Flip this tuple to change every dialog at once. Custom action buttons keep
# their add-order and are placed before this sequence, so Cancel stays last.
BUTTON_ORDER = (Ok, Save, Yes, No, Discard, Cancel, Close)

BUTTON_LABELS = {
    Ok: "OK",
    Save: "Save",
    Discard: "Discard",
    Cancel: "Cancel",
    Yes: "Yes",
    No: "No",
    Close: "Close",
}

_STANDARD_VALUES = tuple(int(b) for b in BUTTON_ORDER)

_SURFACE_NAME = "rcDialogSurface"
_TITLE_NAME = "rcDialogTitle"
_BODY_NAME = "rcDialogBody"
_HINT_NAME = "rcDialogHint"


def _dialog_qss() -> str:
    return f"""
        QDialog {{
            background: {tokens.BG_POPOVER};
        }}
        QFrame#{_SURFACE_NAME} {{
            background: {tokens.BG_POPOVER};
            border: 1px solid {tokens.BORDER_POPOVER};
            border-radius: {tokens.RADIUS_MD}px;
        }}
        QLabel#{_TITLE_NAME} {{
            background: transparent;
            color: {tokens.TEXT_PRIMARY};
            font-size: {tokens.TYPE_TITLE}px;
            font-weight: {tokens.WEIGHT_SEMIBOLD};
        }}
        QLabel#{_BODY_NAME} {{
            background: transparent;
            color: {tokens.TEXT_SECONDARY};
            font-size: {tokens.TYPE_BODY}px;
            font-weight: {tokens.WEIGHT_REGULAR};
        }}
        QLabel#{_HINT_NAME} {{
            background: transparent;
            color: {tokens.TEXT_MUTED};
            font-size: {tokens.TYPE_CAPTION}px;
            font-weight: {tokens.WEIGHT_REGULAR};
        }}
    """


# ─── Painted state icons ────────────────────────────────────────────────────
_ICON_SIZE = 28
_ICON_STROKE = 2.0


class _StateIcon(QWidget):
    """A 28 px state glyph drawn from token colours (no platform icon)."""

    def __init__(self, kind: str = "information", parent=None):
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(_ICON_SIZE, _ICON_SIZE)

    def _color(self) -> str:
        return {
            "information": tokens.ACCENT,
            "warning": tokens.WARNING,
            "critical": tokens.DANGER,
            "question": tokens.ACCENT_TEXT,
        }.get(self._kind, tokens.ACCENT)

    def paintEvent(self, event):  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(self._color()), _ICON_STROKE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        kind = self._kind
        if kind == "warning":
            path = QPainterPath()
            path.moveTo(14.0, 3.6)
            path.lineTo(25.0, 23.4)
            path.lineTo(3.0, 23.4)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(QLineF(14.0, 10.0, 14.0, 17.0))
            painter.setBrush(QColor(self._color()))
            painter.drawEllipse(QRectF(13.0, 19.6, 2.0, 2.0))
        else:
            painter.drawEllipse(QRectF(3.0, 3.0, 22.0, 22.0))
            if kind == "critical":
                painter.drawLine(QLineF(9.5, 9.5, 18.5, 18.5))
                painter.drawLine(QLineF(18.5, 9.5, 9.5, 18.5))
            elif kind == "question":
                path = QPainterPath()
                path.moveTo(9.6, 10.8)
                path.cubicTo(9.6, 6.2, 18.4, 6.2, 18.4, 10.8)
                path.cubicTo(18.4, 13.4, 14.0, 13.6, 14.0, 16.8)
                painter.drawPath(path)
                painter.setBrush(QColor(self._color()))
                painter.drawEllipse(QRectF(13.0, 19.4, 2.0, 2.0))
            else:  # information
                painter.setBrush(QColor(self._color()))
                painter.drawEllipse(QRectF(13.0, 8.0, 2.0, 2.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(QLineF(14.0, 12.6, 14.0, 20.0))
        painter.end()


def _kind_from_icon(icon) -> str:
    """Map a QMessageBox.Icon (or our own string) to the painted kind."""
    if isinstance(icon, str):
        return icon if icon in ("information", "warning", "critical",
                                "question") else "information"
    return {
        Icon.Information: "information",
        Icon.Warning: "warning",
        Icon.Critical: "critical",
        Icon.Question: "question",
    }.get(icon, "information")


# ─── Dialog base ────────────────────────────────────────────────────────────
class Dialog(QDialog):
    """Base for app dialogs: token surface, native frame, explicit centering.

    The outer QDialog is the OS window; ``surface`` is the client card. Both
    are painted ``BG_POPOVER`` so a rounded client corner never flashes a
    different colour on a square native frame.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_dialog_qss())
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setSizeGripEnabled(False)
        self._autocenter = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.surface = QFrame(self)
        self.surface.setObjectName(_SURFACE_NAME)
        outer.addWidget(self.surface)

        self.body_layout = QVBoxLayout(self.surface)
        self.body_layout.setContentsMargins(
            tokens.SPACE_24, tokens.SPACE_24,
            tokens.SPACE_24, tokens.SPACE_24)
        self.body_layout.setSpacing(tokens.SPACE_16)

    # -- explicit placement -------------------------------------------------
    def center_on(self, parent=None) -> None:
        """Centre over the parent window (or the screen when there is none).

        Windows and X11 honour this; Wayland compositors may ignore a
        top-level move and place the transient child themselves.
        """
        parent = parent or self.parentWidget()
        screen = None
        if parent is not None:
            top = parent.window()
            frame = top.frameGeometry()
            screen = top.screen()
        else:
            frame = None
        if screen is None:
            screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        size = self.sizeHint()
        if frame is not None and frame.isValid():
            x = frame.center().x() - size.width() // 2
            y = frame.center().y() - size.height() // 2
        else:
            x = available.center().x() - size.width() // 2
            y = available.center().y() - size.height() // 2
        x = max(available.left(), min(x, available.right() - size.width() + 1))
        y = max(available.top(), min(y, available.bottom() - size.height() + 1))
        self.move(x, y)

    def showEvent(self, event):  # noqa: N802 (Qt API)
        super().showEvent(event)
        if self._autocenter:
            self.adjustSize()
            self.center_on()

    def done(self, result: int):  # noqa: N802 (Qt API)
        # Preserve the same integer the static helpers return.
        super().done(result)


# ─── Message dialog ─────────────────────────────────────────────────────────
class MessageDialog(Dialog):
    """Drop-in replacement for the QMessageBox subset this app uses.

    Supported: window title, icon kind, text, standard buttons, custom
    action buttons, default button, ``button()``, ``clickedButton()``,
    ``exec()``/``show()``, and ``buttonClicked``.
    """

    buttonClicked = pyqtSignal(object)

    def __init__(self, parent=None, icon=None, title: str = "",
                 text: str = ""):
        super().__init__(parent)
        self._kind = _kind_from_icon(icon) if icon is not None else "information"
        self._standard_buttons: dict[StandardButton, QPushButton] = {}
        self._standard_for_widget: dict[QPushButton, StandardButton] = {}
        self._custom_buttons: list[QPushButton] = []
        self._custom_roles: dict[QPushButton, ButtonRole] = {}
        self._clicked: QPushButton | None = None
        self._default_button: QPushButton | None = None
        self._explicit_default: StandardButton | None = None
        self._escape_button: QPushButton | None = None
        self._info_label: QLabel | None = None

        top = QHBoxLayout()
        top.setSpacing(tokens.SPACE_16)
        top.setContentsMargins(0, 0, 0, 0)
        self._icon = _StateIcon(self._kind, self.surface)
        top.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(tokens.SPACE_8)
        text_col.setContentsMargins(0, 0, 0, 0)
        self._title_label = QLabel(title, self.surface)
        self._title_label.setObjectName(_TITLE_NAME)
        self._title_label.setWordWrap(True)
        self._title_label.setVisible(bool(title))
        text_col.addWidget(self._title_label)

        self._body_label = QLabel(text, self.surface)
        self._body_label.setObjectName(_BODY_NAME)
        self._body_label.setWordWrap(True)
        self._body_label.setTextFormat(Qt.TextFormat.PlainText)
        self._body_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._body_label.setMinimumWidth(320)
        self._body_label.setMaximumWidth(520)
        text_col.addWidget(self._body_label)
        text_col.addStretch(1)
        top.addLayout(text_col, 1)
        self.body_layout.addLayout(top)

        self._button_row = QHBoxLayout()
        self._button_row.setSpacing(tokens.SPACE_8)
        self._button_row.setContentsMargins(0, 0, 0, 0)
        self._button_row.addStretch(1)
        self.body_layout.addLayout(self._button_row)

        if title:
            self.setWindowTitle(title)

    # -- content ------------------------------------------------------------
    def setIcon(self, icon) -> None:  # noqa: N802 (Qt API)
        self._kind = _kind_from_icon(icon)
        self._icon.set_kind(self._kind)

    def icon_kind(self) -> str:
        return self._kind

    def setText(self, text: str) -> None:  # noqa: N802 (Qt API)
        self._body_label.setText(text)

    def text(self) -> str:
        return self._body_label.text()

    def setInformativeText(self, text: str) -> None:  # noqa: N802 (Qt API)
        if self._info_label is None:
            self._info_label = QLabel(self.surface)
            self._info_label.setObjectName(_HINT_NAME)
            self._info_label.setWordWrap(True)
            self._info_label.setTextFormat(Qt.TextFormat.PlainText)
            index = self.body_layout.indexOf(self._button_row)
            self.body_layout.insertWidget(max(index, 0), self._info_label)
        self._info_label.setText(text)
        self._info_label.setVisible(bool(text))

    def informativeText(self) -> str:  # noqa: N802 (Qt API)
        return self._info_label.text() if self._info_label else ""

    def setWindowTitle(self, title: str) -> None:  # noqa: N802 (Qt API)
        super().setWindowTitle(title)
        if hasattr(self, "_title_label"):
            self._title_label.setText(title)
            self._title_label.setVisible(bool(title))

    # -- buttons ------------------------------------------------------------
    def _clear_buttons(self) -> None:
        for widget in list(self._standard_for_widget) + list(self._custom_buttons):
            self._button_row.removeWidget(widget)
            widget.deleteLater()
        self._standard_buttons.clear()
        self._standard_for_widget.clear()
        self._custom_buttons.clear()
        self._custom_roles.clear()
        self._default_button = None
        self._clicked = None

    def _new_button(self, text: str, primary: bool = False) -> QPushButton:
        button = QPushButton(text, self.surface)
        button.setAutoDefault(False)
        button.setDefault(False)
        button.setIconSize(QSize(0, 0))
        button.setFixedHeight(tokens.BUTTON_HEIGHT)
        button.setMinimumWidth(84)
        button.setStyleSheet(tokens.button_qss(
            "primary" if primary else "secondary"))
        return button

    def setStandardButtons(self, buttons) -> None:  # noqa: N802 (Qt API)
        self._clear_buttons()
        flags = StandardButton(int(buttons))
        for standard in BUTTON_ORDER:
            if flags & standard:
                button = self._new_button(BUTTON_LABELS[standard])
                button.clicked.connect(
                    lambda _checked=False, b=button: self._on_button(b))
                self._standard_buttons[standard] = button
                self._standard_for_widget[button] = standard
                self._button_row.addWidget(button)
        self._refresh_button_emphasis()
        self._apply_default(self._explicit_default)

    def addButton(self, text_or_standard, role=None):  # noqa: N802 (Qt API)
        if role is None and isinstance(text_or_standard, StandardButton):
            standard = text_or_standard
            button = self._new_button(BUTTON_LABELS[standard])
            self._standard_buttons[standard] = button
            self._standard_for_widget[button] = standard
            self._button_row.addWidget(button)
        else:
            button = self._new_button(str(text_or_standard))
            self._custom_buttons.append(button)
            self._custom_roles[button] = role or ButtonRole.ActionRole
            # Custom actions sit before the standard dismissive sequence.
            first_std = None
            for index in range(self._button_row.count()):
                item = self._button_row.itemAt(index)
                if item.widget() in self._standard_for_widget:
                    first_std = index
                    break
            if first_std is None:
                self._button_row.addWidget(button)
            else:
                self._button_row.insertWidget(first_std, button)
        button.clicked.connect(
            lambda _checked=False, b=button: self._on_button(b))
        self._refresh_button_emphasis()
        self._apply_default(self._explicit_default)
        return button

    def button(self, standard: StandardButton) -> QPushButton | None:  # noqa: N802
        return self._standard_buttons.get(standard)

    def setDefaultButton(self, button) -> None:  # noqa: N802 (Qt API)
        if isinstance(button, StandardButton):
            self._explicit_default = button
            widget = self._standard_buttons.get(button)
        else:
            widget = button
            self._explicit_default = None
        if widget is not None and widget in self._standard_for_widget:
            self._default_button = widget
            self._apply_default(self._explicit_default)
        elif widget is not None:
            self._default_button = widget
            self._refresh_button_emphasis()

    def _apply_default(self, standard) -> None:
        if standard is not None:
            widget = self._standard_buttons.get(standard)
            if widget is not None:
                self._default_button = widget
        if self._default_button is None:
            for candidate in BUTTON_ORDER:
                if candidate in self._standard_buttons:
                    self._default_button = self._standard_buttons[candidate]
                    break
            if self._default_button is None and self._custom_buttons:
                self._default_button = self._custom_buttons[0]
        self._refresh_button_emphasis()

    def _refresh_button_emphasis(self) -> None:
        for button in list(self._standard_for_widget) + list(self._custom_buttons):
            is_default = button is self._default_button
            button.setDefault(is_default)
            button.setStyleSheet(tokens.button_qss(
                "primary" if is_default else "secondary"))

    def setEscapeButton(self, button) -> None:  # noqa: N802 (Qt API)
        if isinstance(button, StandardButton):
            button = self._standard_buttons.get(button)
        self._escape_button = button

    def clickedButton(self) -> QPushButton | None:  # noqa: N802 (Qt API)
        return self._clicked

    def standardButton(self, button) -> StandardButton:  # noqa: N802 (Qt API)
        return self._standard_for_widget.get(button, NoButton)

    # -- keyboard -----------------------------------------------------------
    def _escape_target(self) -> QPushButton | None:
        if self._escape_button is not None:
            return self._escape_button
        for standard in (Cancel, Close, No, Discard):
            if standard in self._standard_buttons:
                return self._standard_buttons[standard]
        buttons = list(self._standard_for_widget) + list(self._custom_buttons)
        if len(buttons) == 1:
            return buttons[0]
        return self._default_button

    def _on_button(self, button: QPushButton) -> None:
        self._clicked = button
        self.buttonClicked.emit(button)
        standard = self._standard_for_widget.get(button)
        if standard is not None:
            self.done(int(standard))
            return
        role = self._custom_roles.get(button, ButtonRole.ActionRole)
        accepted = role in (ButtonRole.AcceptRole, ButtonRole.YesRole,
                            ButtonRole.ActionRole)
        self.done(int(QDialog.DialogCode.Accepted if accepted
                      else QDialog.DialogCode.Rejected))

    def keyPressEvent(self, event):  # noqa: N802 (Qt API)
        if event.key() == Qt.Key.Key_Escape:
            target = self._escape_target()
            if target is not None:
                self._on_button(target)
            else:
                self.reject()
            event.accept()
            return
        super().keyPressEvent(event)


def _run(dialog: MessageDialog) -> StandardButton:
    result = dialog.exec()
    if result in _STANDARD_VALUES:
        return StandardButton(result)
    return NoButton


def _message(parent, icon: str, title: str, text: str, buttons, default):
    dialog = MessageDialog(parent, icon=icon, title=title, text=text)
    dialog.setStandardButtons(buttons)
    if default is not None:
        dialog.setDefaultButton(default)
    return _run(dialog)


# ─── QMessageBox-compatible static helpers ──────────────────────────────────
def information(parent, title, text, buttons=Ok, defaultButton=NoButton):
    default = Ok if defaultButton == NoButton else defaultButton
    return _message(parent, "information", title, text, buttons, default)


def warning(parent, title, text, buttons=Ok, defaultButton=NoButton):
    default = Ok if defaultButton == NoButton else defaultButton
    return _message(parent, "warning", title, text, buttons, default)


def critical(parent, title, text, buttons=Ok, defaultButton=NoButton):
    default = Ok if defaultButton == NoButton else defaultButton
    return _message(parent, "critical", title, text, buttons, default)


def question(parent, title, text, buttons=Yes | No, defaultButton=NoButton):
    # Measured Fusion behavior before this module existed: Enter on a Yes/No
    # question chose No, and Escape chose No. Keep that exact default unless
    # the caller names another button.
    default = No if defaultButton == NoButton else defaultButton
    return _message(parent, "question", title, text, buttons, default)


# ─── Input dialogs (replace QInputDialog statics) ───────────────────────────
class _InputDialog(Dialog):
    """Shared chrome for one-field input dialogs."""

    def __init__(self, parent, title: str, label: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._title_label = QLabel(title, self.surface)
        self._title_label.setObjectName(_TITLE_NAME)
        self._title_label.setWordWrap(True)
        self.body_layout.addWidget(self._title_label)

        self._label = QLabel(label, self.surface)
        self._label.setObjectName(_BODY_NAME)
        self._label.setWordWrap(True)
        self.body_layout.addWidget(self._label)

        self._button_row = QHBoxLayout()
        self._button_row.setSpacing(tokens.SPACE_8)
        self._button_row.addStretch(1)
        self._ok = self._new_button("OK", primary=True)
        self._ok.setDefault(True)
        self._cancel = self._new_button("Cancel")
        self._ok.clicked.connect(self.accept)
        self._cancel.clicked.connect(self.reject)
        self._button_row.addWidget(self._ok)
        self._button_row.addWidget(self._cancel)
        self.body_layout.addLayout(self._button_row)

    def _new_button(self, text: str, primary: bool = False) -> QPushButton:
        button = QPushButton(text, self.surface)
        button.setAutoDefault(False)
        button.setFixedHeight(tokens.BUTTON_HEIGHT)
        button.setMinimumWidth(84)
        button.setStyleSheet(tokens.button_qss(
            "primary" if primary else "secondary"))
        return button


class TextInputDialog(_InputDialog):
    def __init__(self, parent, title: str, label: str, text: str = "",
                 echo=None):
        super().__init__(parent, title, label)
        self._edit = QLineEdit(text, self.surface)
        self._edit.setStyleSheet(tokens.field_qss())
        self._edit.setMinimumWidth(360)
        if echo is not None:
            self._edit.setEchoMode(echo)
        self._edit.returnPressed.connect(self.accept)
        self.body_layout.insertWidget(2, self._edit)
        self._edit.selectAll()
        self._edit.setFocus()

    def value(self) -> str:
        return self._edit.text()


class DoubleInputDialog(_InputDialog):
    def __init__(self, parent, title: str, label: str, value: float,
                 minimum: float, maximum: float, decimals: int, step: float):
        super().__init__(parent, title, label)
        self._spin = QDoubleSpinBox(self.surface)
        self._spin.setStyleSheet(tokens.field_qss())
        self._spin.setDecimals(decimals)
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        self._spin.setValue(value)
        self._spin.setMinimumWidth(360)
        self.body_layout.insertWidget(2, self._spin)
        self._spin.setFocus()
        self._spin.selectAll()

    def value(self) -> float:
        return self._spin.value()


def get_text(parent, title, label, echo=None, text="", **kwargs):
    """Mirror of ``QInputDialog.getText`` -> ``(str, bool)``."""
    dialog = TextInputDialog(parent, title, label, text=text, echo=echo)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return (dialog.value() if accepted else ""), accepted


def get_double(parent, title, label, value=0.0, minimum=-2147483647.0,
               maximum=2147483647.0, decimals=2, step=1.0, **kwargs):
    """Mirror of ``QInputDialog.getDouble`` -> ``(float, bool)``."""
    dialog = DoubleInputDialog(parent, title, label, value, minimum, maximum,
                               decimals, step)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return (dialog.value() if accepted else value), accepted


# ─── Multiline editor (deck slide text) ─────────────────────────────────────
class TextEditDialog(Dialog):
    def __init__(self, parent, title: str, label: str, text: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(480, 320)
        if label:
            hint = QLabel(label, self.surface)
            hint.setObjectName(_HINT_NAME)
            hint.setWordWrap(True)
            self.body_layout.addWidget(hint)
        self._edit = QPlainTextEdit(self.surface)
        self._edit.setStyleSheet(tokens.field_qss())
        self._edit.setPlainText(text)
        self.body_layout.addWidget(self._edit, 1)

        row = QHBoxLayout()
        row.setSpacing(tokens.SPACE_8)
        row.addStretch(1)
        save = QPushButton("Save", self.surface)
        cancel = QPushButton("Cancel", self.surface)
        for button, primary in ((save, True), (cancel, False)):
            button.setAutoDefault(False)
            button.setFixedHeight(tokens.BUTTON_HEIGHT)
            button.setMinimumWidth(84)
            button.setStyleSheet(tokens.button_qss(
                "primary" if primary else "secondary"))
        save.setDefault(True)
        save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(cancel)
        self.body_layout.addLayout(row)

    def value(self) -> str:
        return self._edit.toPlainText()


def edit_text(parent, title, label, text=""):
    """Modal multiline editor -> ``(str, bool)``."""
    dialog = TextEditDialog(parent, title, label, text)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return (dialog.value() if accepted else ""), accepted


# ─── Assertion helpers used by tests ────────────────────────────────────────
def standard_button_order(dialog: MessageDialog) -> list[str]:
    """Visible button labels in layout order (custom actions included)."""
    labels = []
    for index in range(dialog._button_row.count()):
        item = dialog._button_row.itemAt(index)
        widget = item.widget()
        if isinstance(widget, QPushButton):
            labels.append(widget.text())
    return labels
