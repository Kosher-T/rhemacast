"""
ui/app_theme.py

Single source of truth for RhemaCast application colors.

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
    accent, accent_hover, accent_soft, accent_border, accent_text_on
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
        "text_faint": "#71717a",
        "text_selected": "#f5f3ff",
        # Accent — purple.
        "accent": "#a855f7",
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
