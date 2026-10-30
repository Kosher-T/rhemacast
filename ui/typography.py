"""
ui/typography.py

Application-wide typography: the bundled Inter family, the app QFont, and
an A/B switch for text rendering.

    install(app)    call once, right after QApplication exists and before
                    any widget is constructed.

RHEMA_TEXT_MODE
    full     (default) bundled Inter — full hinting, antialiased
    none               bundled Inter — no hinting (A/B for edge weight)
    legacy             pre-typography behaviour: system font, Qt defaults

The bundled TTFs live beside the other app assets, in ui/assets/fonts/
(Regular 400 / Medium 500 / SemiBold 600 / Bold 700, SIL OFL 1.1 — see
ui/assets/fonts/OFL.txt). The directory is resolved for both a source
checkout and a frozen/packaged build.

The values below are DEFAULTS, not enforcement: they are what the app
looks like until the operator changes something. Per-area sizes (Bible
verse/reference, slide strips/deck/editor, search results/reference) are
settings-backed and accept whatever the operator picks — see
Settings → Interface, ui/tabs/settings_tab.py.
"""

import logging
import os
import sys

from PyQt6.QtGui import QFont, QFontDatabase

logger = logging.getLogger(__name__)

MODE_ENV = "RHEMA_TEXT_MODE"
MODE_FULL = "full"
MODE_NONE = "none"
MODE_LEGACY = "legacy"
MODES = (MODE_FULL, MODE_NONE, MODE_LEGACY)
DEFAULT_MODE = MODE_FULL

#: Static faces loaded at startup (weights 400 / 500 / 600 / 700).
FONT_FILES = (
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "Inter-Bold.ttf",
)
FONT_FAMILY = "Inter"

#: Body text size (px) and weight for light-on-dark rendering. Light text
#: on a dark surface looks thinner than it measures, so the default body
#: weight is Medium rather than Regular.
APP_FONT_PX = 13
APP_FONT_WEIGHT = QFont.Weight.Medium

#: Families tried, in order, if the bundled files cannot be loaded.
FALLBACK_FAMILIES = ("Inter", "Noto Sans", "DejaVu Sans", "Sans Serif")

_install_report = {}


def text_mode() -> str:
    """Validated RHEMA_TEXT_MODE (unknown values fall back to the default)."""
    raw = os.environ.get(MODE_ENV, "").strip().lower()
    if not raw:
        return DEFAULT_MODE
    if raw not in MODES:
        logger.warning("unknown %s=%r; using %r", MODE_ENV, raw, DEFAULT_MODE)
        return DEFAULT_MODE
    return raw


def font_dir() -> str:
    """Directory holding the bundled TTFs (works frozen and from source).

    Primary location is ui/assets/fonts/ next to this module — the same
    tree that holds brand-mark.svg, icons, etc. The other candidates are
    frozen-build fallbacks (PyInstaller one-file/one-dir)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, "assets", "fonts")]
    meipass = getattr(sys, "_MEIPASS", "")      # PyInstaller one-file/one-dir
    if meipass:
        candidates.append(os.path.join(meipass, "ui", "assets", "fonts"))
        candidates.append(os.path.join(meipass, "assets", "fonts"))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "ui", "assets", "fonts"))
        candidates.append(os.path.join(exe_dir, "assets", "fonts"))
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[0]


def load_fonts() -> str:
    """Register the bundled faces; return the family name Qt actually
    reports for them ("" if nothing loaded). Never raises."""
    directory = font_dir()
    families = []
    for name in FONT_FILES:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            logger.warning("bundled font missing: %s", path)
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id == -1:
                logger.warning("could not register font: %s", path)
                continue
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
        except Exception as exc:                      # pragma: no cover
            logger.warning("font load failed (%s): %s", name, exc)
    installed = set(QFontDatabase.families())
    for family in families:
        if family in installed:
            return family
    return ""


def build_app_font(family: str, mode: str) -> QFont:
    """App QFont: pixel-sized body text, Medium weight, hinted per mode."""
    font = QFont(family)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setHintingPreference(
        QFont.HintingPreference.PreferFullHinting
        if mode == MODE_FULL
        else QFont.HintingPreference.PreferNoHinting)
    font.setPixelSize(APP_FONT_PX)
    font.setWeight(APP_FONT_WEIGHT)
    return font


def install(app) -> str:
    """Set the application font. Returns the mode actually applied."""
    mode = text_mode()
    _install_report.clear()
    _install_report["mode"] = mode

    if mode == MODE_LEGACY:
        _install_report["family"] = app.font().family()
        _install_report["source"] = "system"
        logger.info("typography: legacy mode (system font %r)",
                    app.font().family())
        return mode

    family = load_fonts()
    source = "bundled"
    if not family:
        installed = set(QFontDatabase.families())
        family = next((f for f in FALLBACK_FAMILIES if f in installed), "")
        source = "fallback"
        logger.warning("typography: bundled Inter unavailable; using %r",
                       family or "Qt default")

    if not family:
        _install_report.update(family="", source="qt-default", mode=mode)
        return mode

    font = build_app_font(family, mode)
    app.setFont(font)

    _install_report.update(family=family, source=source)
    logger.info("typography: mode=%s family=%r (%s) %dpx weight=%d",
                mode, family, source, APP_FONT_PX, APP_FONT_WEIGHT)
    return mode


def install_report() -> dict:
    """What install() actually did — for the Settings panel / diagnostics."""
    return dict(_install_report)
