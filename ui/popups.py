"""
ui/popups.py

Shared look for the two floating surfaces QSS alone cannot own: combo-box
dropdowns and menus. Both are painted from ``ui.tokens`` so Linux and
Windows show the same surface, row metrics and state language.

Menus and tooltips are plain QSS. Combo popups are a real ``QListView``
plus a delegate because the private QComboBox view's frame, item padding,
hover wash and selected row are platform-style decisions otherwise.
Placement and width stay Qt's own combo-popup algorithm; only the pixels
change.

``install_combo`` is deliberately a free function rather than a QComboBox
subclass: the app builds 24 plain combos (and two QFontComboBoxes) in
place, and swapping the widget class would touch construction sites far
more than a one-line call.
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView, QFrame, QListView, QStyle, QStyledItemDelegate,
)

from ui import tokens

_VIEW_NAME = "rcComboView"


def menu_qss() -> str:
    """One menu surface for every QMenu in the app."""
    return f"""
        QMenu {{
            background: {tokens.BG_POPOVER};
            color: {tokens.TEXT_PRIMARY};
            border: 1px solid {tokens.BORDER_POPOVER};
            border-radius: {tokens.RADIUS_MD}px;
            padding: {tokens.SPACE_4}px;
        }}
        QMenu::item {{
            background: transparent;
            color: {tokens.TEXT_PRIMARY};
            padding: {tokens.SPACE_8}px {tokens.SPACE_12}px;
            border-radius: {tokens.RADIUS_SM}px;
        }}
        QMenu::item:selected {{
            background: {tokens.BG_CARD_HOVER};
            color: {tokens.TEXT_PRIMARY};
        }}
        QMenu::item:disabled {{
            color: {tokens.TEXT_MUTED};
        }}
        QMenu::separator {{
            height: 1px;
            background: {tokens.BORDER_HAIRLINE};
            margin: {tokens.SPACE_4}px {tokens.SPACE_8}px;
        }}
        QMenu::indicator {{
            width: {tokens.SPACE_12}px;
            height: {tokens.SPACE_12}px;
        }}
    """


def tooltip_qss() -> str:
    """One tooltip surface, appended to the application stylesheet."""
    return f"""
        QToolTip {{
            background: {tokens.BG_POPOVER};
            color: {tokens.TEXT_PRIMARY};
            border: 1px solid {tokens.BORDER_POPOVER};
            border-radius: {tokens.RADIUS_SM}px;
            padding: {tokens.SPACE_4}px {tokens.SPACE_8}px;
            font-size: {tokens.TYPE_CAPTION}px;
        }}
    """


def combo_view_qss() -> str:
    return f"""
        QListView#{_VIEW_NAME} {{
            background: {tokens.BG_FIELD};
            border: 1px solid {tokens.BORDER_POPOVER};
            border-radius: {tokens.RADIUS_SM}px;
            padding: {tokens.SPACE_4}px;
            outline: none;
        }}
    """


class ComboRowDelegate(QStyledItemDelegate):
    """One dropdown row: field surface, 8 px padding, accent bar when chosen.

    The bar lane is reserved at rest so selecting a row never shifts its
    text — the same rule the schedule cards and Outputs rows follow.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)

        surface = tokens.BG_FIELD
        if selected:
            surface = tokens.BG_CARD_SELECTED
        elif hovered:
            surface = tokens.BG_CARD_HOVER
        painter.fillRect(rect, QColor(surface))

        bar_left = rect.left()
        if selected:
            painter.fillRect(
                QRectF(bar_left, rect.top(), tokens.SELECTED_BAR_WIDTH,
                       rect.height()),
                QColor(tokens.ACCENT))

        text = index.data(Qt.ItemDataRole.DisplayRole)
        text = "" if text is None else str(text)
        font = QFont(option.font)
        font.setWeight(tokens.WEIGHT_MEDIUM)
        painter.setFont(font)
        painter.setPen(QColor(tokens.TEXT_MUTED if not enabled
                              else tokens.TEXT_PRIMARY))
        text_rect = rect.adjusted(
            tokens.SELECTED_BAR_WIDTH + tokens.SPACE_8, 0,
            -tokens.SPACE_8, 0)
        elided = QFontMetrics(font).elidedText(
            text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect,
                         int(Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignVCenter),
                         elided)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        font = QFont(option.font)
        font.setWeight(tokens.WEIGHT_MEDIUM)
        metrics = QFontMetrics(font)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        width = metrics.horizontalAdvance("" if text is None else str(text))
        width += (tokens.SELECTED_BAR_WIDTH + tokens.SPACE_8
                  + tokens.SPACE_8 + tokens.SPACE_16)
        height = max(tokens.BUTTON_HEIGHT,
                     metrics.height() + 2 * tokens.SPACE_8)
        return QSize(width, height)


def install_combo(combo):
    """Give a QComboBox/QFontComboBox the shared dropdown look.

    Idempotent and cheap; returns the combo so it can wrap a constructor
    expression. Menu/row pixels are ours; popup placement and width remain
    Qt's combo algorithm (identical under Fusion and the Windows style:
    ``SH_ComboBox_Popup`` is 0 in both).
    """
    if combo.property("_rc_combo_installed"):
        return combo

    view = QListView(combo)
    view.setObjectName(_VIEW_NAME)
    view.setFrameShape(QFrame.Shape.NoFrame)
    view.setStyleSheet(combo_view_qss())
    view.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    view.setMouseTracking(True)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setUniformItemSizes(False)
    view.setItemDelegate(ComboRowDelegate(view))

    combo.setView(view)

    # The private popup container is a QFrame window around the view. Kill
    # its platform drop shadow (a Windows-only halo otherwise) and make it
    # transparent so only our rounded view surface is visible.
    container = view.window()
    if container is not None and container is not view:
        container.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True)
        container.setWindowFlag(
            Qt.WindowType.NoDropShadowWindowHint, True)
        container.setStyleSheet("background: transparent; border: none;")

    combo.setProperty("_rc_combo_installed", True)
    return combo
