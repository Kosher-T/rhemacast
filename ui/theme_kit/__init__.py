"""ui/theme_kit

Reusable, property-agnostic widgets for the Theme Designer rebuild.

Stage 1 only: this package is not imported by the shipped Designer yet. The
developer gallery (``tools/token_gallery.py``) shows every widget in every
state on Linux and Windows.

Modules are grouped by widget family; ``base`` holds the shared option
dataclasses and painting helpers, ``popup`` owns every floating surface
(dropdown, colour picker, tooltip), and ``flow`` holds the wrapping layout.
"""

from ui.theme_kit.anchor_picker import ANCHOR_GRID, ANCHORS, AnchorPicker, AnchorRow
from ui.theme_kit.backdrop_field import BackdropField
from ui.theme_kit.animation_phase import (
    INLINE_TYPES, ORIGINS, AnimationDefinition, AnimationPhaseCard,
    resolve_slot, slot_mode,
)
from ui.theme_kit.base import (
    ChoiceOption, SampleState, checkerboard, coerce_option, coerce_options,
    draw_check, draw_chevron, elide, font, format_number,
)
from ui.theme_kit.border_editor import (
    BORDER_STYLES, SIDES, BorderEditor, BorderField, BorderSidesBox,
    border_summary, parse_border,
)
from ui.theme_kit.chip_select import ChipSelect, ChoiceField
from ui.theme_kit.color_field import ColorEditor, ColorField, parse_css_color
from ui.theme_kit.container_canvas import (
    ContainerBox, ContainerCanvas, ContainerStrip,
)
from ui.theme_kit.dropdown import CompactDropdown
from ui.theme_kit.easing_picker import (
    EASING_CURVES, PRESETS, EasingPicker, easing_label, parse_easing,
)
from ui.theme_kit.flow import FlowLayout, FlowRow
from ui.theme_kit.four_side import FourSideField
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.paint_field import (
    GradientEditor, GradientSpec, GradientStop, PaintField, format_gradient,
    parse_gradient,
)
from ui.theme_kit.param_group import SUB_INDENT, ParamGroup
from ui.theme_kit.popup import PopupSurface, attach_tooltip
from ui.theme_kit.property_row import PropertyRow, PropertySection
from ui.theme_kit.sample_injector import SampleInjector
from ui.theme_kit.segmented import SegmentedToggle, ToggleButton
from ui.theme_kit.shadow_editor import (
    ShadowEditor, ShadowField, ShadowLayer, format_shadow, parse_shadow,
    shadow_summary,
)
from ui.theme_kit.slider_field import SliderField
from ui.theme_kit.small import (
    Badge, BlockTabBar, Divider, EmptyState, IconButton, InlineMessage,
    SearchField, SectionLabel, TextInput, ValidationBadge, ValidationItem,
)
from ui.theme_kit.split_editor import SplitEditor
from ui.theme_kit.switch import Switch
from ui.theme_kit.timeline import KeyframeEditor, Timeline

__all__ = [
    "ANCHOR_GRID", "ANCHORS", "AnchorPicker", "AnchorRow",
    "BackdropField",
    "INLINE_TYPES", "ORIGINS", "AnimationDefinition", "AnimationPhaseCard",
    "resolve_slot", "slot_mode",
    "ChoiceOption", "SampleState", "checkerboard", "coerce_option",
    "coerce_options", "draw_check", "draw_chevron", "elide", "font",
    "format_number",
    "BORDER_STYLES", "SIDES", "BorderEditor", "BorderField", "BorderSidesBox",
    "border_summary", "parse_border",
    "ChipSelect", "ChoiceField",
    "ColorEditor", "ColorField", "parse_css_color",
    "ContainerBox", "ContainerCanvas", "ContainerStrip",
    "CompactDropdown",
    "EASING_CURVES", "PRESETS", "EasingPicker", "easing_label",
    "parse_easing",
    "FlowLayout", "FlowRow", "FourSideField", "NumberField",
    "GradientEditor", "GradientSpec", "GradientStop", "PaintField",
    "format_gradient", "parse_gradient",
    "ParamGroup", "SUB_INDENT",
    "PopupSurface", "attach_tooltip",
    "PropertyRow", "PropertySection", "SampleInjector",
    "SegmentedToggle", "ToggleButton",
    "ShadowEditor", "ShadowField", "ShadowLayer", "format_shadow",
    "parse_shadow", "shadow_summary",
    "SliderField",
    "Badge", "BlockTabBar", "Divider", "EmptyState", "IconButton",
    "InlineMessage", "SearchField", "SectionLabel", "TextInput",
    "ValidationBadge", "ValidationItem",
    "SplitEditor", "Switch", "KeyframeEditor", "Timeline",
]
