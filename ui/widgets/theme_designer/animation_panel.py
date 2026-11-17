"""Stage 3 animation panel: phase cards with embedded ParamForm/Timeline.

Each of the four phases is an `AnimationPhaseCard`. Its editor area hosts a
registry-driven `ParamForm` for the animation behind the slot: an inline
definition is edited in place; a theme library entry is edited in
`theme["animations"]`; shared/built-in entries are read-only until copied.
`custom` also hosts a `Timeline` for its keyframes.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QScrollArea, QVBoxLayout, QWidget,
)

from core import animation_registry as registry
from core import theme_schema as schema
from core.constants import (
    OVERLAP_IN_OFFSET_MAX_MS,
    OVERLAP_IN_OFFSET_MIN_MS,
    OVERLAP_IN_OFFSET_MS,
)
from core.motion_state import DEFAULT_MOTION
from core.theme_shared import load_family
from ui.theme_kit import (
    AnimationDefinition, AnimationPhaseCard, ChoiceOption, CompactDropdown,
    IconButton, InlineMessage, NumberField, PropertyRow, PropertySection,
    ShadowField, SplitEditor, Timeline,
)
from ui.widgets.theme_designer.document import ThemeDocument
from ui.widgets.theme_designer.param_form import ParamForm

def palette_pairs() -> list[tuple[str, str]]:
    return _palette()


def definitions_for(
        theme: dict,
) -> tuple[list[AnimationDefinition], list[AnimationDefinition]]:
    """Theme/shared definitions and registry builtins for pickers."""
    local = []
    animations = theme.get("animations") if isinstance(theme, dict) else None
    if isinstance(animations, dict):
        for name, raw in animations.items():
            if isinstance(raw, dict):
                definition = _definition(str(name), raw, "theme")
                if definition is not None:
                    local.append(definition)
    shared = load_family("animations") or {}
    shared = shared.get("animations") if isinstance(shared, dict) else {}
    if isinstance(shared, dict):
        for name, raw in shared.items():
            if isinstance(raw, dict):
                definition = _definition(str(name), raw, "shared")
                if definition is not None:
                    local.append(definition)
    builtins = []
    for name, raw in registry.default_definitions().items():
        definition = _definition(name, raw, "builtin")
        if definition is not None:
            builtins.append(definition)
    return local, builtins


PHASES = (
    ("entry", "Entry"),
    ("transition_in", "Transition in"),
    ("sustain", "Sustain"),
    ("transition_out", "Transition out"),
    ("out", "Exit"),
)

#: The card already edits these on every phase; repeating them in the form was
#: the Stage 3 real-display duplicate-rows defect. Keyframes belong to Timeline.
CARD_OWNED_PARAMS = ("duration_ms", "delay_ms", "easing", "origin",
                     "keyframes")

#: Blocks whose animation the renderer actually plays. ``_animationTargets``
#: in display.js covers body, text, reference and translation; freeform's
#: ``title`` block is folded into the reference element there. Verse number is
#: never read, so the panel explains it instead of offering dead cards.
RENDERED_BLOCKS = ("body", "text", "reference", "translation")
#: Container property targets. Their values are reserved dropdown ids, not
#: block ids; selecting one edits a property track instead of a phase slot.
BORDER_TARGET = "@border"
SHADOW_TARGET = "@shadow"
PROPERTY_TARGETS = {
    BORDER_TARGET: "border.draw",
    SHADOW_TARGET: "shadow.bloom",
}
PROPERTY_TARGET_LABELS = {
    BORDER_TARGET: "Border",
    SHADOW_TARGET: "Shadow",
}
TRACK_PHASE_VALUES = tuple(value for value, _label in PHASES)
PROPERTY_PHASES = PHASES
BORDER_DIRECTIONS = (
    ("clockwise", "Clockwise"),
    ("counterclockwise", "Counterclockwise"),
    ("start:top", "Start top"),
    ("start:right", "Start right"),
    ("start:bottom", "Start bottom"),
    ("start:left", "Start left"),
    ("start:top counterclockwise", "Start top, counterclockwise"),
    ("start:right counterclockwise", "Start right, counterclockwise"),
    ("start:bottom counterclockwise", "Start bottom, counterclockwise"),
    ("start:left counterclockwise", "Start left, counterclockwise"),
)
BORDER_DIRECTION_VALUES = tuple(value for value, _label in BORDER_DIRECTIONS)
TRACK_TIMING_DEFAULTS = {
    "duration_ms": 600,
    "delay_ms": 0,
    "easing": "ease-out",
}
#: Split is laid out only for the text-bearing elements (display.js
#: ``_layoutSplitUnits``). Container and body splits are accepted by the
#: schema but never produce units.
SPLIT_BLOCKS = ("text", "reference", "title", "translation")

BLOCK_LABELS = {
    "body": "Body", "text": "Text", "reference": "Reference",
    "title": "Title", "translation": "Translation",
    "verse_num": "Verse number",
}

#: Theme-level motion keys, their labels and option labels. The values and
#: defaults are the schema's, not a second table: ``schema`` imports them
#: from ``core.motion_state`` and this panel only chooses display labels.
MOTION_ROWS = (
    ("in_out", "In / out", (
        ("sequential", "Sequential"),
        ("overlap", "Overlap"),
    )),
    ("transition", "Transition", (
        ("sequential", "Sequential"),
        ("overlap", "Overlap"),
    )),
    ("deck_steps", "Deck steps", (
        ("out_in", "OUT then IN"),
        ("instant", "Instant in one deck"),
    )),
    ("sustain_when_cloaked", "While cloaked", (
        ("pause", "Pause sustain"),
        ("run", "Keep sustain running"),
    )),
)

MOTION_DEFAULTS = dict(DEFAULT_MOTION)
MOTION_VALUES = {key: tuple(value for value, _label in options)
                 for key, _label, options in MOTION_ROWS}


def _palette() -> list[tuple[str, str]]:
    family = load_family("palettes") or {}
    colors = family.get("colors") if isinstance(family, dict) else {}
    if not isinstance(colors, dict):
        return []
    return [(str(k), str(v)) for k, v in colors.items()
            if isinstance(v, str) and not v.startswith("@")]


def _definition(name: str, raw: dict, source: str) -> Optional[AnimationDefinition]:
    typ = raw.get("type")
    spec = registry.ANIMATION_SPECS.get(typ)
    if spec is None:
        return None
    param = spec.param
    return AnimationDefinition(
        name=name, type=typ,
        label=str(raw.get("label") or spec.label),
        duration_ms=int(raw.get("duration_ms") or param("duration_ms").default),
        delay_ms=int(raw.get("delay_ms") or 0),
        easing=str(raw.get("easing") or param("easing").default),
        origin=str(raw.get("origin") or "center"),
        reveal=str(raw.get("reveal") or ""),
        cursor=raw.get("cursor"),
        raw=dict(raw), source=source,
    )


class AnimationPanel(QWidget):
    """Phase cards for the selected container or block target."""

    theme_changed = pyqtSignal(dict)
    replay_requested = pyqtSignal(str)
    #: Request only: the tab keeps the single selection and tells the left
    #: Blocks section to follow this target.
    block_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: Optional[ThemeDocument] = None
        self._theme: dict = {}
        self._loading = False
        self._cards: dict[str, AnimationPhaseCard] = {}
        self._palette = _palette()
        self._container_id = ""
        self._block = ""
        self._property_target = ""
        self._property_section: Optional[PropertySection] = None
        self._property_controls: dict[str, QWidget] = {}
        self._split_editor: Optional[SplitEditor] = None
        self._motion_controls: dict[str, CompactDropdown] = {}
        self._motion_offset: Optional[NumberField] = None
        self._motion_note: Optional[InlineMessage] = None
        self._motion_section: Optional[PropertySection] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._target = CompactDropdown(self._target_options(), "", parent=self)
        self._target.changed.connect(self._on_target_changed)
        self._target_row = PropertyRow("Edit", self._target, label_width=36)
        root.addWidget(self._target_row)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._host = QWidget(self._scroll)
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, 1)

    # ── public ──────────────────────────────────────────────────────────────
    def bind_document(self, document: ThemeDocument) -> None:
        """Share the tab's document; this panel only renders and requests edits."""
        if self._document is document:
            self._refresh_from_document()
            return
        if self._document is not None:
            try:
                self._document.changed.disconnect(self._on_document_changed)
                self._document.replaced.disconnect(self._on_document_replaced)
            except (TypeError, RuntimeError):
                pass
        self._document = document
        document.changed.connect(self._on_document_changed)
        document.replaced.connect(self._on_document_replaced)
        self._refresh_from_document()

    def load_theme(self, theme: dict) -> None:
        """Standalone load (tests); the tab uses ``bind_document`` instead."""
        if self._document is None:
            self.bind_document(ThemeDocument(theme))
            return
        self._loading = True
        try:
            self._document.replace(
                theme if isinstance(theme, dict) else {}, source=self)
            self._refresh_from_document()
        finally:
            self._loading = False

    def _refresh_from_document(self) -> None:
        self._theme = (self._document.snapshot()
                       if self._document is not None else {})
        containers = self._theme.get("containers")
        ids = [str(c.get("id", "")) for c in containers
               if isinstance(c, dict)] if isinstance(containers, list) else []
        if self._container_id not in ids:
            self._container_id = ids[0] if ids else ""
        self._rebuild()

    def _on_document_changed(self, paths, source) -> None:
        if source is self:
            return
        for path in paths or ():
            if not isinstance(path, tuple):
                continue
            if path == ("containers",) or path[:1] == ("animations",):
                self._refresh_from_document()
                return
            if path[:1] == ("motion",):
                self._sync_motion()
                return
            if "animation" in path:
                self._refresh_from_document()
                return

    def _on_document_replaced(self, source) -> None:
        if self._loading:
            return
        self._refresh_from_document()

    def theme(self) -> dict:
        if self._document is not None:
            return self._document.snapshot()
        return copy.deepcopy(self._theme)

    def card(self, phase: str) -> Optional[AnimationPhaseCard]:
        return self._cards.get(str(phase))

    def motion_control(self, key: str) -> Optional[CompactDropdown]:
        """The dropdown editing one theme-level motion key (tests/automation)."""
        return self._motion_controls.get(str(key))

    def motion_offset_field(self) -> Optional[NumberField]:
        """The field editing motion.overlap_in_offset_ms."""
        return self._motion_offset

    def _motion(self) -> dict:
        raw = self._theme.get("motion")
        motion = dict(MOTION_DEFAULTS)
        if isinstance(raw, dict):
            for key, allowed in MOTION_VALUES.items():
                value = raw.get(key)
                if value in allowed:
                    motion[key] = value
            offset = raw.get("overlap_in_offset_ms")
            if not isinstance(offset, bool):
                try:
                    offset = int(offset)
                except (TypeError, ValueError):
                    offset = None
                if offset is not None:
                    motion["overlap_in_offset_ms"] = max(
                        OVERLAP_IN_OFFSET_MIN_MS,
                        min(OVERLAP_IN_OFFSET_MAX_MS, offset))
        return motion

    # ── document access ─────────────────────────────────────────────────────
    def set_container(self, container_id: str) -> None:
        """Select the container whose animation slots this panel edits."""
        containers = self._theme.get("containers")
        ids = [str(c.get("id", "")) for c in containers
               if isinstance(c, dict)] if isinstance(containers, list) else []
        if container_id not in ids:
            container_id = ids[0] if ids else ""
        if container_id == self._container_id:
            return
        self._container_id = container_id
        self._rebuild()

    def set_block(self, block: str) -> None:
        """Follow the tab's block selection without emitting it back."""
        block = str(block or "")
        values = {option.value for option in self._target_options()}
        if block not in values:
            return
        if block == self._block and not self._property_target:
            return
        self._property_target = ""
        self._block = block
        self._rebuild()

    def _container_index(self) -> int:
        containers = self._theme.get("containers")
        if not isinstance(containers, list):
            return -1
        for index, container in enumerate(containers):
            if not isinstance(container, dict):
                continue
            if not self._container_id or str(container.get("id", "")) == self._container_id:
                return index
        return -1

    def _container(self) -> Optional[dict]:
        index = self._container_index()
        containers = self._theme.get("containers")
        if isinstance(containers, list) and 0 <= index < len(containers):
            return containers[index] if isinstance(containers[index], dict) else None
        return None

    def _target_animation(self) -> Optional[dict]:
        container = self._container()
        if container is None:
            return None
        if self._block:
            blocks = container.get("blocks")
            block = blocks.get(self._block) if isinstance(blocks, dict) else None
            animation = block.get("animation") if isinstance(block, dict) else None
        else:
            animation = container.get("animation")
        return animation if isinstance(animation, dict) else None

    def _slot(self, phase: str) -> Any:
        animation = self._target_animation() or {}
        if phase in ("entry", "sustain", "out"):
            return animation.get(phase, "none")
        transition = animation.get("transition")
        if isinstance(transition, dict):
            return transition.get("in" if phase == "transition_in" else "out", "none")
        return "none"

    def _animation_path(self) -> tuple:
        index = max(0, self._container_index())
        if self._block:
            return ("containers", index, "blocks", self._block, "animation")
        return ("containers", index, "animation")

    def _slot_path(self, phase: str) -> tuple:
        base = self._animation_path()
        if phase in ("entry", "sustain", "out"):
            return base + (phase,)
        key = "in" if phase == "transition_in" else "out"
        return base + ("transition", key)

    def _write_slot(self, phase: str, value: Any) -> None:
        document = self._document
        if document is None or self._container() is None:
            return
        animation = copy.deepcopy(self._target_animation() or {})
        if phase in ("entry", "sustain", "out"):
            if value in (None, "none", ""):
                animation.pop(phase, None)
            else:
                animation[phase] = copy.deepcopy(value)
        else:
            key = "in" if phase == "transition_in" else "out"
            transition = animation.get("transition")
            if not isinstance(transition, dict):
                transition = {}
            if value in (None, "none", ""):
                transition.pop(key, None)
            else:
                transition[key] = copy.deepcopy(value)
            if transition:
                animation["transition"] = transition
            else:
                animation.pop("transition", None)
        base = self._animation_path()
        target_exists = self._target_animation() is not None
        if phase in ("entry", "sustain", "out"):
            slot_path = base + (phase,)
            new_value = (None if value in (None, "none", "")
                         else copy.deepcopy(value))
        else:
            key = "in" if phase == "transition_in" else "out"
            slot_path = base + ("transition", key)
            new_value = (None if value in (None, "none", "")
                         else copy.deepcopy(value))
        # The leaf path is what lets the preview manager identify the exact
        # phase.  Write it before the parent so ThemeDocument records the
        # leaf even when the parent ends up carrying the same value.  A new
        # target needs an empty parent first and, when the edited value is
        # cleared again, a final cleanup write.
        edits = []
        if not target_exists:
            edits.append((base, {}))
        edits.append((slot_path, new_value))
        if not animation:
            edits.append((base, None))
        elif not target_exists:
            edits.append((base, animation))
        document.set_many(edits, source=self)
        self._theme = document.snapshot()

    def _target_options(self) -> list[ChoiceOption]:
        kind = self._theme.get("kind") if isinstance(self._theme, dict) else None
        if kind not in schema.KINDS:
            kind = (schema.FREEFORM if isinstance(self._theme.get("slide"), dict)
                    else schema.SCRIPTURE)
        options = [ChoiceOption("", "Container")]
        if self._container() is not None and not self._block:
            for target, label in PROPERTY_TARGET_LABELS.items():
                options.append(ChoiceOption(target, label))
        for block in schema.BLOCK_IDS.get(kind, ()):
            options.append(ChoiceOption(
                block, BLOCK_LABELS.get(block, block.title())))
        return options

    def _target_value(self) -> str:
        return self._property_target or self._block

    def _sync_target(self) -> None:
        options = self._target_options()
        values = {option.value for option in options}
        if self._property_target not in values:
            self._property_target = ""
        if self._block not in values:
            self._block = ""
        self._target.set_options(options, value=self._target_value())
        self._target.setEnabled(self._container() is not None)
        self._target_row.setEnabled(self._container() is not None)

    def _on_target_changed(self, value: Any) -> None:
        target = str(value or "")
        if target in PROPERTY_TARGETS:
            if target == self._property_target:
                return
            self._property_target = target
            self._block = ""
            self._rebuild()
            return
        if target == self._block and not self._property_target:
            return
        self._property_target = ""
        self._block = target
        self._rebuild()
        if not self._loading:
            self.block_selected.emit(target)

    def _emit(self) -> None:
        if not self._loading:
            self.theme_changed.emit(copy.deepcopy(self._theme))

    # ── build ───────────────────────────────────────────────────────────────
    def _library(self) -> tuple[list[AnimationDefinition], list[AnimationDefinition]]:
        return definitions_for(self._theme)

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._cards = {}
        self._motion_controls = {}
        self._motion_offset = None
        self._property_section = None
        self._property_controls = {}
        self._split_editor = None
        self._sync_target()
        if self._block and self._block not in RENDERED_BLOCKS \
                and self._block != "title":
            self._layout.addWidget(InlineMessage(
                f"{BLOCK_LABELS.get(self._block, self._block)} is not "
                "animated: the renderer never reads its animation slots.",
                "muted"))
            self._layout.addStretch(1)
            return
        self._layout.addWidget(self._build_motion_section())
        if self._property_target:
            self._layout.addWidget(self._build_property_section())
            self._layout.addStretch(1)
            return
        self._layout.addWidget(self._build_split_section())
        library, builtins = self._library()
        duration = registry.SLOT_PARAMS["duration_ms"]
        delay = registry.SLOT_PARAMS["delay_ms"]
        for phase, title in PHASES:
            card = AnimationPhaseCard(
                title, self._slot(phase), phase=phase,
                library=library, builtins=builtins,
                duration_range=(duration.minimum, duration.maximum),
                delay_range=(delay.minimum, delay.maximum),
                easing_presets=list(registry.ANIMATION_EASINGS),
                origin_options=registry.ORIGIN_VALUES,
                palette=self._palette,
                off_value="none", off_label="None",
                expanded=(phase == "entry"),
            )
            card.changed.connect(
                lambda value, p=phase: self._on_slot_changed(p, value))
            card.replay.connect(
                lambda _v, p=phase: self.replay_requested.emit(p))
            self._layout.addWidget(card)
            self._cards[phase] = card
            self._refresh_editor(phase)
        self._layout.addStretch(1)
        if self._container() is None:
            note = InlineMessage(
                "This theme has no v2 container; animations are read-only.",
                "warning")
            self._layout.addWidget(note)

    # ── container property tracks ───────────────────────────────────────────
    def _property_track_id(self) -> str:
        return PROPERTY_TARGETS.get(self._property_target, "")

    def _property_track(self) -> Optional[dict]:
        animation = self._target_animation()
        properties = animation.get("properties") if isinstance(animation, dict) else None
        track = (properties.get(self._property_track_id())
                 if isinstance(properties, dict) else None)
        return copy.deepcopy(track) if isinstance(track, dict) else None

    def _track_phase(self, track: Optional[dict]) -> str:
        phase = track.get("phase") if isinstance(track, dict) else None
        return phase if phase in TRACK_PHASE_VALUES else "entry"

    def _track_defaults(self, track: Optional[dict]) -> dict:
        out = copy.deepcopy(track) if isinstance(track, dict) else {}
        out["phase"] = self._track_phase(out)
        for key, default in TRACK_TIMING_DEFAULTS.items():
            if key not in out:
                out[key] = default
        if self._property_target == BORDER_TARGET:
            direction = out.get("direction")
            if isinstance(direction, str):
                direction = direction.strip().lower().replace(
                    "counter-clockwise", "counterclockwise")
                if direction.endswith(" clockwise"):
                    direction = direction[:-len(" clockwise")]
            if direction not in BORDER_DIRECTION_VALUES:
                direction = "clockwise"
            out["direction"] = direction
            out.setdefault("from", 0)
            out.setdefault("to", 1)
        return out

    def _build_property_section(self) -> PropertySection:
        track = self._track_defaults(self._property_track())
        track_id = self._property_track_id()
        title = ("Border draw" if track_id == "border.draw"
                 else "Shadow bloom")
        section = PropertySection(title, expanded=True)
        self._property_section = section
        self._property_controls = {}

        phase = CompactDropdown(
            [ChoiceOption(value, label) for value, label in PROPERTY_PHASES],
            track.get("phase"), parent=section)
        phase.changed.connect(
            lambda value: self._on_track_changed("phase", value))
        section.add_row(PropertyRow("Phase", phase, label_width=86))
        self._property_controls["phase"] = phase

        if track_id == "border.draw":
            direction = CompactDropdown(
                [ChoiceOption(value, label) for value, label in BORDER_DIRECTIONS],
                track.get("direction"), parent=section)
            direction.changed.connect(
                lambda value: self._on_track_changed("direction", value))
            section.add_row(PropertyRow("Direction", direction, label_width=86))
            self._property_controls["direction"] = direction

            speed = NumberField(
                track.get("speed") if isinstance(track.get("speed"), (int, float))
                and not isinstance(track.get("speed"), bool) else 0,
                minimum=0, maximum=5000, step=10, integer=True,
                suffix="px/s", label="Speed, 0 uses duration", parent=section)
            speed.changed.connect(self._on_track_speed_changed)
            section.add_row(PropertyRow("Speed", speed, label_width=86))
            self._property_controls["speed"] = speed

            from_field = self._track_number(
                track.get("from"), 0, section, "From", "Draw start")
            to_field = self._track_number(
                track.get("to"), 1, section, "To", "Draw end")
            from_field.changed.connect(
                lambda value: self._on_track_changed("from", value))
            to_field.changed.connect(
                lambda value: self._on_track_changed("to", value))
            self._property_controls["from"] = from_field
            self._property_controls["to"] = to_field
        else:
            from_field = self._track_shadow(
                track.get("from"), section, "From shadow")
            to_field = self._track_shadow(
                track.get("to"), section, "To shadow")
            from_field.changed.connect(
                lambda value: self._on_track_changed("from", value))
            to_field.changed.connect(
                lambda value: self._on_track_changed("to", value))
            self._property_controls["from"] = from_field
            self._property_controls["to"] = to_field

        duration = NumberField(
            track.get("duration_ms"), minimum=0, maximum=5000, step=10,
            integer=True, suffix="ms", label="Duration", parent=section)
        duration.changed.connect(
            lambda value: self._on_track_changed("duration_ms", value))
        section.add_row(PropertyRow("Duration", duration, label_width=86))
        self._property_controls["duration_ms"] = duration

        delay = NumberField(
            track.get("delay_ms"), minimum=0, maximum=5000, step=10,
            integer=True, suffix="ms", label="Delay", parent=section)
        delay.changed.connect(
            lambda value: self._on_track_changed("delay_ms", value))
        section.add_row(PropertyRow("Delay", delay, label_width=86))
        self._property_controls["delay_ms"] = delay

        easing = CompactDropdown(
            [ChoiceOption(value, value.replace("-", " ").title())
             for value in registry.ANIMATION_EASINGS],
            track.get("easing"), parent=section)
        easing.changed.connect(
            lambda value: self._on_track_changed("easing", value))
        section.add_row(PropertyRow("Easing", easing, label_width=86))
        self._property_controls["easing"] = easing

        if track_id == "border.draw":
            note = "Speed overrides duration; 0 uses the duration above."
        else:
            note = "Shadow bloom is saved here; the renderer does not play it yet."
        section.add_widget(InlineMessage(note, "muted"))

        row = QWidget(section)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        clear = IconButton(
            text="Remove track",
            tooltip=f"Remove the {title.lower()} track",
            accessible_name=f"Remove {title} track", parent=row)
        clear.setEnabled(self._property_track() is not None)
        clear.clicked.connect(lambda _checked=False: self._remove_track())
        layout.addWidget(clear)
        section.add_widget(row)
        return section

    def _track_number(self, value: Any, fallback: float,
                      section: PropertySection, label: str,
                      accessible: str) -> NumberField:
        number = value if isinstance(value, (int, float)) \
            and not isinstance(value, bool) else fallback
        field = NumberField(
            number, minimum=0, maximum=1, step=0.05, decimals=2,
            label=accessible, parent=section)
        section.add_row(PropertyRow(label, field, label_width=86))
        return field

    def _track_shadow(self, value: Any, section: PropertySection,
                      label: str) -> ShadowField:
        initial = value if isinstance(value, (str, dict)) else "none"
        field = ShadowField(
            initial, palette=self._palette, allow_shared=False,
            max_layers=4, structured=True, parent=section)
        section.add_row(PropertyRow(label, field, label_width=86))
        return field

    def _on_track_speed_changed(self, value: Any) -> None:
        try:
            speed = float(value)
        except (TypeError, ValueError):
            return
        if speed <= 0:
            if self._property_track() is not None:
                self._on_track_changed("speed", None)
        else:
            self._on_track_changed("speed", min(5000.0, max(10.0, speed)))

    def _on_track_changed(self, key: str, value: Any) -> None:
        if self._loading or self._document is None or not self._property_target:
            return
        if key in ("from", "to") and self._property_target == BORDER_TARGET:
            try:
                value = min(1.0, max(0.0, float(value)))
            except (TypeError, ValueError):
                return
        self._write_track({key: value})

    def _write_track(self, updates: Optional[dict] = None, *,
                     remove: bool = False) -> None:
        document = self._document
        track_id = self._property_track_id()
        if document is None or not track_id or self._container() is None:
            return
        base = self._animation_path()
        animation_exists = self._target_animation() is not None
        animation = copy.deepcopy(self._target_animation() or {})
        properties = animation.get("properties")
        properties_exists = isinstance(properties, dict)
        properties = copy.deepcopy(properties) if properties_exists else {}
        current = properties.get(track_id)
        current = copy.deepcopy(current) if isinstance(current, dict) else {}
        if remove:
            properties.pop(track_id, None)
        else:
            current = self._track_defaults(current)
            for key, value in (updates or {}).items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = copy.deepcopy(value)
            properties[track_id] = current
        if properties:
            animation["properties"] = properties
        else:
            animation.pop("properties", None)
        properties_path = base + ("properties",)
        track_path = properties_path + (track_id,)
        edits: list[tuple[tuple, Any]] = []
        if not animation_exists:
            edits.append((base, {}))
        if properties and not properties_exists:
            edits.append((properties_path, {}))
        edits.append((track_path, None if remove else copy.deepcopy(
            properties.get(track_id))))
        if not properties:
            edits.append((properties_path, None))
        if not animation:
            edits.append((base, None))
        document.set_many(edits, source=self)
        self._theme = document.snapshot()
        self._emit()

    def _remove_track(self) -> None:
        if self._loading or self._document is None:
            return
        self._write_track(remove=True)
        self._rebuild()

    # ── split ───────────────────────────────────────────────────────────────
    def _build_split_section(self) -> QWidget:
        """Split editor for text-bearing blocks; a note for everything else."""
        if self._block not in SPLIT_BLOCKS:
            return InlineMessage(
                "Split applies to text, reference and translation.", "muted")
        animation = self._target_animation() or {}
        split = animation.get("split")
        library, builtins = self._library()
        editor = SplitEditor(
            split if isinstance(split, dict) else None,
            library=library, builtins=builtins, palette=self._palette,
            defaults=schema.split_defaults(),
            unit_labels=("First line", "Rest"), parent=self._host)
        editor.changed.connect(self._on_split_changed)
        self._split_editor = editor
        section = PropertySection("Split", expanded=isinstance(split, dict))
        section.add_widget(editor)
        return section

    def _on_split_changed(self, value: Any) -> None:
        if self._loading or self._document is None:
            return
        animation = copy.deepcopy(self._target_animation() or {})
        base = self._animation_path()
        edits = []
        if isinstance(value, dict):
            unknown = {}
            current = animation.get("split")
            if isinstance(current, dict):
                unknown = {key: item for key, item in current.items()
                           if key not in ("by", "stagger_ms", "first", "rest",
                                          "look")}
            animation["split"] = {**unknown, **copy.deepcopy(value)}
            edits.append((base + ("split",), animation["split"]))
        else:
            if "split" not in animation:
                return
            animation.pop("split", None)
            edits.append((base + ("split",), None))
        if not animation:
            edits.append((base, None))
        self._document.set_many(edits, source=self)
        self._theme = self._document.snapshot()
        self._emit()

    # ── theme motion ────────────────────────────────────────────────────────
    def _build_motion_section(self) -> PropertySection:
        section = PropertySection("Motion")
        self._motion_section = section
        values = self._motion()
        for key, label, options in MOTION_ROWS:
            dropdown = CompactDropdown(
                [ChoiceOption(value, text) for value, text in options],
                values.get(key), parent=section)
            dropdown.changed.connect(
                lambda value, k=key: self._on_motion_changed(k, value))
            row = PropertyRow(label, dropdown, label_width=86)
            section.add_row(row)
            self._motion_controls[key] = dropdown
        self._motion_offset = NumberField(
            values.get("overlap_in_offset_ms", OVERLAP_IN_OFFSET_MS),
            minimum=OVERLAP_IN_OFFSET_MIN_MS,
            maximum=OVERLAP_IN_OFFSET_MAX_MS,
            step=10, integer=True, suffix="ms",
            label="Overlap incoming offset", parent=section)
        self._motion_offset.changed.connect(
            self._on_motion_offset_changed)
        section.add_row(PropertyRow(
            "In offset", self._motion_offset, label_width=86))
        self._motion_note = InlineMessage("", "muted")
        self._motion_note.setVisible(False)
        section.add_widget(self._motion_note)
        self._update_motion_note()
        return section

    def _sync_motion(self) -> None:
        if not self._motion_controls:
            return
        values = self._motion()
        for key, dropdown in self._motion_controls.items():
            dropdown.set_value(values.get(key), emit=False)
        if self._motion_offset is not None:
            self._motion_offset.set_value(
                values.get("overlap_in_offset_ms", OVERLAP_IN_OFFSET_MS),
                emit=False)
        self._update_motion_note()

    def _update_motion_note(self) -> None:
        if self._motion_note is None:
            return
        values = self._motion()
        overlap = [key for key in ("in_out", "transition")
                   if values.get(key) == "overlap"]
        if overlap:
            labels = {"in_out": "In / out", "transition": "Transition"}
            names = " and ".join(labels[key] for key in overlap)
            offset = values.get("overlap_in_offset_ms",
                                OVERLAP_IN_OFFSET_MS)
            self._motion_note.setText(
                f"{names}: outgoing starts at 0 ms, incoming starts "
                f"{offset} ms later and stacks above it.")
            self._motion_note.set_role("info")
            self._motion_note.setVisible(True)
        else:
            self._motion_note.setVisible(False)

    def _on_motion_changed(self, key: str, value: Any) -> None:
        if self._loading or self._document is None:
            return
        if not isinstance(value, str) or not value:
            return
        self._document.set(("motion", key), value, source=self)
        self._theme = self._document.snapshot()
        self._update_motion_note()
        self._emit()

    def _on_motion_offset_changed(self, value: Any) -> None:
        if self._loading or self._document is None:
            return
        try:
            offset = int(value)
        except (TypeError, ValueError):
            return
        offset = max(OVERLAP_IN_OFFSET_MIN_MS,
                     min(OVERLAP_IN_OFFSET_MAX_MS, offset))
        self._document.set(
            ("motion", "overlap_in_offset_ms"), offset, source=self)
        self._theme = self._document.snapshot()
        self._update_motion_note()
        self._emit()

    # ── editors ─────────────────────────────────────────────────────────────
    def _editor_target(self, phase: str) -> tuple[str, Optional[dict], str]:
        """(type, writable target, reason when read-only)."""
        slot = self._slot(phase)
        if isinstance(slot, dict) and "type" in slot:
            return str(slot["type"]), slot, ""
        if isinstance(slot, dict) and "use" in slot:
            name = str(slot["use"])
        elif isinstance(slot, str) and slot not in ("", "none"):
            name = slot
        else:
            return "", None, ""
        local = self._theme.get("animations")
        target = local.get(name) if isinstance(local, dict) else None
        if isinstance(target, dict):
            return str(target.get("type") or ""), target, ""
        definition = self._definition_named(name)
        typ = definition.type if definition else ""
        return typ, None, "Built-in or shared animation — copy it into the theme to edit."

    def _definition_named(self, name: str) -> Optional[AnimationDefinition]:
        library, builtins = self._library()
        for definition in library + builtins:
            if definition.name == name:
                return definition
        return None

    def _refresh_editor(self, phase: str) -> None:
        card = self._cards.get(phase)
        if card is None:
            return
        typ, target, reason = self._editor_target(phase)
        if not typ:
            card.set_editor_widget(None)
            return
        editor = QWidget(card)
        layout = QVBoxLayout(editor)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(6)
        if reason:
            layout.addWidget(InlineMessage(reason, "muted"))
            copy = IconButton(
                text="Copy into theme",
                tooltip="Copy this definition into theme animations so it can be edited",
                accessible_name=f"Copy {typ} animation into the theme",
                parent=editor)
            copy.clicked.connect(
                lambda _checked=False, p=phase: self._copy_to_theme(p))
            layout.addWidget(copy, 0, Qt.AlignmentFlag.AlignLeft)
        else:
            editable = self._editable_params(typ)
            if editable:
                form = ParamForm(typ, target, palette=self._palette,
                                 exclude=CARD_OWNED_PARAMS, parent=editor)
                form.changed.connect(
                    lambda values, p=phase: self._on_params_changed(p, values))
                layout.addWidget(form)
            if typ == "custom" and isinstance(target, dict):
                timeline = Timeline(
                    target.get("keyframes") or [], minimum=2, maximum=8,
                    show_editor=True, parent=editor)
                timeline.changed.connect(
                    lambda frames, p=phase: self._on_frames_changed(p, frames))
                layout.addWidget(timeline)
            elif not editable:
                layout.addWidget(InlineMessage(
                    "Stored in theme animations; the rows above edit this slot.",
                    "muted"))
        card.set_editor_widget(editor)

    @staticmethod
    def _editable_params(typ: str) -> list:
        spec = registry.ANIMATION_SPECS.get(typ)
        if spec is None:
            return []
        return [param for param in spec.params
                if param.key not in CARD_OWNED_PARAMS]

    def _copy_to_theme(self, phase: str) -> None:
        """Copy a shared/built-in definition into ``theme["animations"]``."""
        document = self._document
        if document is None:
            return
        slot = copy.deepcopy(self._slot(phase))
        name = slot.get("use") if isinstance(slot, dict) else slot
        if not isinstance(name, str):
            return
        definition = self._definition_named(name)
        if definition is None:
            return
        animations = copy.deepcopy(document.get(("animations",)))
        if not isinstance(animations, dict):
            animations = {}
        target = name
        if target in animations:
            suffix = 2
            while f"{name}_copy{suffix if suffix > 2 else ''}" in animations:
                suffix += 1
            target = f"{name}_copy" if suffix == 2 else f"{name}_copy{suffix}"
        raw = copy.deepcopy(definition.raw)
        raw["type"] = definition.type
        animations[target] = raw
        if isinstance(slot, dict):
            slot["use"] = target
            new_slot = slot
        else:
            new_slot = target
        document.set_many([
            (("animations",), animations),
            (self._slot_path(phase), new_slot),
        ], source=self)
        self._theme = document.snapshot()
        self._refresh_editor(phase)
        self._emit()

    def _on_slot_changed(self, phase: str, value: Any) -> None:
        if self._loading:
            return
        self._write_slot(phase, value)
        self._refresh_editor(phase)
        self._emit()

    def _write_target(self, phase: str, values: dict) -> None:
        document = self._document
        if document is None:
            return
        slot = copy.deepcopy(self._slot(phase))
        if isinstance(slot, dict) and "type" in slot and "use" not in slot:
            slot.update(values)
            document.set(self._slot_path(phase), slot, source=self)
            self._theme = document.snapshot()
            return
        name = slot.get("use") if isinstance(slot, dict) else slot
        if not isinstance(name, str):
            return
        target = copy.deepcopy(document.get(("animations", name)))
        if isinstance(target, dict):
            target.update(values)
            document.set(("animations", name), target, source=self)
            self._theme = document.snapshot()

    def _on_params_changed(self, phase: str, values: dict) -> None:
        if self._loading:
            return
        self._write_target(phase, values)
        self._emit()

    def _on_frames_changed(self, phase: str, frames: list) -> None:
        if self._loading:
            return
        document = self._document
        if document is None:
            return
        slot = copy.deepcopy(self._slot(phase))
        if isinstance(slot, dict) and "type" in slot and "use" not in slot:
            slot["keyframes"] = copy.deepcopy(frames)
            document.set(self._slot_path(phase), slot, source=self)
        else:
            name = slot.get("use") if isinstance(slot, dict) else slot
            target = (copy.deepcopy(document.get(("animations", name)))
                      if isinstance(name, str) else None)
            if isinstance(target, dict):
                target["keyframes"] = copy.deepcopy(frames)
                document.set(("animations", name), target, source=self)
        self._theme = document.snapshot()
        self._emit()
