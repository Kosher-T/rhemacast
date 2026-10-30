"""
ui/app_style.py

One widget-style base for every platform.

Qt picks its widget style from the OS: Fusion on a Linux box with no
platform style plugin, the native Windows style on Windows. The two paint
different chrome (frame metrics, button heights, popup padding, icons),
which is exactly the divergence the operator UI must not have. This module
pins the base to Fusion before any widget exists, so every platform starts
from the same drawing code; the app's own QSS and tokens then paint on top.

It also switches off the style's popup animations (QApplication effect
flags). Those are timed by the platform and make side-by-side captures
differ for reasons unrelated to colour or metrics.

The dark colour-scheme hint is requested only for the OS-drawn parts that
QSS cannot reach (the native title bar on Windows 11). It is guarded: Qt
older than 6.8 has no ``setColorScheme``. On this Linux session the hint is
ignored (``colorScheme()`` stays Unknown), so it changes nothing here; the
app palette is applied afterwards by ``ui.app_theme.apply_palette`` either
way.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QStyleFactory

logger = logging.getLogger(__name__)

STYLE_NAME = "fusion"

# Fade/slide effects Qt animates on top of the style. Off everywhere: the
# operator UI is a live control surface, and a menu that fades in over a
# verse is slower to read than one that is simply there.
_DISABLED_EFFECTS = (
    Qt.UIEffect.UI_AnimateCombo,
    Qt.UIEffect.UI_AnimateMenu,
    Qt.UIEffect.UI_FadeMenu,
    Qt.UIEffect.UI_AnimateTooltip,
    Qt.UIEffect.UI_FadeTooltip,
    Qt.UIEffect.UI_AnimateToolBox,
)


def install(app: QApplication) -> bool:
    """Pin the widget style and animation policy. Returns True if Fusion
    was selected (False means the build has no Fusion style — the caller
    still gets the animation policy). Call before constructing widgets."""
    style = QStyleFactory.create(STYLE_NAME)
    selected = style is not None
    if selected:
        app.setStyle(style)
    else:
        logger.warning("Fusion style unavailable; keeping %s",
                       app.style().objectName())

    for effect in _DISABLED_EFFECTS:
        app.setEffectEnabled(effect, False)

    _request_dark_color_scheme()
    return selected


def _request_dark_color_scheme() -> None:
    """Ask the platform for a dark colour scheme, if this Qt can.

    Only QStyleHints knows about this (Qt 6.8+). It is a request, not a
    palette: platforms that do not support it leave it as Unknown. It is
    what keeps Windows 11's native title bar dark when the system itself
    is in light mode; the client area is painted by our own tokens.
    """
    hints = QGuiApplication.styleHints()
    setter = getattr(hints, "setColorScheme", None)
    if setter is None:
        logger.info("QStyleHints.setColorScheme unavailable (Qt < 6.8)")
        return
    try:
        setter(Qt.ColorScheme.Dark)
    except Exception:       # never let a cosmetic hint block startup
        logger.exception("dark colour-scheme request failed")
