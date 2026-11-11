"""Developer gallery for the Theme Designer widget kit (ui/theme_kit).

Not part of the shipped app: nothing under ``core/`` or ``ui/`` imports this
file. It exists so every kit widget can be compared by eye on Pop!OS and
Windows 11, at the Designer's 300 px panel width and at the 240 px minimum.

Run from the repository root:

    Linux:    venv/bin/python tools/token_gallery.py
    Windows:  venv\\Scripts\\python.exe tools\\token_gallery.py

Headless screenshots (one PNG per page, useful for review):

    QT_QPA_PLATFORM=offscreen venv/bin/python tools/token_gallery.py \
        --shots dev/_gallery_shots

Every page shows the same widgets twice: a 300 px column (Designer right
panel) and a 240 px column (Designer left panel / minimum width). States are
forced where a real hover or focus is impractical: ``hover()`` sets the
painters' internal flag, ``PropertyRow`` states are set through its API, and
each page focuses its first child for the screenshot pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from ui import tokens
from ui.app_style import install as install_app_style
from ui.app_theme import apply_palette
from ui.theme_kit import (
    AnchorPicker, AnchorRow, AnimationDefinition, AnimationPhaseCard,
    Badge, BlockTabBar, BorderEditor, BorderField, BorderSidesBox,
    ChipSelect, ChoiceField, ChoiceOption, ColorField, CompactDropdown,
    ContainerBox, ContainerCanvas, ContainerStrip, Divider, EasingPicker,
    EmptyState, FourSideField, IconButton, InlineMessage, KeyframeEditor,
    NumberField, PaintField, PropertyRow, PropertySection, SampleInjector,
    SampleState, SearchField, SectionLabel, SegmentedToggle, ShadowEditor,
    ShadowField, SliderField, SplitEditor, Switch, TextInput, Timeline,
    ToggleButton, ValidationBadge, ValidationItem, attach_tooltip,
)
from ui.typography import install as install_typography

PALETTE = [
    ("gold", "#D4AF37"),
    ("lime", "#AAFF00"),
    ("white", "#ffffff"),
    ("ink", "rgba(0, 0, 0, 0.6)"),
]
SHARED_SHADOWS = [ChoiceOption("soft", "Soft"), ChoiceOption("ring", "Ring")]
SHARED_BORDERS = [ChoiceOption("gold_frame", "Gold frame"),
                  ChoiceOption("hairline", "Hairline")]
DEFINITIONS = [
    AnimationDefinition("fade_in", "fade_in", "Fade In", 600, 0, "ease-out",
                        "center", "Built-in"),
    AnimationDefinition("fade_up", "fade_up", "Fade Up", 600, 0, "ease-out",
                        "center", "Built-in"),
    AnimationDefinition("scale_up", "scale_up", "Scale Up", 500, 0,
                        "ease-out", "center", "Built-in"),
    AnimationDefinition("slide_up", "slide_up", "Slide Up", 700, 120,
                        "ease-in-out", "bottom", "Shared"),
    AnimationDefinition("typewriter", "typewriter", "Typewriter", 900, 0,
                        "linear", "center", "Built-in", reveal="char"),
    AnimationDefinition("church_slow", "custom", "Church Slow", 1400, 200,
                        "cubic-bezier(0.22, 1, 0.36, 1)", "center", "Library"),
]


# ─── App ───────────────────────────────────────────────────────────────────

def build_app() -> QApplication:
    app = QApplication(["rhemacast-token-gallery"])
    install_app_style(app)
    app.setStyleSheet(tokens.scrollbar_qss())
    install_typography(app)
    apply_palette(app)
    return app


# ─── Helpers ───────────────────────────────────────────────────────────────

def hover(widget: QWidget) -> QWidget:
    """Force the painters' hover state without moving the pointer."""
    for attribute in ("_hover", "_hovered", "_hover_dot"):
        if hasattr(widget, attribute) and isinstance(
                getattr(widget, attribute), bool):
            setattr(widget, attribute, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
    widget.update()
    return widget


def group(title: str, *widgets: QWidget, hint: str = "") -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.SPACE_4)
    layout.addWidget(SectionLabel(title))
    if hint:
        layout.addWidget(InlineMessage(hint, role="muted"))
    for widget in widgets:
        layout.addWidget(widget)
    return box


def field(password: bool = False) -> TextInput:
    control = TextInput("Nunito, sans-serif", placeholder="Font family")
    control.setMinimumWidth(80)
    return control


def _property_rows(narrow: bool) -> QWidget:
    rows = QWidget()
    layout = QVBoxLayout(rows)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.SPACE_4)

    default = PropertyRow("Opacity", SliderField(
        0.84, minimum=0, maximum=1, step=0.01, decimals=2))
    changed = PropertyRow("Letter spacing", NumberField(
        "-0.01em", units=["px", "em"], step=0.1, decimals=2),
        changed=True)
    size_field = NumberField(540, minimum=1, maximum=400, integer=True)
    size_field.set_warning("Clamped to 400 in the preview")
    warning = PropertyRow("Size", size_field,
                          warning="Clamped to 400 in the preview")
    disabled = PropertyRow(
        "Offset X", NumberField("120px", units=["px", "%"]),
        disabled_reason="Ignored when anchor is fill")
    hovered = PropertyRow("Weight", NumberField(700, minimum=100,
                                                maximum=900, step=100,
                                                integer=True))
    hover(hovered)
    full = PropertyRow(
        "Font family",
        CompactDropdown([ChoiceOption(name, name, font_family=name)
                         for name in ("Inter", "Nunito", "DM Sans",
                                      "DejaVu Sans", "Serif")],
                        "Inter", variant="field", preview_font=True),
        full_width=True)

    layout.addWidget(default)
    layout.addWidget(changed)
    layout.addWidget(warning)
    layout.addWidget(disabled)
    layout.addWidget(hovered)
    layout.addWidget(full)
    return rows


def _property_sections(narrow: bool) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.SPACE_8)

    section = PropertySection("Canvas", expanded=True)
    section.add_row(PropertyRow("Width", NumberField(
        1920, minimum=320, maximum=7680, integer=True, suffix="px")))
    section.add_row(PropertyRow("Height", NumberField(
        1080, minimum=240, maximum=4320, integer=True, suffix="px")))
    section.add_row(PropertyRow("Fit", CompactDropdown(
        ["contain", "none"], "contain", variant="field")))
    section.set_changed_count(2)
    layout.addWidget(section)

    collapsed = PropertySection("Advanced", expanded=False)
    collapsed.add_row(PropertyRow("Overflow", CompactDropdown(
        ["hidden", "visible"], "hidden", variant="field")))
    layout.addWidget(collapsed)
    return box


# ─── Pages ─────────────────────────────────────────────────────────────────

def page_rows(narrow: bool) -> QWidget:
    return _two_groups(
        ("Rows · states", _property_rows(narrow), ""),
        ("Sections", _property_sections(narrow), ""),
    )


def _two_groups(*entries: tuple[str, QWidget, str]) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.SPACE_16)
    for title, widget, hint in entries:
        layout.addWidget(group(title, widget, hint=hint))
    return box


def page_numbers(narrow: bool) -> QWidget:
    plain = NumberField(24, minimum=0, maximum=400, integer=True,
                        suffix="px")
    unit = NumberField("24px", minimum=-20, maximum=400, step=0.1,
                       units=["px", "em"], keywords=["auto", "inherit"],
                       label="Letter spacing")
    empty = NumberField(None, minimum=0, maximum=7680, integer=True,
                        nullable=True, placeholder="Auto")
    warned = NumberField(90, minimum=0, maximum=40, integer=True)
    warned.set_warning("Maximum is 40")
    disabled = NumberField(120, minimum=0, maximum=400, integer=True,
                           suffix="px")
    disabled.setEnabled(False)
    hovered = hover(NumberField(600, minimum=0, maximum=5000, integer=True,
                                suffix="ms"))

    slider = SliderField(0.65, minimum=0, maximum=1, step=0.01,
                         default=1.0, decimals=2, label="Opacity")
    slider_hover = hover(SliderField(0.35, minimum=0, maximum=1, step=0.01,
                                     default=1.0, decimals=2))
    slider_disabled = SliderField(0.5, minimum=0, maximum=1, step=0.01)
    slider_disabled.setEnabled(False)

    sides_linked = FourSideField({"padding": 24}, base_key="padding")
    sides_unlinked = FourSideField(
        {"top": 12, "right": 24, "bottom": 12, "left": 4},
        base_key=None, linked=False, unit="px")
    sides_disabled = FourSideField(16, base_key="margin", linked=True)
    sides_disabled.setEnabled(False)

    return _stack(
        group("Number fields", plain, unit, empty, warned, disabled, hovered,
              hint="Drag the field or a PropertyRow label to scrub. "
                   "Shift = coarse, Alt = fine."),
        group("Sliders", slider, slider_hover, slider_disabled,
              hint="The tick marks the caller's default."),
        group("Four sides", sides_linked, sides_unlinked, sides_disabled,
              hint="Linked edits all four; unlinked emits per-side keys."),
    )


def _stack(*widgets: QWidget) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.SPACE_16)
    for widget in widgets:
        layout.addWidget(widget)
    return box


def page_choice(narrow: bool) -> QWidget:
    single = ChipSelect([ChoiceOption("left", "Left"),
                         ChoiceOption("center", "Center"),
                         ChoiceOption("right", "Right"),
                         ChoiceOption("justify", "Justify")], "center")
    multi = ChipSelect([ChoiceOption("blur", "Blur"),
                        ChoiceOption("brightness", "Bright"),
                        ChoiceOption("contrast", "Contrast"),
                        ChoiceOption("saturate", "Saturate"),
                        ChoiceOption("grayscale", "Grayscale")],
                       ["blur", "saturate"], multi=True)
    muted = ChipSelect([ChoiceOption("auto", "Auto", muted=True),
                        ChoiceOption("none", "None", muted=True),
                        ChoiceOption("solid", "Solid"),
                        ChoiceOption("dashed", "Dashed")], "auto")

    segmented = SegmentedToggle(
        [ChoiceOption("left", "L"), ChoiceOption("center", "C"),
         ChoiceOption("right", "R"), ChoiceOption("justify", "J")], "center",
        accessible_name="Text align")
    segmented_disabled = SegmentedToggle(
        [ChoiceOption("top", "Top"), ChoiceOption("middle", "Mid"),
         ChoiceOption("bottom", "Bottom")], "middle")
    segmented_disabled.setEnabled(False)
    bold = ToggleButton(text="B", checked=True, tooltip="Bold",
                        accessible_name="Bold")
    italic = ToggleButton(text="I", tooltip="Italic", accessible_name="Italic")

    dropdown = CompactDropdown(
        [ChoiceOption(name, name, group="Fonts", font_family=name)
         for name in ("Inter", "Nunito", "DM Sans", "DejaVu Sans",
                      "Noto Sans", "Serif", "Monospace", "Cursive")],
        "Inter", variant="field", searchable=True, preview_font=True)
    dropdown_warn = CompactDropdown(["solid", "dashed", "dotted"], "solid",
                                    variant="field")
    dropdown_warn.setEnabled(False)
    dropdown_hover = hover(CompactDropdown(
        [ChoiceOption("linear", "Linear"), ChoiceOption("radial", "Radial")],
        "linear", variant="field"))
    auto_chips = ChoiceField([ChoiceOption("char", "Char"),
                              ChoiceOption("word", "Word")], "char")
    auto_dropdown = ChoiceField([ChoiceOption(str(i), f"Option {i}")
                                 for i in range(12)], "Option 1")

    return _stack(
        group("Chips", single, multi, muted),
        group("Segmented", segmented, segmented_disabled, bold, italic),
        group("Compact dropdown", dropdown, dropdown_warn, dropdown_hover,
              auto_chips, auto_dropdown,
              hint="Type to jump; search appears for long lists."),
    )


def page_colour(narrow: bool) -> QWidget:
    solid = ColorField("#a855f7", palette=PALETTE)
    alpha = ColorField("rgba(168, 85, 247, 0.55)", palette=PALETTE,
                       nullable=True)
    token = ColorField("@gold", palette=PALETTE)
    empty = ColorField(None, palette=PALETTE, nullable=True,
                       placeholder="Not set")
    warned = ColorField("#f87171", palette=PALETTE)
    warned.set_warning("Named colours outside the allowlist are rejected")
    disabled = ColorField("#94a3b8", palette=PALETTE)
    disabled.setEnabled(False)
    hovered = hover(ColorField("#38bdf8", palette=PALETTE))

    paint_solid = PaintField("#22c55e", palette=PALETTE)
    paint_gradient = PaintField(
        "linear-gradient(180deg, #a855f7 0%, rgba(0,0,0,0) 100%)",
        palette=PALETTE, allow_none=True)
    paint_none = PaintField("none", palette=PALETTE, allow_none=True)
    paint_disabled = PaintField("#111827", palette=PALETTE)
    paint_disabled.setEnabled(False)

    return _stack(
        group("ColorField", solid, alpha, token, empty, warned, disabled,
              hovered, hint="Swatch opens the kit picker; @tokens detach."),
        group("PaintField", paint_solid, paint_gradient, paint_none,
              paint_disabled,
              hint="Gradients keep a raw CSS mode for unparseable values."),
    )


def page_anchor(narrow: bool) -> QWidget:
    center = AnchorPicker("center")
    corner = AnchorPicker("top_left")
    fill = AnchorPicker("fill")
    disabled = AnchorPicker("bottom_right")
    disabled.setEnabled(False)
    hovered = hover(AnchorPicker("top"))
    row = AnchorRow({"anchor": "center", "x": "12px", "y": "-8px"},
                    show_offsets=True)

    sides = BorderSidesBox()
    sides.set_state({"top", "left"}, "top")

    return _stack(
        group("Anchor", center, corner, fill, disabled, hovered, row,
              hint="3×3 grid plus Fill; 64 px square."),
        group("Border sides", sides,
              hint="Click an edge to edit its override."),
    )


def page_shadow_border(narrow: bool) -> QWidget:
    shadow_none = ShadowField("none", shared_options=SHARED_SHADOWS,
                              palette=PALETTE)
    shadow_custom = ShadowField(
        "0 24px 48px -12px rgba(0, 0, 0, 0.55)", shared_options=SHARED_SHADOWS,
        palette=PALETTE)
    shadow_shared = ShadowField({"shared": "soft"},
                                shared_options=SHARED_SHADOWS, palette=PALETTE)
    shadow_text = ShadowField(
        "0 4px 12px rgba(0,0,0,0.4)", shared_options=SHARED_SHADOWS,
        palette=PALETTE, allow_shared=False, show_spread=False)

    shadow_editor = ShadowEditor(
        "0 24px 48px -12px rgba(0,0,0,0.55), inset 0 0 0 1px "
        "rgba(255,255,255,0.08)", shared_options=SHARED_SHADOWS,
        palette=PALETTE)
    shadow_editor.setMaximumWidth(380)

    border_none = BorderField("none", shared_options=SHARED_BORDERS,
                              palette=PALETTE)
    border_custom = BorderField(
        {"width": 2, "style": "solid", "color": "@gold", "radius": 18},
        shared_options=SHARED_BORDERS, palette=PALETTE)
    border_shared = BorderField({"shared": "gold_frame"},
                                shared_options=SHARED_BORDERS, palette=PALETTE)

    border_editor = BorderEditor(
        {"width": 2, "style": "dashed", "color": "@gold", "radius": 12,
         "sides": {"top": {"width": 6}, "left": {"color": "#AAFF00"}}},
        shared_options=SHARED_BORDERS, palette=PALETTE)
    border_editor.setMaximumWidth(380)
    border_editor.set_editing_side("top")

    return _stack(
        group("Shadow fields", shadow_none, shadow_custom, shadow_shared,
              shadow_text),
        group("Shadow editor", shadow_editor),
        group("Border fields", border_none, border_custom, border_shared),
        group("Border editor", border_editor),
    )


def page_easing(narrow: bool) -> QWidget:
    standard = EasingPicker("ease-out")
    spring = EasingPicker("spring")
    custom = EasingPicker("cubic-bezier(0.22, 1, 0.36, 1)")
    disabled = EasingPicker("ease-in")
    disabled.setEnabled(False)
    hovered = hover(EasingPicker("linear"))

    frames = [
        {"at": 0, "opacity": 0, "translate_y": 24, "scale": 0.96,
         "blur": 6},
        {"at": 55, "opacity": 1, "translate_y": 0, "scale": 1},
        {"at": 100, "opacity": 1, "scale": 1, "rotate": 0},
    ]
    timeline = Timeline(frames)
    read_only = Timeline(frames, show_editor=False)

    return _stack(
        group("Easing", standard, spring, custom, disabled, hovered,
              hint="Curve thumbnail; popup has presets, bezier and replay."),
        group("Timeline", timeline, read_only,
              hint="2–8 keyframes, endpoints pinned at 0 and 100."),
    )


def page_animation(narrow: bool) -> QWidget:
    off = AnimationPhaseCard("Entry", None, library=DEFINITIONS)
    named = AnimationPhaseCard("Entry", "fade_up", library=DEFINITIONS,
                               expanded=True)
    overrides = AnimationPhaseCard(
        "Entry", {"use": "fade_up", "duration_ms": 900, "delay_ms": 250},
        library=DEFINITIONS, expanded=True)
    inline = AnimationPhaseCard(
        "Entry", {"type": "typewriter", "duration_ms": 900,
                  "reveal": "word",
                  "cursor": {"char": "▌", "color": "@gold",
                             "blink_ms": 450}},
        library=DEFINITIONS, expanded=True)
    out_phase = AnimationPhaseCard(
        "Exit", {"type": "fade_out"}, phase="out", library=DEFINITIONS,
        expanded=True)
    light = AnimationPhaseCard(
        "Transition In", {"use": "slide_up", "delay_ms": 100},
        phase="transition_in", library=DEFINITIONS, light=True)
    light.set_expanded(True)

    return _stack(
        group("Phase cards", off, named, overrides,
              hint="Collapsed line: name, type chip, delay/duration bar, "
                   "switch, replay."),
        group("Typewriter / inline", inline),
        group("Invalid for this slot", out_phase,
              hint="Typewriter is disabled with a reason on out phases."),
        group("Light variant (split)", light),
    )


def page_split(narrow: bool) -> QWidget:
    value = {
        "by": "line",
        "stagger_ms": 70,
        "first": {"entry": {"use": "fade_up", "duration_ms": 400}},
        "rest": {"entry": {"use": "fade_up", "delay_ms": 120}},
        "look": {
            "first": {"color": "@gold", "weight": 700},
            "rest": {"opacity": 0.72, "letter_spacing": "0.02em"},
        },
    }
    editor = SplitEditor(value, library=DEFINITIONS, palette=PALETTE,
                         defaults={"by": "line", "stagger_ms": 70})
    editor.set_readout("3 lines in current sample")
    disabled = SplitEditor(
        None, library=DEFINITIONS, palette=PALETTE,
        disabled_reason="Split is not available on containers")

    return _stack(
        group("Split · lines", editor),
        group("Disabled", disabled,
              hint="The reason is a tooltip; nothing is hidden."),
    )


def page_canvas(narrow: bool) -> QWidget:
    boxes = [
        ContainerBox("main", "Main", 160, 120, 1600, 840, 10),
        ContainerBox("reference", "Reference", 320, 60, 1280, 90, 20),
        ContainerBox("badge", "Badge", 80, 900, 300, 90, 30, visible=False),
        ContainerBox("frame", "Frame", 0, 0, 1920, 1080, 5, fill=True),
    ]
    canvas = ContainerCanvas((1920, 1080), background="#0f0e13")
    canvas.setFixedHeight(250)
    canvas.set_boxes(boxes, "main")
    canvas.set_safe_area_visible(True)

    strip = ContainerStrip(boxes, "main")
    strip.setFixedWidth(280 if not narrow else 220)

    return _stack(
        group("Canvas", canvas,
              hint="Drag to move, handles resize, arrows nudge; "
                   "fill anchors are locked."),
        group("Container strip", strip),
    )


def page_injector(narrow: bool) -> QWidget:
    scripture = SampleInjector([
        SampleState("shortest", "Shortest verse", group="Scripture"),
        SampleState("medium", "Medium verse", group="Scripture"),
        SampleState("longest", "Longest verse", group="Scripture"),
        SampleState("random", "Random verse", kind="shuffle",
                    group="Scripture"),
        SampleState("custom", "Custom text", kind="custom",
                    group="Scripture"),
        SampleState("blank", "Blank", kind="blank", group="Utility"),
    ], "medium")
    freeform = SampleInjector([
        SampleState("short", "Short title + body", group="Freeform"),
        SampleState("long", "Long body", group="Freeform"),
        SampleState("random", "Random sample", kind="shuffle",
                    group="Freeform"),
        SampleState("custom", "Custom text", kind="custom",
                    group="Freeform"),
        SampleState("blank", "Blank", kind="blank", group="Utility"),
    ], "short")
    shuffle = SampleInjector(
        [SampleState("a", "Short verse"), SampleState("b", "Long verse"),
         SampleState("random", "Random verse", kind="shuffle")], "random")
    disabled = SampleInjector(
        [SampleState("a", "Short verse"), SampleState("b", "Long verse")],
        "a")
    disabled.setEnabled(False)

    return _stack(
        group("Scripture samples", scripture,
              hint="Arrows or click advance; hold or the caret opens the list."),
        group("Freeform samples", freeform),
        group("Shuffle + disabled", shuffle, disabled),
    )


def page_small(narrow: bool) -> QWidget:
    search = SearchField("Search properties", delay_ms=150)
    search.set_text("padding")
    search_hover = hover(SearchField("Search fonts"))
    name = TextInput("Dark sanctuary", placeholder="Theme name")
    name.set_state("warning", "A theme with this name already exists")
    slug = TextInput("dark-sanctuary", placeholder="File name")
    slug.set_state("error", "Only letters, numbers, dashes and underscores")
    neutral = TextInput("", placeholder="Author")
    disabled = TextInput("locked", placeholder="Author")
    disabled.setEnabled(False)

    tabs = BlockTabBar([
        ("body", "Body", True, 3),
        ("text", "Text", True, 2),
        ("reference", "Reference", True, 0),
        ("translation", "Translation", False, 1),
        ("verse_num", "Verse #", True, 0),
    ], "text")

    validation = QWidget()
    v_layout = QVBoxLayout(validation)
    v_layout.setContentsMargins(0, 0, 0, 0)
    v_layout.setSpacing(1)
    for severity, message, path in (
            ("error", "animation.entry: unknown slot name", "animation.entry"),
            ("warning", "text.size clamped to 400", "blocks.text.size"),
            ("note", "Unknown key “padding” ignored", "containers[0].padding")):
        v_layout.addWidget(ValidationItem(severity, message, path))
    badge = ValidationBadge("3")
    badge_warn = ValidationBadge("1", severity="error")

    icons = QWidget()
    icon_row = QHBoxLayout(icons)
    icon_row.setContentsMargins(0, 0, 0, 0)
    icon_row.setSpacing(2)
    for glyph in ("plus", "minus", "close", "up", "down", "link", "eye",
                  "lock", "play", "copy", "trash"):
        icon_row.addWidget(IconButton(glyph=glyph, tooltip=glyph,
                                      accessible_name=glyph,
                                      variant="ghost"))
    icon_row.addStretch(1)

    return _stack(
        group("Search", search, search_hover),
        group("Text inputs", name, slug, neutral, disabled),
        group("Block tabs", tabs,
              hint="Dot toggles visibility; badge counts changed fields."),
        group("Validation", validation, badge, badge_warn),
        group("Divider · empty state", Divider(),
              EmptyState("No shared borders", "Create one in borders.json")),
        group("Icon buttons", icons),
        group("Inline messages", InlineMessage("Plain note", "muted"),
              InlineMessage("Amber warning", "warning"),
              InlineMessage("Accent info", "info")),
    )


def page_narrow(narrow: bool) -> QWidget:
    rows = QWidget()
    layout = QVBoxLayout(rows)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.SPACE_4)
    layout.addWidget(PropertyRow("Color", ColorField("#a855f7", palette=PALETTE)))
    layout.addWidget(PropertyRow("Letter spacing", NumberField(
        "0.1em", units=["px", "em"], keywords=["inherit"])))
    layout.addWidget(PropertyRow("Backdrop", ChipSelect(
        [ChoiceOption("blur", "Blur"), ChoiceOption("brightness", "Bright"),
         ChoiceOption("contrast", "Contrast"), ChoiceOption("saturate", "Sat")],
        ["blur"], multi=True)))
    layout.addWidget(PropertyRow("Type", CompactDropdown(
        ["fade_up", "scale_up", "slide_up", "typewriter"], "fade_up",
        variant="field")))
    layout.addWidget(PropertyRow("Scale", SliderField(
        1.0, minimum=0.01, maximum=4, step=0.01, decimals=2)))
    layout.addWidget(PropertyRow("Shadow", ShadowField(
        "0 24px 48px -12px rgba(0,0,0,0.55)", shared_options=SHARED_SHADOWS,
        palette=PALETTE)))
    layout.addWidget(PropertyRow("Border", BorderField(
        {"width": 2, "style": "solid", "color": "@gold", "radius": 18},
        shared_options=SHARED_BORDERS, palette=PALETTE)))
    layout.addWidget(PropertyRow("Anchor", AnchorPicker("center")))
    layout.addWidget(PropertyRow("Sample", SampleInjector([
        SampleState("short", "Shortest verse"),
        SampleState("long", "Longest verse"),
        SampleState("random", "Random", kind="shuffle"),
    ], "short")))
    return _two_groups(
        ("240 px · the hard case", rows,
         "Every control above is at its minimum working width."),
        ("Tabs", BlockTabBar([
            ("body", "Body", True, 3), ("text", "Text", True, 1),
            ("reference", "Ref", True, 0), ("translation", "Trans", False, 0),
            ("verse_num", "Verse #", True, 0),
        ], "body"), ""),
    )


# ─── Gallery window ────────────────────────────────────────────────────────

PAGES = [
    ("Rows", page_rows),
    ("Numbers", page_numbers),
    ("Choice", page_choice),
    ("Colour", page_colour),
    ("Anchor", page_anchor),
    ("Shadow · Border", page_shadow_border),
    ("Easing · Timeline", page_easing),
    ("Animation", page_animation),
    ("Split", page_split),
    ("Canvas", page_canvas),
    ("Sample injector", page_injector),
    ("Small pieces", page_small),
    ("240 px", page_narrow),
]


class Gallery(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RhemaCast — Theme Designer token gallery (dev)")
        self.setDocumentMode(True)
        self.resize(1180, 940)
        self._scrollers: list[QScrollArea] = []
        for title, builder in PAGES:
            self.addTab(self._build_page(builder), title)

    def _build_page(self, builder) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        row = QHBoxLayout(content)
        row.setContentsMargins(tokens.SPACE_16, tokens.SPACE_16,
                               tokens.SPACE_16, tokens.SPACE_16)
        row.setSpacing(tokens.SPACE_16)
        for width, label in ((300, "300 px · Designer panel"),
                             (240, "240 px · minimum")):
            column = QWidget()
            column.setFixedWidth(width)
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(tokens.SPACE_8)
            heading = QLabel(label)
            heading.setStyleSheet(
                f"color: {tokens.TEXT_MUTED};"
                f"font-size: {tokens.TYPE_CAPTION}px;"
                "background: transparent;")
            column_layout.addWidget(heading)
            column_layout.addWidget(builder(width <= 240))
            column_layout.addStretch(1)
            row.addWidget(column)
        row.addStretch(1)
        scroll.setWidget(content)
        self._scrollers.append(scroll)
        return scroll

    def focus_current(self) -> None:
        scroller = self.currentWidget()
        if scroller is None:
            return
        content = scroller.widget()
        content.focusNextChild()
        content.focusNextChild()
        # Tab focus selects the whole field; clear it so the screenshot shows
        # the value rather than a purple selection block.
        focused = QApplication.focusWidget()
        if focused is not None and hasattr(focused, "deselect"):
            focused.deselect()
            focused.setCursorPosition(0)

    def capture(self, directory: Path) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for index, (title, _builder) in enumerate(PAGES):
            self.setCurrentIndex(index)
            QApplication.processEvents()
            self.focus_current()
            QApplication.processEvents()
            name = f"{index + 1:02d}-{title.lower().replace(' · ', '-').replace(' ', '-')}.png"
            path = directory / name
            self.grab().save(str(path))
            saved.append(path)
        return saved


def main(argv: list[str]) -> int:
    app = build_app()
    shots = None
    if "--shots" in argv:
        index = argv.index("--shots")
        shots = Path(argv[index + 1] if index + 1 < len(argv)
                     else "dev/_gallery_shots")
    gallery = Gallery()
    gallery.show()
    if shots is not None:
        QTimer.singleShot(250, lambda: _shoot(app, gallery, shots))
    return app.exec()


def _shoot(app: QApplication, gallery: Gallery, directory: Path) -> None:
    QApplication.processEvents()
    saved = gallery.capture(directory)
    print(f"saved {len(saved)} screenshots to {directory}")
    for path in saved:
        print(" ", path.name)
    app.quit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
