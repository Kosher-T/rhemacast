"""
ui/field_chrome.py

Generated chevrons and token-based QSS for the Settings tab's fields.

Why generated images
    Under Fusion, the CSS border-triangle trick on ``::down-arrow`` paints
    nothing useful (the old COMBO_STYLE leaves an empty box), and
    ``QProxyStyle`` primitives are swallowed by ``QStyleSheetStyle`` as soon
    as any stylesheet exists. A small PNG referenced with ``image: url(...)``
    is the mechanism that works on Linux and Windows. The files are generated
    lazily on first use, after a QGuiApplication exists, with QImage/QPainter
    (never QPixmap, which needs a GUI application).

Cache
    Files live in ``<tempdir>/rhemacast-field-arrows-<hash>`` where the hash
    covers the token colours and glyph geometry. Writing is tmp-file +
    ``os.replace`` so two running instances cannot observe a half-written
    PNG. ``@2x`` twins let Qt pick a sharp asset on scaled displays.

Scope
    Every rule is qualified by the widget's objectName. Call
    :func:`apply_combo` / :func:`apply_spin`; never append these rules to an
    application stylesheet (that is what made the old styles paint twice).

State selectors
    Qt evaluates ``:hover`` / ``:disabled`` on the *subcontrol*:
    ``::down-arrow:hover`` works, ``QComboBox:hover::down-arrow`` does not
    brighten the image and can paint a second arrow at the widget centre.
    Every arrow rule therefore repeats ``subcontrol-origin`` and
    ``subcontrol-position``; do not remove those two lines.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

from ui import tokens

# Object names. A Settings field gets one of these, and the generated QSS is
# qualified by it, so nothing can leak into another tab or another widget.
SETTINGS_FONT_FAMILY_COMBO = "settingsFontFamilyCombo"
SETTINGS_FONT_WEIGHT_COMBO = "settingsFontWeightCombo"
SETTINGS_FONT_SIZE_SPIN = "settingsFontSizeSpin"
SETTINGS_FIELD_COMBO = "settingsFieldCombo"
SETTINGS_FIELD_SPIN = "settingsFieldSpin"
SETTINGS_COMPACT_COMBO = "settingsCompactCombo"

# ─── Generated chevrons ──────────────────────────────────────────────────────
# One 12×12 canvas with an 8×5 glyph centred in it. @2x is drawn at twice
# every dimension rather than upscaled, so the round caps stay clean.
_ARROW_VERSION = 1
_ARROW_SIZE = 12
_ARROW_GLYPH_WIDTH = 8.0
_ARROW_GLYPH_HEIGHT = 5.0
_ARROW_PEN_WIDTH = 1.5
_DIRECTORY_PREFIX = "rhemacast-field-arrows"

_STATES = (
    ("normal", tokens.ARROW_COLOR),
    ("hover", tokens.ARROW_COLOR_HOVER),
    ("disabled", tokens.ARROW_COLOR_DISABLED),
)
_DIRECTIONS = ("up", "down")

_PATH_CACHE: Dict[str, Dict[str, str]] = {}


def _cache_key() -> str:
    """Short stable hash of everything that changes the pixels."""
    payload = "|".join((
        str(_ARROW_VERSION),
        str(_ARROW_SIZE),
        repr(_ARROW_GLYPH_WIDTH),
        repr(_ARROW_GLYPH_HEIGHT),
        repr(_ARROW_PEN_WIDTH),
        tokens.ARROW_COLOR,
        tokens.ARROW_COLOR_HOVER,
        tokens.ARROW_COLOR_DISABLED,
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def arrow_directory(base_dir: str | os.PathLike | None = None) -> Path:
    """Directory for this token/geometry combination.

    ``base_dir`` exists for tests (notably a path containing a space); the
    app always uses the platform temp directory.
    """
    root = Path(base_dir) if base_dir is not None else Path(tempfile.gettempdir())
    return root / f"{_DIRECTORY_PREFIX}-{_cache_key()}"


def _draw_chevron(image: QImage, direction: str, color: str, scale: int) -> None:
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(color), _ARROW_PEN_WIDTH * scale)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        centre = _ARROW_SIZE * scale / 2.0
        half_width = _ARROW_GLYPH_WIDTH * scale / 2.0
        half_height = _ARROW_GLYPH_HEIGHT * scale / 2.0
        if direction == "down":
            points = (
                QPointF(centre - half_width, centre - half_height),
                QPointF(centre, centre + half_height),
                QPointF(centre + half_width, centre - half_height),
            )
        else:
            points = (
                QPointF(centre - half_width, centre + half_height),
                QPointF(centre, centre - half_height),
                QPointF(centre + half_width, centre + half_height),
            )
        painter.drawPolyline(points)
    finally:
        painter.end()


def _write_chevron(path: Path, direction: str, color: str, scale: int) -> None:
    size = _ARROW_SIZE * scale
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    _draw_chevron(image, direction, color, scale)

    # A temp name in the same directory keeps the rename atomic. PID + uuid
    # keeps two instances from sharing a temp file.
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        if not image.save(temporary.as_posix(), "PNG"):
            raise RuntimeError(f"could not write arrow image: {path}")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _usable(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def ensure_arrow_images(
        base_dir: str | os.PathLike | None = None) -> Dict[str, str]:
    """Generate any missing chevrons; return logical name -> absolute path.

    Keys are ``up-normal``, ``down-hover``, ``up-disabled@2x`` and so on.
    Called lazily from the QSS helpers, so importing this module before a
    QApplication exists is safe.
    """
    if QGuiApplication.instance() is None:
        raise RuntimeError(
            "field chrome arrows need a QGuiApplication; call this after "
            "the application exists")

    directory = arrow_directory(base_dir)
    cache_key = str(directory)
    cached = _PATH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    directory.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, str] = {}
    for direction in _DIRECTIONS:
        for state, color in _STATES:
            for scale in (1, 2):
                suffix = "@2x" if scale == 2 else ""
                filename = f"chevron-{direction}-{state}{suffix}.png"
                path = directory / filename
                if not _usable(path):
                    _write_chevron(path, direction, color, scale)
                paths[f"{direction}-{state}{suffix}"] = path.as_posix()

    _PATH_CACHE[cache_key] = paths
    return paths


def _url(path: str) -> str:
    """A QSS url() from a plain absolute path (forward slashes only)."""
    return f"url({path})"


# ─── QSS ─────────────────────────────────────────────────────────────────────

def _content_height(widget_height: int) -> int:
    """QSS heights size the content box; the border is added on top."""
    return widget_height - 2 * tokens.FIELD_BORDER_WIDTH


def _combo_metrics(compact: bool) -> dict:
    """Outer metrics for the standard and compact combo variants.

    Both variants derive their content height from the outer height, the
    border and their vertical padding. The compact variant deliberately has
    no max-width: it must keep growing for longer translation names, exactly
    as the legacy inline style did.
    """
    if compact:
        height = tokens.COMPACT_COMBO_HEIGHT
        padding_y = tokens.COMPACT_COMBO_PADDING_Y
        return {
            "height": height,
            "padding_y": padding_y,
            "padding_x": tokens.SPACE_8,
            "button_width": tokens.COMPACT_COMBO_BUTTON_WIDTH,
            "min_width": tokens.COMPACT_COMBO_MIN_WIDTH,
            "max_width": None,
            "radius": tokens.RADIUS_SM,
            "font_size": tokens.TYPE_CAPTION,
            "content": (height - 2 * tokens.FIELD_BORDER_WIDTH
                        - 2 * padding_y),
        }
    return {
        "height": tokens.COMBO_HEIGHT,
        "padding_y": 0,
        "padding_x": tokens.SPACE_12,
        "button_width": tokens.COMBO_BUTTON_WIDTH,
        "min_width": tokens.COMBO_MIN_WIDTH,
        "max_width": tokens.COMBO_MAX_WIDTH,
        "radius": tokens.RADIUS_SM,
        "font_size": tokens.TYPE_BODY,
        "content": _content_height(tokens.COMBO_HEIGHT),
    }


def combo_qss(object_name: str,
              arrow_paths: Dict[str, str] | None = None,
              *, compact: bool = False) -> str:
    """Scoped QComboBox chrome: field surface, hairline, generated chevron.

    ``compact`` keeps the 27px dense-row variant; everything else — the
    chevron, states and explicit subcontrol positioning — is shared.
    """
    arrows = arrow_paths or ensure_arrow_images()
    metrics = _combo_metrics(compact)
    max_width = (f"            max-width: {metrics['max_width']}px;\n"
                 if metrics["max_width"] is not None else "")

    return f"""
        QComboBox#{object_name} {{
            background: {tokens.BG_FIELD};
            color: {tokens.TEXT_PRIMARY};
            border: {tokens.FIELD_BORDER_WIDTH}px solid {tokens.BORDER_POPOVER};
            border-radius: {metrics['radius']}px;
            padding: {metrics['padding_y']}px {metrics['padding_x']}px;
            font-size: {metrics['font_size']}px;
            min-height: {metrics['content']}px;
            max-height: {metrics['content']}px;
            min-width: {metrics['min_width']}px;
{max_width}        }}
        QComboBox#{object_name}:hover {{
            border-color: {tokens.ACCENT_BORDER};
        }}
        QComboBox#{object_name}:focus {{
            border-color: {tokens.ACCENT};
        }}
        QComboBox#{object_name}:on {{
            border-color: {tokens.ACCENT};
        }}
        QComboBox#{object_name}:disabled {{
            color: {tokens.TEXT_MUTED};
        }}
        QComboBox#{object_name}::drop-down {{
            subcontrol-origin: border;
            subcontrol-position: center right;
            width: {metrics['button_width']}px;
            background: transparent;
            border: none;
        }}
        QComboBox#{object_name}::down-arrow {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["down-normal"])};
        }}
        QComboBox#{object_name}::down-arrow:hover {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["down-hover"])};
        }}
        QComboBox#{object_name}::down-arrow:disabled {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["down-disabled"])};
        }}
    """


def spin_qss(object_name: str,
             arrow_paths: Dict[str, str] | None = None) -> str:
    """Scoped QSpinBox chrome with two chevrons inside the inner rect.

    The buttons split ``COMBO_HEIGHT - 2 × border`` exactly, so there is no
    gap and neither covers the border or a rounded corner. The field's
    right padding is derived from the button width; it is not a magic
    number.
    """
    arrows = arrow_paths or ensure_arrow_images()
    inner_height = _content_height(tokens.COMBO_HEIGHT)
    button_height = inner_height // 2
    padding_right = tokens.SPIN_BUTTON_WIDTH

    return f"""
        QSpinBox#{object_name} {{
            background: {tokens.BG_FIELD};
            color: {tokens.TEXT_PRIMARY};
            border: {tokens.FIELD_BORDER_WIDTH}px solid {tokens.BORDER_POPOVER};
            border-radius: {tokens.RADIUS_SM}px;
            padding: 0 {tokens.SPACE_8}px;
            padding-right: {padding_right}px;
            font-size: {tokens.TYPE_BODY}px;
            min-height: {_content_height(tokens.COMBO_HEIGHT)}px;
            max-height: {_content_height(tokens.COMBO_HEIGHT)}px;
            min-width: 80px;
        }}
        QSpinBox#{object_name}:hover {{
            border-color: {tokens.ACCENT_BORDER};
        }}
        QSpinBox#{object_name}:focus {{
            border-color: {tokens.ACCENT};
        }}
        QSpinBox#{object_name}:disabled {{
            color: {tokens.TEXT_MUTED};
        }}
        QSpinBox#{object_name}::up-button,
        QSpinBox#{object_name}::down-button {{
            subcontrol-origin: padding;
            width: {tokens.SPIN_BUTTON_WIDTH}px;
            height: {button_height}px;
            background: transparent;
            border: none;
        }}
        QSpinBox#{object_name}::up-button {{
            subcontrol-position: top right;
        }}
        QSpinBox#{object_name}::down-button {{
            subcontrol-position: bottom right;
        }}
        QSpinBox#{object_name}::up-button:pressed,
        QSpinBox#{object_name}::down-button:pressed {{
            background: transparent;
        }}
        QSpinBox#{object_name}::up-arrow {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["up-normal"])};
        }}
        QSpinBox#{object_name}::down-arrow {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["down-normal"])};
        }}
        QSpinBox#{object_name}::up-arrow:hover {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["up-hover"])};
        }}
        QSpinBox#{object_name}::down-arrow:hover {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["down-hover"])};
        }}
        QSpinBox#{object_name}::up-arrow:disabled {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["up-disabled"])};
        }}
        QSpinBox#{object_name}::down-arrow:disabled {{
            subcontrol-origin: padding;
            subcontrol-position: center;
            width: 12px;
            height: 12px;
            image: {_url(arrows["down-disabled"])};
        }}
    """


def apply_combo(combo, object_name: str = SETTINGS_FIELD_COMBO,
                *, compact: bool = False) -> None:
    """Give one Settings combo its object name and scoped chrome.

    Replacing the widget stylesheet (rather than appending) is deliberate:
    the legacy COMBO_STYLE also declares ``::down-arrow``, and two matching
    arrow rules paint two chevrons. ``install_combo`` (popup view) is
    independent and stays in place.
    """
    combo.setObjectName(object_name)
    combo.setStyleSheet(combo_qss(object_name, compact=compact))


def apply_spin(spin, object_name: str = SETTINGS_FIELD_SPIN) -> None:
    """Give one Settings spin box its object name and scoped chrome."""
    spin.setObjectName(object_name)
    spin.setStyleSheet(spin_qss(object_name))
