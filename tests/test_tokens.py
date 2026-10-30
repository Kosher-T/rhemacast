"""Design tokens: contrast floor and scale invariants (no Qt needed)."""

from ui import tokens


def _channel(value: int) -> float:
    value = value / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast(fg: str, bg: str) -> float:
    lighter, darker = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_text_roles_clear_contrast_floor():
    surfaces = (
        tokens.BG_BASE, tokens.BG_PANEL, tokens.BG_CARD,
        tokens.BG_CARD_HOVER, tokens.BG_CARD_SELECTED, tokens.BG_POPOVER,
        tokens.BG_FIELD,
    )
    for fg in (tokens.TEXT_PRIMARY, tokens.TEXT_SECONDARY, tokens.TEXT_MUTED,
               tokens.ACCENT_TEXT, tokens.SUCCESS, tokens.SUCCESS_TEXT,
               tokens.DANGER):
        for bg in surfaces:
            ratio = _contrast(fg, bg)
            assert ratio >= 4.5, (fg, bg, round(ratio, 2))


def test_translation_borders_stay_visible_on_cards():
    for name, color in tokens.TRANSLATION_COLORS.items():
        ratio = _contrast(color, tokens.BG_CARD)
        assert ratio >= 3.0, (name, color, round(ratio, 2))


def test_display_link_roles_clear_the_non_text_floor():
    """The always-visible Live border is a 1px line on the dark chrome."""
    for color in (tokens.ACCENT, tokens.WARNING, tokens.DISCONNECTED,
                  tokens.TEXT_MUTED):
        for bg in (tokens.BG_BASE, tokens.BG_PANEL):
            ratio = _contrast(color, bg)
            assert ratio >= 3.0, (color, bg, round(ratio, 2))


def test_scales_are_flat_constants():
    assert (tokens.RADIUS_SM, tokens.RADIUS_MD) == (6, 8)
    assert (tokens.SPACE_4, tokens.SPACE_8, tokens.SPACE_12,
            tokens.SPACE_16, tokens.SPACE_24) == (4, 8, 12, 16, 24)
    assert (tokens.TYPE_CAPTION, tokens.TYPE_BODY,
            tokens.TYPE_TITLE) == (12, 13, 14)
    assert (tokens.WEIGHT_REGULAR, tokens.WEIGHT_MEDIUM,
            tokens.WEIGHT_SEMIBOLD) == (400, 500, 600)


def test_qss_helpers_speak_in_tokens():
    card = tokens.card_qss()
    assert tokens.BG_CARD in card
    assert tokens.BG_CARD_HOVER in card
    assert tokens.BG_CARD_SELECTED in card
    assert tokens.ACCENT in card
    assert f"{tokens.SELECTED_BAR_WIDTH}px" in card
    assert f"border-radius: {tokens.RADIUS_MD}px" in card

    badge = tokens.badge_qss("#f59e0b")
    assert "#f59e0b" in badge
    assert tokens.TEXT_SECONDARY in badge
    assert f"border-radius: {tokens.RADIUS_SM}px" in badge
    assert f"padding: {tokens.BADGE_PAD_Y}px {tokens.BADGE_PAD_X}px" in badge


def test_option_row_qss_speaks_in_tokens():
    row = tokens.option_row_qss()
    for color in (tokens.BG_CARD, tokens.BG_CARD_HOVER,
                  tokens.BG_CARD_SELECTED, tokens.ACCENT, tokens.TEXT_PRIMARY):
        assert color in row
    assert tokens.TEXT_SECONDARY in row, "resting label colour"
    assert f"border-left: {tokens.SELECTED_BAR_WIDTH}px solid transparent" in row
    assert f"border-left: {tokens.SELECTED_BAR_WIDTH}px solid {tokens.ACCENT}" in row
    assert f"font-size: {tokens.TYPE_BODY}px" in row


def test_option_row_hover_is_a_tracked_property():
    """Qt ignores :hover on an ancestor selector, so the hover text colour
    must key off the tracked ``hovered`` property instead. ``...:hover
    QLabel`` painted every resting row in the hover colour."""
    row = tokens.option_row_qss()
    assert ":hover" not in row, "ancestor :hover is ignored by Qt"
    assert f'[hovered="true"] QLabel' in row
    assert f'[hovered="true"]' in row
    assert tokens.BG_CARD_HOVER in row


def test_option_row_colours_clear_the_contrast_floor():
    """Every text role the option row uses, on every surface it paints."""
    pairs = (
        (tokens.TEXT_SECONDARY, tokens.BG_CARD),
        (tokens.TEXT_PRIMARY, tokens.BG_CARD_HOVER),
        (tokens.TEXT_PRIMARY, tokens.BG_CARD_SELECTED),
    )
    for fg, bg in pairs:
        ratio = _contrast(fg, bg)
        assert ratio >= 4.5, (fg, bg, round(ratio, 2))


def test_scrollbar_qss_is_flat_and_arrowless():
    qss = tokens.scrollbar_qss()
    for orientation in ("vertical", "horizontal"):
        assert f"QScrollBar:{orientation}" in qss
        assert f"QScrollBar::handle:{orientation}" in qss
        # No arrow buttons and no page area: the handle floats on the
        # surface behind it.
        assert f"QScrollBar::add-line:{orientation}" in qss
        assert f"QScrollBar::sub-page:{orientation}" in qss
    assert f"width: {tokens.SCROLLBAR_THICKNESS}px" in qss
    assert f"height: {tokens.SCROLLBAR_THICKNESS}px" in qss
    assert f"min-height: {tokens.SCROLLBAR_MIN_HANDLE}px" in qss
    assert f"min-width: {tokens.SCROLLBAR_MIN_HANDLE}px" in qss
    assert (f"border-radius: {tokens.SCROLLBAR_HANDLE_RADIUS}px" in qss)
    assert tokens.BG_CARD_HOVER in qss
    assert tokens.TEXT_MUTED in qss, "hover step"
    assert "background: transparent;\n            width:" in qss, \
        "the track itself must stay transparent"


def test_ghost_button_qss_is_chrome_free_until_touched():
    qss = tokens.ghost_button_qss()
    assert "background: transparent" in qss
    assert tokens.TEXT_MUTED in qss
    assert tokens.BG_CARD_HOVER in qss, "hover surface"
    assert tokens.BG_CARD_SELECTED in qss, "checked/pressed surface"
    assert tokens.TEXT_PRIMARY in qss
    assert ":focus" in qss, "a tab-focusable ghost button needs a focus state"
    assert f"border-radius: {tokens.RADIUS_SM}px" in qss
    assert "border: none" in qss


def test_output_link_cards_have_no_raw_colour_literals():
    """The hover/click link cards speak only in tokens, like the panel."""
    import os
    import re

    path = os.path.join(os.path.dirname(__file__), "..",
                        "ui", "widgets", "output_links.py")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", source)
    assert literals == [], literals


def test_outputs_panel_has_no_raw_colour_literals():
    """The Outputs page must speak only in tokens (no blue, no rgba())."""
    import os
    import re

    path = os.path.join(os.path.dirname(__file__), "..",
                        "ui", "panels", "themes_panel.py")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", source)
    assert literals == [], literals


def test_tab_load_states_are_readable_and_distinct():
    """Loaded (accent wash) vs unloaded (grey) vs selected (chrome + rule)."""
    pairs = (
        (tokens.TAB_LOADED_TEXT, tokens.TAB_LOADED_BG),
        (tokens.TAB_UNLOADED_TEXT, tokens.TAB_UNLOADED_BG),
        (tokens.TAB_SELECTED_TEXT, tokens.TAB_SELECTED_BG),
    )
    for fg, bg in pairs:
        ratio = _contrast(fg, bg)
        assert ratio >= 4.5, (fg, bg, round(ratio, 2))

    # A loaded tab must not read as an unloaded one at rest, and the
    # selected tab must separate from both resting surfaces.
    assert tokens.TAB_LOADED_BG != tokens.TAB_UNLOADED_BG
    assert tokens.TAB_SELECTED_BG not in (tokens.TAB_LOADED_BG,
                                          tokens.TAB_UNLOADED_BG)
    assert tokens.TAB_LOADED_TEXT != tokens.TAB_UNLOADED_TEXT


# ── Workstream polish: button language, chips, rows, scrollbars ─────────────

def _composite(argb: str, base: str) -> str:
    """Flatten an #AARRGGBB tint (or an opaque #RRGGBB) over a surface."""
    value = argb.lstrip("#")
    if len(value) == 6:
        return "#" + value
    alpha = int(value[0:2], 16) / 255.0
    tint = [int(value[i:i + 2], 16) for i in (2, 4, 6)]
    under = [int(base.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    mixed = [round(a * alpha + b * (1 - alpha)) for a, b in zip(tint, under)]
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


def test_button_metrics_are_one_language():
    """Every variant shares the same height, radius and 1px edge budget."""
    assert tokens.BUTTON_HEIGHT == 28
    assert tokens.BUTTON_ICON_SIZE == 28
    assert tokens.BUTTON_BORDER_WIDTH == 1

    secondary = tokens.button_qss("secondary")
    ghost = tokens.button_qss("ghost")
    dashed = tokens.button_qss("ghost", dashed=True)
    for qss in (secondary, ghost, dashed):
        assert f"border-radius: {tokens.RADIUS_SM}px" in qss
        assert "box-shadow" not in qss, "no drop shadows on text surfaces"
        assert ":hover" in qss and ":pressed" in qss and ":disabled" in qss

    # Secondary always reserves its edge; ghost reserves it only when the
    # dashed add-affordance is on, so both keep the label still.
    assert (f"border: {tokens.BUTTON_BORDER_WIDTH}px solid "
            f"{tokens.BORDER_HAIRLINE}") in secondary
    assert "border: none" in ghost
    assert f"{tokens.BUTTON_BORDER_WIDTH}px dashed" in dashed


def test_secondary_button_states_are_distinct_and_token_based():
    qss = tokens.button_qss("secondary")
    assert tokens.BG_CARD in qss, "resting surface"
    assert tokens.BG_CARD_HOVER in qss, "hover surface"
    assert tokens.BG_CARD_SELECTED in qss, "pressed surface"
    assert tokens.TEXT_SECONDARY in qss and tokens.TEXT_PRIMARY in qss
    assert tokens.ACCENT_TINT in qss, "checked state"
    assert tokens.ACCENT_TEXT in qss
    assert tokens.ACCENT_BORDER in qss
    # Checked is not a colour-only story: the surface, the edge and the
    # text all change together.
    assert ":checked" in qss


def test_tone_buttons_paint_each_state_from_tokens():
    cases = (
        (tokens.SUCCESS, tokens.SUCCESS_TEXT,
         tokens.SUCCESS_TINT, tokens.SUCCESS_TINT_HOVER),
        (tokens.DANGER, tokens.DANGER,
         tokens.DANGER_TINT, tokens.DANGER_TINT_HOVER),
        (tokens.WARNING, tokens.WARNING,
         tokens.WARNING_TINT, tokens.WARNING_TINT_HOVER),
    )
    for tone, text, rest, hover in cases:
        qss = tokens.tone_button_qss(tone)
        assert f"background: {rest}" in qss
        assert f"background: {hover}" in qss
        assert f"color: {text}" in qss
        assert f"border-color: {text}" in qss, "hover edge repeats the state"


def test_tone_text_clears_contrast_on_its_own_tint():
    """State text sits on its translucent tint over the card, not the card."""
    cases = (
        (tokens.SUCCESS_TEXT, tokens.SUCCESS_TINT, tokens.SUCCESS_TINT_HOVER),
        (tokens.DANGER, tokens.DANGER_TINT, tokens.DANGER_TINT_HOVER),
        (tokens.WARNING, tokens.WARNING_TINT, tokens.WARNING_TINT_HOVER),
    )
    for tone, rest, hover in cases:
        for tint in (rest, hover):
            surface = _composite(tint, tokens.BG_CARD)
            ratio = _contrast(tone, surface)
            assert ratio >= 4.5, (tone, tint, round(ratio, 2))


def test_row_stripes_and_hover_are_quiet_overlays():
    assert tokens.ROW_EVEN.startswith("#")
    assert tokens.ROW_ODD == "transparent"
    assert tokens.ROW_HOVER.startswith("#")
    # Both stripes stay translucent — the panel behind them must show
    # through, otherwise the "calm stripe" becomes a second surface.
    assert tokens.ROW_EVEN.lstrip("#")[0:2] != "ff"
    assert tokens.ROW_HOVER.lstrip("#")[0:2] != "ff"
    assert tokens.ROW_EVEN[:9] != tokens.ROW_HOVER[:9], "hover must lift"


def test_chip_reserves_its_underline_at_rest():
    """Selecting a chip must not move its label by 2px."""
    active = tokens.chip_qss(True)
    inactive = tokens.chip_qss(False)
    for qss in (active, inactive):
        assert f"border-bottom: 2px solid" in qss
        assert f"border-radius: {tokens.RADIUS_SM}px" in qss
    assert f"border-bottom: 2px solid {tokens.ACCENT}" in active
    assert "border-bottom: 2px solid transparent" in inactive
    assert tokens.ACCENT_TINT in active and tokens.ACCENT_TEXT in active
    assert tokens.TEXT_SECONDARY in inactive
    # Hover is shared by both states.
    assert tokens.BG_CARD_HOVER in active and tokens.BG_CARD_HOVER in inactive


def test_chip_text_clears_contrast_in_both_states():
    active_bg = _composite(tokens.ACCENT_TINT, tokens.BG_CARD)
    assert _contrast(tokens.ACCENT_TEXT, active_bg) >= 4.5
    assert _contrast(tokens.TEXT_SECONDARY, tokens.BG_BASE) >= 4.5


# ── Dialog/popup layer: field well, primary action, popup surfaces ──────────

def test_field_well_speaks_in_tokens():
    qss = tokens.field_qss()
    assert tokens.BG_FIELD in qss, "recessed input surface"
    assert tokens.TEXT_PRIMARY in qss
    assert tokens.BORDER_POPOVER in qss
    assert tokens.ACCENT_BORDER in qss, "focus edge"
    assert tokens.TEXT_MUTED in qss, "disabled text"
    assert f"border-radius: {tokens.RADIUS_SM}px" in qss
    assert f"padding: {tokens.SPACE_4}px {tokens.SPACE_8}px" in qss
    # Scope note: spin-box arrows stay style-drawn by decision.
    assert "QDoubleSpinBox::up-button" in qss


def test_field_text_clears_the_contrast_floor():
    for fg in (tokens.TEXT_PRIMARY, tokens.TEXT_SECONDARY, tokens.TEXT_MUTED):
        ratio = _contrast(fg, tokens.BG_FIELD)
        assert ratio >= 4.5, (fg, tokens.BG_FIELD, round(ratio, 2))


def test_primary_button_variant_is_token_based_and_readable():
    qss = tokens.button_qss("primary")
    for color in (tokens.ACCENT_TINT, tokens.ACCENT_BORDER, tokens.ACCENT_TEXT,
                  tokens.BG_CARD_HOVER, tokens.BG_CARD_SELECTED,
                  tokens.TEXT_MUTED):
        assert color in qss
    assert f"border-radius: {tokens.RADIUS_SM}px" in qss
    assert ":hover" in qss and ":pressed" in qss and ":disabled" in qss

    for bg in (tokens.ACCENT_TINT, tokens.BG_CARD_HOVER,
               tokens.BG_CARD_SELECTED):
        ratio = _contrast(tokens.ACCENT_TEXT, bg)
        assert ratio >= 4.5, (tokens.ACCENT_TEXT, bg, round(ratio, 2))


def test_popup_surfaces_are_token_based():
    from ui.popups import combo_view_qss, menu_qss, tooltip_qss

    menu = menu_qss()
    for color in (tokens.BG_POPOVER, tokens.TEXT_PRIMARY,
                  tokens.BORDER_POPOVER, tokens.BG_CARD_HOVER,
                  tokens.TEXT_MUTED):
        assert color in menu, color
    assert f"border-radius: {tokens.RADIUS_MD}px" in menu

    tooltip = tooltip_qss()
    assert tokens.BG_POPOVER in tooltip and tokens.TEXT_PRIMARY in tooltip
    assert tokens.BORDER_POPOVER in tooltip

    combo = combo_view_qss()
    assert tokens.BG_FIELD in combo and tokens.BORDER_POPOVER in combo
