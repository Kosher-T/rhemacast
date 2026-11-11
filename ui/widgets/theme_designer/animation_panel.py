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
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from core import animation_registry as registry
from core import theme_schema as schema
from core.theme_shared import load_family
from ui.theme_kit import (
    AnimationDefinition, AnimationPhaseCard, ChoiceOption, CompactDropdown,
    IconButton, InlineMessage, PropertyRow, Timeline,
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
    ("transition_out", "Transition out"),
    ("out", "Exit"),
)

#: The card already edits these on every phase; repeating them in the form was
#: the Stage 3 real-display duplicate-rows defect. Keyframes belong to Timeline.
CARD_OWNED_PARAMS = ("duration_ms", "delay_ms", "easing", "origin",
                     "keyframes")


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: Optional[ThemeDocument] = None
        self._theme: dict = {}
        self._loading = False
        self._cards: dict[str, AnimationPhaseCard] = {}
        self._palette = _palette()
        self._container_id = ""
        self._block = ""

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
        if phase in ("entry", "out"):
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
        if phase in ("entry", "out"):
            return base + (phase,)
        key = "in" if phase == "transition_in" else "out"
        return base + ("transition", key)

    def _write_slot(self, phase: str, value: Any) -> None:
        document = self._document
        if document is None or self._container() is None:
            return
        animation = copy.deepcopy(self._target_animation() or {})
        if phase in ("entry", "out"):
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
        if phase in ("entry", "out"):
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
        labels = {
            "body": "Body", "text": "Text", "reference": "Reference",
            "title": "Title", "translation": "Translation",
            "verse_num": "Verse number",
        }
        options = [ChoiceOption("", "Container")]
        for block in schema.BLOCK_IDS.get(kind, ()):
            options.append(ChoiceOption(block, labels.get(block, block.title())))
        return options

    def _sync_target(self) -> None:
        options = self._target_options()
        values = {option.value for option in options}
        if self._block not in values:
            self._block = ""
        self._target.set_options(options, value=self._block)
        self._target.setEnabled(self._container() is not None)
        self._target_row.setEnabled(self._container() is not None)

    def _on_target_changed(self, value: Any) -> None:
        self._block = str(value or "")
        self._rebuild()

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
        self._sync_target()
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
