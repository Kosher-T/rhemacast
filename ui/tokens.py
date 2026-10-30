"""
ui/tokens.py

Small, flat design tokens for the operator UI.

These values are derived from the graphite palette in ``ui.app_theme`` so
adopting them never shifts the current look. They are deliberately plain
constants — no theme machinery, no widget imports. The only functions here
build QSS strings from the constants.

Migration is opt-in: the schedule cards use these tokens today; other panels
keep their existing styles until they are moved over one at a time.

Type: the scale below documents the interface sizes in use. Actual schedule
card sizes remain settings-backed (``schedule.cards``) — the operator's saved
value is always used as-is, including values below the scale's caption size.
The font family is never redefined here; it comes from ``ui.typography``.
"""

# ─── Colour roles ────────────────────────────────────────────────────────────
# Derived from ui/app_theme.py "graphite":
#   bg_base           bg_app
#   bg_panel          bg_panel #64141417 composited over bg_base
#   bg_card           rgba(255, 255, 255, 8) over bg_panel (today's card)
#   bg_card_hover     accent_soft #26a855f7 over bg_card
#   bg_card_selected  selection_bg
#   border_hairline   border_subtle #0cffffff over bg_card
# Contrast (WCAG) is asserted in tests/test_tokens.py.
BG_BASE = "#0a0a0c"
BG_PANEL = "#0e0e10"
BG_CARD = "#161517"
BG_CARD_HOVER = "#2c1f38"
BG_CARD_SELECTED = "#2b2135"
# Raised surface for floating chrome (hover cards) — mirrors app_theme
# "bg_raised" so a popover separates from the panel behind it.
BG_POPOVER = "#1d1d22"
# Input/field well inside a popover: app_theme "bg_input" (39% black)
# composited over BG_POPOVER, resolved to a flat value so a combo popup and
# a dialog field paint the same pixel on every platform.
BG_FIELD = "#121215"
BORDER_HAIRLINE = "#1f1f24"
# Mirrors app_theme "border_light": 10% white, visible over bg_popover.
BORDER_POPOVER = "#19ffffff"

TEXT_PRIMARY = "#fafafa"
TEXT_SECONDARY = "#a1a1aa"
TEXT_MUTED = "#8b8b93"

ACCENT = "#a855f7"          # fill / border only
ACCENT_TEXT = "#c084fc"     # accent-coloured text (on dark)
ACCENT_TINT = "#2a1e36"     # ~13% accent over bg_card
# Dashed/tinted accent outline (mirrors app_theme "accent_border": 35%
# accent, #AARRGGBB — QSS- and QColor-valid alike).
ACCENT_BORDER = "#59a855f7"
SUCCESS = "#10b981"
# Readable-on-tint lift for state text (same relationship as DANGER below):
# #10b981 drops to 4.17:1 on the 30% success hover tint, #34d399 holds 5.5:1.
SUCCESS_TEXT = "#34d399"
# Readable-on-dark lift of app_theme "error" (#ef4444): that value drops to
# 4.1:1 on bg_card_hover / bg_card_selected, so it cannot be used as text
# there. Same hue, lifted until it clears 4.5:1 on every card surface.
DANGER = "#f87171"

# State tints for state-carrying buttons (Start/Stop, REC/STOP, cloak).
# Resting fills mirror app_theme "success_soft" / "error_soft"; the hover
# fills are the same hue one step stronger so the pointer feedback stays in
# the state's colour instead of turning purple.
SUCCESS_TINT = "#3310b981"
SUCCESS_TINT_HOVER = "#4d10b981"
DANGER_TINT = "#26ef4444"
DANGER_TINT_HOVER = "#40ef4444"
WARNING_TINT = "#26f59e0b"
WARNING_TINT_HOVER = "#40f59e0b"

# Quiet row wash for hover (mirrors app_theme "bg_hover"). The list rows are
# painted by a delegate, so this is a translucent overlay rather than a
# surface token: it reads on both the even and odd stripe.
ROW_HOVER = "#14ffffff"
ROW_EVEN = "#08ffffff"
ROW_ODD = "transparent"

# Display-link status roles (ui/connection_status.py). ACCENT doubles as the
# healthy/connected colour: the Live viewport border is the peripheral signal
# and wears the theme accent. WARNING is the "can't tell" caution (the display
# server isn't accepting clients); DISCONNECTED is a muted orange that reads
# as a status rather than an alarm. Both clear the 3:1 non-text floor on the
# dark surfaces (asserted in tests/test_tokens.py).
WARNING = "#f59e0b"
DISCONNECTED = "#c2703d"

# ─── Tab-bar load states ─────────────────────────────────────────────────────
# Loaded tabs carry a low accent wash; unloaded tabs are neutral grey. The
# selected tab keeps the existing active-chrome fill plus an accent underline,
# so it reads apart from both other loaded tabs and unloaded ones. All three
# text/background pairs clear WCAG AA on the chrome (tests/test_tokens.py).
# These are graphite values: a future light theme needs its own tab roles, in
# the same way it needs its own chrome roles.
TAB_LOADED_BG = ACCENT_TINT     # accent wash over the chrome
TAB_LOADED_TEXT = TEXT_PRIMARY
TAB_UNLOADED_BG = "#151517"     # plain neutral grey, no accent
TAB_UNLOADED_TEXT = TEXT_SECONDARY
TAB_SELECTED_BG = "#2d2d2d"     # graphite chrome_tab_active
TAB_SELECTED_TEXT = "#ffffff"

# ─── Radii ───────────────────────────────────────────────────────────────────
RADIUS_SM = 6
RADIUS_MD = 8

# ─── Spacing scale ───────────────────────────────────────────────────────────
SPACE_4 = 4
SPACE_8 = 8
SPACE_12 = 12
SPACE_16 = 16
SPACE_24 = 24

# ─── Type scale ──────────────────────────────────────────────────────────────
TYPE_CAPTION = 12
TYPE_BODY = 13
TYPE_TITLE = 14

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_SEMIBOLD = 600

# ─── Component metrics (smaller than the spacing scale by design) ────────────
SELECTED_BAR_WIDTH = 3
BUTTON_HEIGHT = 28
BUTTON_ICON_SIZE = 28
BUTTON_BORDER_WIDTH = 1
BADGE_PAD_Y = 2
BADGE_PAD_X = SPACE_8
BADGE_BORDER_WIDTH = 1

CARD_OBJECT_NAME = "scheduleCard"

# ─── Option rows (the Outputs theme list) ────────────────────────────────────
OPTION_OBJECT_NAME = "themeOptionRow"

# ─── Scrollbars ──────────────────────────────────────────────────────────────
# One flat bar everywhere: no arrows, no groove, a thumb that reads as
# chrome until you touch it. Thicker than the 5-6px legacy bars because a
# stage machine is often driven with a trackpad, not a mouse wheel.
SCROLLBAR_THICKNESS = 8
SCROLLBAR_HANDLE_RADIUS = 4
SCROLLBAR_MIN_HANDLE = 32

# ─── Translation colour coding ───────────────────────────────────────────────
# Mirrors ui/tabs/library_tab.py's version colours, adjusted only where the
# original was too dark to read as a 1 px border on bg_card (KJV, TPT).
TRANSLATION_COLORS = {
    "KJV": "#8b8b93",
    "NKJV": "#a855f7",
    "NIV": "#f59e0b",
    "ESV": "#10b981",
    "NLT": "#8b5cf6",
    "AMP": "#ec4899",
    "BSB": "#06b6d4",
    "MSG": "#64748b",
    "BIBLE_ENGLISH_MSG": "#64748b",
    "TPT": "#94a3b8",
    "ERV": "#64748b",
}
TRANSLATION_FALLBACK = TEXT_MUTED

# Long canonical IDs get a short badge label.
TRANSLATION_LABELS = {
    "BIBLE_ENGLISH_MSG": "MSG",
}


# ─── QSS helpers ─────────────────────────────────────────────────────────────

def card_qss(background: str = BG_CARD) -> str:
    """QSS for a schedule card at rest and in its three states.

    The left border is always present (transparent at rest) so selecting a
    card paints the 3 px accent bar without shifting the text.
    """
    return f"""
        QFrame#{CARD_OBJECT_NAME} {{
            background: {background};
            border: none;
            border-left: {SELECTED_BAR_WIDTH}px solid transparent;
            border-radius: {RADIUS_MD}px;
        }}
        QFrame#{CARD_OBJECT_NAME}:hover {{
            background: {BG_CARD_HOVER};
        }}
        QFrame#{CARD_OBJECT_NAME}[selected="true"] {{
            background: {BG_CARD_SELECTED};
            border-left: {SELECTED_BAR_WIDTH}px solid {ACCENT};
        }}
        QFrame#{CARD_OBJECT_NAME}[selected="true"]:hover {{
            background: {BG_CARD_SELECTED};
            border-left: {SELECTED_BAR_WIDTH}px solid {ACCENT};
        }}
    """


def option_row_qss(font_css: str = "") -> str:
    """QSS for one clickable option row (the Outputs theme list).

    The row is the whole hit target: no indicator, no swatch — the surface,
    the hover wash and the 3 px accent bar carry every state. The left
    border is always present (transparent at rest) so checking a row never
    shifts its text.

    Hover is the ``hovered`` property, not ``:hover``: Qt does not evaluate
    a pseudo-state on an *ancestor* in a descendant selector, so
    ``...:hover QLabel`` matched every row at rest and painted resting
    labels in the hover colour. The row tracks enter/leave instead
    (``ui.panels.themes_panel.ThemeCard``) and both rules key off that
    property, exactly like ``selected``.
    """
    return f"""
        QFrame#{OPTION_OBJECT_NAME} {{
            background: {BG_CARD};
            border: none;
            border-left: {SELECTED_BAR_WIDTH}px solid transparent;
            border-radius: {RADIUS_MD}px;
        }}
        QFrame#{OPTION_OBJECT_NAME} QLabel {{
            background: transparent;
            color: {TEXT_SECONDARY};
            font-size: {TYPE_BODY}px;
            font-weight: {WEIGHT_MEDIUM};
            {font_css}
        }}
        QFrame#{OPTION_OBJECT_NAME}[hovered="true"] {{
            background: {BG_CARD_HOVER};
        }}
        QFrame#{OPTION_OBJECT_NAME}[hovered="true"] QLabel {{
            color: {TEXT_PRIMARY};
        }}
        QFrame#{OPTION_OBJECT_NAME}[selected="true"] {{
            background: {BG_CARD_SELECTED};
            border-left: {SELECTED_BAR_WIDTH}px solid {ACCENT};
        }}
        QFrame#{OPTION_OBJECT_NAME}[selected="true"] QLabel {{
            color: {TEXT_PRIMARY};
            font-weight: {WEIGHT_SEMIBOLD};
        }}
    """


def button_qss(variant: str = "secondary", font_css: str = "",
               padding: str | None = None, dashed: bool = False) -> str:
    """One button language, two flat surfaces (plus the ghost form).

    ``secondary`` is the workhorse: a card surface with a hairline edge, a
    lift on hover and a stronger selected surface when checked. ``ghost``
    reads as text until touched (menu rows, quiet actions); ``dashed`` is
    the same ghost with an add-affordance outline. Both reserve their edge
    width at rest, so a state change never nudges the label.

    No drop shadows, no outlines heavier than 1 px, and every colour is a
    token with a tested contrast floor. Callers set ``BUTTON_HEIGHT``; this
    function only paints.
    """
    type_css = font_css or (
        f"font-size: {TYPE_CAPTION}px; font-weight: {WEIGHT_SEMIBOLD};")
    pad = padding if padding is not None else f"0 {SPACE_12}px"

    if variant == "ghost":
        edge = (f"border: {BUTTON_BORDER_WIDTH}px dashed {BORDER_HAIRLINE};"
                if dashed else "border: none;")
        hover_edge = (f"border-color: {ACCENT_BORDER};" if dashed else "")
        return f"""
            QPushButton {{
                background: transparent;
                {edge}
                border-radius: {RADIUS_SM}px;
                color: {TEXT_MUTED};
                padding: {pad};
                {type_css}
            }}
            QPushButton:hover, QPushButton:focus {{
                background: {BG_CARD};
                color: {TEXT_PRIMARY};
                {hover_edge}
            }}
            QPushButton:pressed {{
                background: {BG_CARD_SELECTED};
                color: {TEXT_PRIMARY};
            }}
            QPushButton:disabled {{
                background: transparent;
                color: {TEXT_MUTED};
            }}
        """

    if variant == "secondary":
        return f"""
            QPushButton {{
                background: {BG_CARD};
                border: {BUTTON_BORDER_WIDTH}px solid {BORDER_HAIRLINE};
                border-radius: {RADIUS_SM}px;
                color: {TEXT_SECONDARY};
                padding: {pad};
                {type_css}
            }}
            QPushButton:hover, QPushButton:focus {{
                background: {BG_CARD_HOVER};
                border-color: {ACCENT_BORDER};
                color: {TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background: {BG_CARD_SELECTED};
                border-color: {ACCENT_BORDER};
                color: {TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background: {ACCENT_TINT};
                border-color: {ACCENT_BORDER};
                color: {ACCENT_TEXT};
            }}
            QPushButton:checked:hover {{
                background: {ACCENT_TINT};
                border-color: {ACCENT};
                color: {ACCENT_TEXT};
            }}
            QPushButton:disabled {{
                background: transparent;
                border-color: {BORDER_HAIRLINE};
                color: {TEXT_MUTED};
            }}
        """

    if variant == "primary":
        return f"""
            QPushButton {{
                background: {ACCENT_TINT};
                border: {BUTTON_BORDER_WIDTH}px solid {ACCENT_BORDER};
                border-radius: {RADIUS_SM}px;
                color: {ACCENT_TEXT};
                padding: {pad};
                {type_css}
            }}
            QPushButton:hover, QPushButton:focus {{
                background: {BG_CARD_HOVER};
                border-color: {ACCENT};
                color: {ACCENT_TEXT};
            }}
            QPushButton:pressed {{
                background: {BG_CARD_SELECTED};
                border-color: {ACCENT};
                color: {ACCENT_TEXT};
            }}
            QPushButton:disabled {{
                background: {ACCENT_TINT};
                border-color: {BORDER_HAIRLINE};
                color: {TEXT_MUTED};
            }}
        """

    raise ValueError(f"unknown button variant: {variant!r}")


def icon_button_qss(tone: str | None = None, font_css: str = "") -> str:
    """The icon-only form of the button language: a square secondary or a
    state-toned surface. Size comes from ``BUTTON_ICON_SIZE`` at the call
    site; the glyph stays the icon's business."""
    if tone:
        return tone_button_qss(tone, font_css=font_css, padding="0px")
    return button_qss("secondary", font_css=font_css, padding="0px")


def tone_button_qss(tone: str, font_css: str = "",
                    padding: str | None = None) -> str:
    """A state-carrying button painted in its state's colour.

    Used by the Start/Stop service action, REC/STOP and the cloak toggle:
    the fill and label both carry the state, and the label text changes too
    (Start↔Stop, REC↔STOP), so the state never rests on colour alone.
    """
    type_css = font_css or (
        f"font-size: {TYPE_CAPTION}px; font-weight: {WEIGHT_SEMIBOLD};")
    pad = padding if padding is not None else f"0 {SPACE_12}px"
    # tone -> (rest fill, hover fill, readable text role). The text role is
    # lifted where the pure hue cannot clear 4.5:1 on its own hover fill.
    tints = {
        SUCCESS: (SUCCESS_TINT, SUCCESS_TINT_HOVER, SUCCESS_TEXT),
        DANGER: (DANGER_TINT, DANGER_TINT_HOVER, DANGER),
        WARNING: (WARNING_TINT, WARNING_TINT_HOVER, WARNING),
    }
    rest, hover, text = tints.get(tone, (BG_CARD, BG_CARD_HOVER, tone))
    return f"""
        QPushButton {{
            background: {rest};
            border: {BUTTON_BORDER_WIDTH}px solid transparent;
            border-radius: {RADIUS_SM}px;
            color: {text};
            padding: {pad};
            {type_css}
        }}
        QPushButton:hover, QPushButton:focus {{
            background: {hover};
            color: {text};
            border-color: {text};
        }}
        QPushButton:pressed {{
            background: {BG_CARD_SELECTED};
            color: {text};
        }}
        QPushButton:disabled {{
            background: {BG_CARD};
            border-color: {BORDER_HAIRLINE};
            color: {TEXT_MUTED};
        }}
    """


def chip_qss(active: bool, font_css: str = "") -> str:
    """One translation chip in the version row.

    The selected chip wears the same accent language as a selected tab: an
    accent wash, accent text and a 2 px accent underline (the width is
    reserved at rest, so selecting never moves the label). That underline is
    a second, non-colour state cue.
    """
    if active:
        surface, text, edge, underline = (ACCENT_TINT, ACCENT_TEXT,
                                          ACCENT_BORDER, ACCENT)
    else:
        surface, text, edge, underline = (
            "transparent", TEXT_SECONDARY, "transparent", "transparent")
    return f"""
        QPushButton {{
            background: {surface};
            border: 1px solid {edge};
            border-bottom: 2px solid {underline};
            border-radius: {RADIUS_SM}px;
            color: {text};
            padding: 0 {SPACE_8}px;
            {font_css}
        }}
        QPushButton:hover {{
            background: {BG_CARD_HOVER};
            border-color: {ACCENT_BORDER};
            color: {TEXT_PRIMARY};
        }}
        QPushButton:pressed {{
            background: {BG_CARD_SELECTED};
        }}
    """


def ghost_button_qss(font_css: str = "", padding: str = "0px") -> str:
    """Minimal chrome-free button: no border, no fill at rest.

    The quiet button used wherever a control should read as text until you
    touch it (an output name, a card's close glyph, an icon-only copy).
    Hover or keyboard focus paints the raised surface; checked/pressed paint
    the selected one so an open card's trigger stays lit.
    """
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-radius: {RADIUS_SM}px;
            color: {TEXT_MUTED};
            padding: {padding};
            {font_css}
        }}
        QPushButton:hover, QPushButton:focus {{
            background: {BG_CARD_HOVER};
            color: {TEXT_PRIMARY};
        }}
        QPushButton:pressed, QPushButton:checked {{
            background: {BG_CARD_SELECTED};
            color: {TEXT_PRIMARY};
        }}
        QPushButton:disabled {{
            background: transparent;
            color: {TEXT_MUTED};
        }}
    """


def badge_qss(border_color: str, font_css: str = "") -> str:
    """QSS for a translation pill. The fill is solid so the caption keeps a
    known contrast ratio even on a colour-coded card."""
    return f"""
        QLabel {{
            background: {BG_CARD};
            color: {TEXT_SECONDARY};
            border: {BADGE_BORDER_WIDTH}px solid {border_color};
            border-radius: {RADIUS_SM}px;
            padding: {BADGE_PAD_Y}px {BADGE_PAD_X}px;
            {font_css}
        }}
    """


def field_qss() -> str:
    """The input well used by dialog text/number fields.

    It reads as a recessed surface inside a popover: one step darker than
    ``BG_POPOVER``, a hairline edge, the same focus accent as the rest of
    the app. Spin-box arrows are deliberately left to the style (Fusion on
    every platform) — the task scope keeps QSpinBox chrome as it is.
    """
    return f"""
        QLineEdit, QPlainTextEdit, QDoubleSpinBox {{
            background: {BG_FIELD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_POPOVER};
            border-radius: {RADIUS_SM}px;
            padding: {SPACE_4}px {SPACE_8}px;
            selection-background-color: {ACCENT};
            selection-color: {TEXT_PRIMARY};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus {{
            border-color: {ACCENT_BORDER};
        }}
        QLineEdit:disabled, QPlainTextEdit:disabled, QDoubleSpinBox:disabled {{
            color: {TEXT_MUTED};
        }}
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            background: transparent;
            border: none;
            width: {SPACE_16}px;
        }}
    """


def scrollbar_qss() -> str:
    """One scrollbar style for the whole app: flat, arrowless, token-coloured.

    Applied once at application level (``core.ui.RhemaCastApp``) so every
    panel inherits it. There is deliberately no groove/page area: the handle
    floats on whatever surface it scrolls, which is the only way one style
    works over bg_app, bg_panel and bg_popover alike. Hover steps the handle
    from the raised surface colour to muted text grey — a control, not text,
    so no 4.5:1 floor applies, but it stays visible on every surface.

    A widget with its own ``QScrollBar`` rules (``ui.styles``
    ``apply_minimal_scrollbar`` for the verse/schedule/deck lists) keeps
    them: local stylesheets win over the application sheet.
    """
    return f"""
        QScrollBar:vertical {{
            background: transparent;
            width: {SCROLLBAR_THICKNESS}px;
            margin: 0px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {BG_CARD_HOVER};
            min-height: {SCROLLBAR_MIN_HANDLE}px;
            border: none;
            border-radius: {SCROLLBAR_HANDLE_RADIUS}px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {TEXT_MUTED};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            width: 0px;
            background: none;
            border: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
            border: none;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: {SCROLLBAR_THICKNESS}px;
            margin: 0px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {BG_CARD_HOVER};
            min-width: {SCROLLBAR_MIN_HANDLE}px;
            border: none;
            border-radius: {SCROLLBAR_HANDLE_RADIUS}px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {TEXT_MUTED};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            height: 0px;
            width: 0px;
            background: none;
            border: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
            border: none;
        }}
    """
