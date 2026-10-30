"""
ui/app_theme.py

Single source of truth for RhemaCast application colors, plus the
Settings-backed per-area interface font helpers (area_font / font_qss).

THEMES maps a theme name → role → value. Add a new theme by adding one
dict entry; activate it with set_theme() before UI construction (styles
are resolved at import/apply time, so switching is authoring-time, not
runtime). All QSS in ui/styles.py and all panel stylesheets must resolve
through these roles (imported via ui.styles aliases) — never hardcode a
color elsewhere.

Roles:
  Backgrounds (greys/blacks — never tinted blue):
    bg_app, bg_panel, bg_raised, bg_input, bg_hover, bg_even_row, bg_odd_row
  Text:
    text_primary, text_muted, text_faint, text_selected
  Accent (purple family):
    accent, accent_text, accent_hover, accent_soft, accent_border,
    accent_text_on
  Selection (search results, schedule — purple highlight):
    selection_bg, selection_border, selection_text
  Focus:
    focus_ring
  Chrome/dividers (neutral):
    border_subtle, border_light, chrome_bg, chrome_tab_active
  Status (semantic — stable across themes):
    success, success_soft, warning, warning_text, error, error_soft, info
"""

# ─── Themes ────────────────────────────────────────────────────────────────

THEMES = {
    "graphite": {
        # Backgrounds — greys and blacks.
        # NOTE: translucent roles use #AARRGGBB (QColor- AND QSS-valid;
        # CSS rgba() strings do not parse in QColor).
        "bg_app": "#0a0a0c",
        "bg_panel": "#64141417",
        "bg_raised": "#1d1d22",
        "bg_input": "#64000000",
        "bg_hover": "#08ffffff",
        "bg_even_row": "#06ffffff",
        "bg_odd_row": "#59000000",
        # Text.
        "text_primary": "#fafafa",
        "text_muted": "#a1a1aa",
        # Faint text (placeholders, hints, empty states) must still clear
        # 4.5:1 on the surface it sits on: #8b8b93 is 5.85:1 on bg_app,
        # 5.70:1 on bg_panel, 4.97:1 on bg_raised, 4.53:1 on selection_bg.
        # (The previous #71717a was 4.09 / 3.99 / 3.47 / 3.17 — it failed.)
        "text_faint": "#8b8b93",
        "text_selected": "#f5f3ff",
        # Accent — purple.
        # `accent` stays the fill/border colour; `accent_text` is the
        # readable-on-dark variant for accent-coloured *text* (7.49:1 on
        # bg_app, 6.35:1 on bg_raised — `accent` was 5.00 / 4.24).
        "accent": "#a855f7",
        "accent_text": "#c084fc",
        "accent_hover": "#9333ea",
        "accent_light": "#c471ed",
        "accent_soft": "#26a855f7",
        "accent_border": "#59a855f7",
        "accent_text_on": "#ffffff",
        # Selection — purple highlight (search results, schedule).
        # Solid (never translucent): renders identically on every
        # surface, and dark enough that grey secondary text stays readable.
        "selection_bg": "#2b2135",
        # Text selection INSIDE inputs/editors is a different job than a
        # row fill: it must be unmistakable. Brighter and saturated, with
        # text_selected on top (contrast checked).
        "text_selection": "#6d28d9",
        "selection_border": "#a855f7",
        "selection_text": "#f5f3ff",
        # Focus.
        "focus_ring": "#a855f7",
        # Chrome / dividers.
        "border_subtle": "#0cffffff",
        "border_light": "#19ffffff",
        "chrome_bg": "#1a1a1a",
        "chrome_tab_active": "#2d2d2d",
        # Translucent chrome (buttons idle/hover, toolbar, menus).
        "menu_bg": "#f01d1d22",
        "chrome_soft": "#991d1d22",
        "chrome_strong": "#e61d1d22",
        "toolbar_bg": "#c8141417",
        # Status semantics (intentionally not purple).
        "success": "#10b981",
        "success_soft": "#3310b981",
        "warning": "#f59e0b",
        "warning_text": "#78350f",
        "error": "#ef4444",
        "error_soft": "#26ef4444",
        "info": "#60a5fa",
    },
}

DEFAULT_THEME = "graphite"

_REQUIRED_ROLES = (
    "bg_app bg_panel bg_raised bg_input bg_hover bg_even_row bg_odd_row "
    "text_primary text_muted text_faint text_selected "
    "accent accent_hover accent_light accent_soft accent_border accent_text_on "
    "accent_text "
    "selection_bg selection_border selection_text text_selection "
    "focus_ring border_subtle border_light chrome_bg chrome_tab_active "
    "menu_bg chrome_soft chrome_strong toolbar_bg "
    "success success_soft warning warning_text error error_soft info"
).split()


def validate_theme(name: str) -> None:
    """Raise KeyError if a theme is missing roles (fail fast at startup)."""
    missing = [r for r in _REQUIRED_ROLES if r not in THEMES[name]]
    if missing:
        raise KeyError(f"theme {name!r} missing roles: {missing}")


# ─── Active theme ──────────────────────────────────────────────────────────

_active_name = DEFAULT_THEME


def set_theme(name: str) -> None:
    """Activate a theme by name (call before UI construction)."""
    global _active_name
    if name not in THEMES:
        raise KeyError(f"unknown app theme: {name!r} "
                       f"(have: {sorted(THEMES)})")
    validate_theme(name)
    _active_name = name


def active_name() -> str:
    return _active_name


def theme_names() -> list:
    return sorted(THEMES)


def color(role: str) -> str:
    """Resolve a color role from the active theme."""
    return THEMES[_active_name][role]


def apply_palette(app) -> None:
    """Apply the active theme to the application QPalette (native widgets)."""
    from PyQt6.QtGui import QPalette, QColor
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(color("bg_app")))
    p.setColor(QPalette.ColorRole.WindowText, QColor(color("text_primary")))
    p.setColor(QPalette.ColorRole.Base, QColor("#000000"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(color("bg_raised")))
    p.setColor(QPalette.ColorRole.Text, QColor(color("text_primary")))
    p.setColor(QPalette.ColorRole.PlaceholderText,
               QColor(color("text_faint")))
    p.setColor(QPalette.ColorRole.Button, QColor(color("bg_raised")))
    p.setColor(QPalette.ColorRole.ButtonText,
               QColor(color("text_primary")))
    p.setColor(QPalette.ColorRole.Highlight, QColor(color("accent")))
    p.setColor(QPalette.ColorRole.HighlightedText,
               QColor(color("accent_text_on")))
    p.setColor(QPalette.ColorRole.Link, QColor(color("accent_hover")))
    p.setColor(QPalette.ColorRole.ToolTipBase,
               QColor(color("bg_raised")))
    p.setColor(QPalette.ColorRole.ToolTipText,
               QColor(color("text_primary")))
    app.setPalette(p)


# ─── Per-area interface fonts (settings-backed) ─────────────────────────────
# Each text area (Bible verses, slide strips, deck list, designer text,
# search results) stores its own family/weight/size under
# "<area>.font_family" / "<area>.font_weight" / "<area>.font_size".
# Nothing is applied globally: consumers read their area's keys (with
# fallbacks preserving today's look) and the Settings → Interface section
# edits them with a live preview.

INTERFACE_FONT_WEIGHT_DEFAULT = 400
INTERFACE_FONT_WEIGHTS = (
    (100, "Thin"), (200, "Extra Light"), (300, "Light"), (400, "Normal"),
    (500, "Medium"), (600, "Demi Bold"), (700, "Bold"),
    (800, "Extra Bold"), (900, "Black"),
)
INTERFACE_FONT_PREVIEW_TEXT = (
    "The quick brown fox jumps over the lazy dog 0123456789")

# ─── Live font-change notification ──────────────────────────────────────────
# Settings → Interface cards save one key per control. Chrome that is always
# on screen (top tab names, panel headers, schedule rows) re-reads its group
# from this signal instead of waiting for a restart. The QObject is created
# lazily so importing this color module never needs Qt.

_font_bus_instance = None


def _font_bus():
    global _font_bus_instance
    if _font_bus_instance is not None:
        try:
            _font_bus_instance.signalsBlocked()   # liveness probe
        except RuntimeError:
            # The QApplication that created it is gone (tests build a new
            # app per case); widgets made under the old app are gone too,
            # so a fresh signal is the correct replacement.
            _font_bus_instance = None
    if _font_bus_instance is None:
        from PyQt6.QtCore import QObject, pyqtSignal

        class _InterfaceFontBus(QObject):
            changed = pyqtSignal(str)   # area prefix, e.g. "panel.labels"

        _font_bus_instance = _InterfaceFontBus()
    return _font_bus_instance


def subscribe_interface_font_changed(callback) -> None:
    """Call `callback(prefix)` after any interface font control is saved."""
    _font_bus().changed.connect(callback)


def notify_interface_font_changed(prefix: str = "") -> None:
    """Announce that a settings-backed font group changed."""
    _font_bus().changed.emit(prefix)


def resolve_font_family(value) -> str:
    """A saved family iff it names an installed font, else "" (keep the
    current painter/widget font — today's look preserved). Never raises."""
    try:
        from PyQt6.QtGui import QFontDatabase
        if value and value in set(QFontDatabase.families()):
            return value
    except Exception:
        pass
    return ""


def resolve_font_weight(value, default: int = 400) -> int:
    """A saved weight iff it parses to 1-1000, else the default (today's
    look preserved). Never raises."""
    try:
        weight = int(value)
    except (TypeError, ValueError):
        return default
    return weight if 1 <= weight <= 1000 else default


def area_font(prefix: str, size_default: int, weight_default: int = 400,
              size_min: int = 7, size_max: int = 24, family_key=None,
              weight_key=None, size_key=None) -> dict:
    """Validated {family, weight, size} for a settings area. Key names are
    explicit (house style is flat underscores: "bible.verse_text_size").
    Unset/invalid falls back to today's rendering ("" family = keep
    current font). Never raises."""
    from core.database import get_setting
    family_key = family_key or f"{prefix}.font_family"
    weight_key = weight_key or f"{prefix}.font_weight"
    size_key = size_key or f"{prefix}.font_size"
    try:
        family = resolve_font_family(get_setting(family_key, ""))
        weight = resolve_font_weight(get_setting(weight_key, ""),
                                     weight_default)
        size = int(get_setting(size_key, str(size_default)))
        if not size_min <= size <= size_max:
            size = size_default
    except Exception:
        family, weight, size = "", weight_default, size_default
    return {"family": family, "weight": weight, "size": size}


def font_qss(spec: dict) -> str:
    """QSS font fragment for a validated area_font spec (color rides
    separately in the caller's stylesheet)."""
    fam = f" font-family: '{spec['family']}';" if spec.get("family") else ""
    return (f"{fam} font-size: {spec.get('size', 10)}px;"
            f" font-weight: {spec.get('weight', 400)};")


def build_interface_font(family=None, size=None, weight=None, size_min=7,
                         size_max=72, size_default=13, weight_default=400):
    """QFont from raw settings values, validated with fallbacks.

    Unknown family -> system family; out-of-range size -> size_default;
    junk weight -> weight_default. Never raises (worst case: defaults).
    """
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication
    font = QFont()
    try:
        system = QApplication.font()
    except Exception:
        system = QFont()
    resolved = resolve_font_family(family)
    font.setFamily(resolved or system.family())
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = size_default
    if not size_min <= size <= size_max:
        size = size_default
    font.setPointSize(size)
    try:
        weight = int(weight)
    except (TypeError, ValueError):
        weight = weight_default
    if not 1 <= weight <= 1000:
        weight = weight_default
    font.setWeight(weight)
    return font
