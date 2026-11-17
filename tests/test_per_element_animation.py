"""Per-element animation: selection-driven targets, paths and split editing.

The renderer animates container, body, text, reference (freeform title) and
translation; verse number is never read. These tests keep the panel aligned
with that list and prove edits land on the selected element's path.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from core import theme_schema as schema  # noqa: E402
from ui.theme_kit import BlockTabBar  # noqa: E402
from ui.widgets.theme_designer.animation_panel import (  # noqa: E402
    BORDER_TARGET, RENDERED_BLOCKS, SHADOW_TARGET, AnimationPanel,
)
from ui.widgets.theme_designer.document import ThemeDocument  # noqa: E402
from ui.widgets.theme_designer.property_editor import (  # noqa: E402
    ThemePropertyEditor,
)

_QAPP = None

_ROOT = Path(__file__).resolve().parent.parent
SHIPPED = sorted(
    (kind, path.stem, path)
    for kind in ("scripture", "freeform")
    for path in (_ROOT / "themes" / kind).glob("*.json")
)
PHASES = {"entry", "sustain", "transition_in", "transition_out", "out"}


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def _theme() -> dict:
    return {
        "schema_version": 2,
        "kind": "scripture",
        "name": "Per element",
        "unknown_top": {"keep": True},
        "canvas": {"width": 1920, "height": 1080},
        "containers": [
            {
                "id": "main",
                "label": "Main",
                "unknown_container": 1,
                "animation": {
                    "entry": {"use": "fade_in"},
                    "sustain": {"use": "fade_in"},
                    "out": {"use": "fade_out"},
                    "transition": {"in": {"use": "fade_up"}},
                },
                "blocks": {
                    "body": {"animation": {"entry": {"use": "fade_in"}}},
                    "text": {
                        "unknown_block": 2,
                        "animation": {
                            "entry": {"use": "fade_up"},
                            "split": {
                                "by": "line", "stagger_ms": 70,
                                "future": 1,
                            },
                        },
                    },
                    "reference": {"animation": {"entry": {"use": "fade_in"}}},
                    "translation": {
                        "animation": {"entry": {"use": "fade_in"}},
                    },
                    "verse_num": {"animation": {"entry": {"use": "fade_in"}}},
                },
            },
            {
                "id": "aside",
                "blocks": {
                    "text": {"animation": {"entry": {"use": "fade_down"}}},
                    "reference": {
                        "animation": {"entry": {"use": "fade_down"}},
                    },
                },
            },
        ],
    }


def _pair(qapp, theme=None):
    document = ThemeDocument(theme or _theme())
    editor = ThemePropertyEditor()
    panel = AnimationPanel()
    editor.bind_document(document)
    panel.bind_document(document)
    # The same two connections the tab makes.
    editor.block_selected.connect(panel.set_block)
    panel.block_selected.connect(editor.set_selected_block)
    editor._pages.set_value("blocks")
    editor._on_page("blocks")
    qapp.processEvents()
    return document, editor, panel


def test_left_blocks_tab_drives_animation_panel(qapp):
    document, editor, panel = _pair(qapp)
    bar = editor.findChild(BlockTabBar)
    assert bar is not None
    bar.set_current("reference", emit=True)
    qapp.processEvents()
    assert panel._block == "reference"
    assert panel._animation_path() == (
        "containers", 0, "blocks", "reference", "animation")
    assert panel._slot("entry") == {"use": "fade_in"}


def test_panel_target_drives_left_blocks_section(qapp):
    document, editor, panel = _pair(qapp)
    panel._on_target_changed("body")
    qapp.processEvents()
    assert editor.selected_block() == "body"
    assert editor._page() == "blocks"
    bar = editor.findChild(BlockTabBar)
    assert bar is not None and bar.current() == "body"


def test_every_rendered_block_offers_all_five_phases(qapp):
    document, editor, panel = _pair(qapp)
    for block in RENDERED_BLOCKS:
        panel.set_block(block)
        assert set(panel._cards) == PHASES, block
        panel._write_slot("entry", {"use": "fade_up"})
        assert document.get((
            "containers", 0, "blocks", block, "animation", "entry")) == {
                "use": "fade_up"}


def test_second_container_edits_land_on_its_own_path(qapp):
    document, editor, panel = _pair(qapp)
    panel.set_container("aside")
    assert panel._animation_path() == ("containers", 1, "animation")
    panel._write_slot("entry", {"use": "fade_up"})
    assert document.get(("containers", 1, "animation", "entry")) == {
        "use": "fade_up"}
    panel.set_block("reference")
    panel._write_slot("transition_in", {"use": "fade_down"})
    assert document.get((
        "containers", 1, "blocks", "reference", "animation",
        "transition", "in")) == {"use": "fade_down"}


def test_border_and_shadow_targets_only_offer_on_the_container(qapp):
    document, editor, panel = _pair(qapp)
    values = [option.value for option in panel._target_options()]
    assert BORDER_TARGET in values and SHADOW_TARGET in values
    labels = {option.value: option.label for option in panel._target_options()}
    assert labels[BORDER_TARGET] == "Border"
    assert labels[SHADOW_TARGET] == "Shadow"

    panel.set_block("text")
    values = [option.value for option in panel._target_options()]
    assert BORDER_TARGET not in values and SHADOW_TARGET not in values

    panel.set_block("")
    values = [option.value for option in panel._target_options()]
    assert BORDER_TARGET in values and SHADOW_TARGET in values


def test_border_target_writes_a_container_property_track(qapp):
    document, editor, panel = _pair(qapp)
    panel._on_target_changed(BORDER_TARGET)
    assert panel._property_target == BORDER_TARGET
    assert panel._animation_path() == ("containers", 0, "animation")
    assert panel._property_section is not None

    panel._on_track_changed("phase", "transition_in")
    panel._on_track_changed("direction", "start:left counterclockwise")
    panel._on_track_speed_changed(400)
    panel._on_track_changed("from", 0.25)

    track = document.get((
        "containers", 0, "animation", "properties", "border.draw"))
    assert track["phase"] == "transition_in"
    assert track["direction"] == "start:left counterclockwise"
    assert track["speed"] == 400

    panel._on_track_speed_changed(2)
    track = document.get((
        "containers", 0, "animation", "properties", "border.draw"))
    assert track["speed"] == 10
    panel._on_track_speed_changed(0)
    track = document.get((
        "containers", 0, "animation", "properties", "border.draw"))
    assert "speed" not in track
    assert track["from"] == 0.25
    assert track["to"] == 1
    assert track["duration_ms"] == 600
    assert document.get((
        "containers", 0, "animation", "entry")) == {"use": "fade_in"}


def test_shadow_target_writes_shadow_bloom_and_keeps_border(qapp):
    document, editor, panel = _pair(qapp)
    panel._on_target_changed(BORDER_TARGET)
    panel._on_track_changed("speed", 500)
    panel._on_target_changed(SHADOW_TARGET)
    panel._on_track_changed("phase", "entry")
    panel._on_track_changed("from", "0 2px 0 #00000000")
    panel._on_track_changed("to", "0 18px 40px #00000066")

    properties = document.get((
        "containers", 0, "animation", "properties"))
    assert properties["border.draw"]["speed"] == 500
    shadow = properties["shadow.bloom"]
    assert shadow["phase"] == "entry"
    assert shadow["from"] == "0 2px 0 #00000000"
    assert shadow["to"] == "0 18px 40px #00000066"

    resolved, report = schema.normalize_theme(
        copy.deepcopy(document.snapshot()), kind="scripture", name="tracks")
    assert not report.errors
    saved = resolved["containers"][0]["animation"]["properties"]
    assert saved["shadow.bloom"]["to"] == "0 18px 40px #00000066"
    assert saved["border.draw"]["speed"] == 500


def test_property_track_creates_and_cleans_the_animation_parent(qapp):
    document, editor, panel = _pair(qapp)
    panel.set_container("aside")
    panel._on_target_changed(BORDER_TARGET)
    panel._on_track_changed("speed", 300)
    animation = document.get(("containers", 1, "animation"))
    assert animation["properties"]["border.draw"]["speed"] == 300

    panel._remove_track()
    assert document.get(("containers", 1, "animation")) is None


def test_removing_one_track_keeps_the_other_and_the_slots(qapp):
    document, editor, panel = _pair(qapp)
    panel._on_target_changed(BORDER_TARGET)
    panel._on_track_changed("speed", 500)
    panel._on_target_changed(SHADOW_TARGET)
    panel._on_track_changed("from", "0 2px 0 #00000000")
    panel._on_target_changed(BORDER_TARGET)
    panel._remove_track()

    animation = document.get(("containers", 0, "animation"))
    assert "border.draw" not in animation["properties"]
    assert "shadow.bloom" in animation["properties"]
    assert animation["entry"] == {"use": "fade_in"}


def test_border_direction_is_canonicalized_without_losing_the_start(qapp):
    document, editor, panel = _pair(qapp)
    document.set((
        "containers", 0, "animation", "properties", "border.draw"), {
            "phase": "entry", "direction": "start:top clockwise",
        })
    panel._on_target_changed(BORDER_TARGET)
    panel._on_track_changed("delay_ms", 50)
    track = document.get((
        "containers", 0, "animation", "properties", "border.draw"))
    assert track["direction"] == "start:top"
    assert track["delay_ms"] == 50


def test_track_edits_preserve_unknown_track_keys(qapp):
    document, editor, panel = _pair(qapp)
    document.set((
        "containers", 0, "animation", "properties", "border.draw"), {
            "phase": "entry", "direction": "clockwise", "future": 1,
        })
    panel._on_target_changed(BORDER_TARGET)
    panel._on_track_changed("speed", 900)
    track = document.get((
        "containers", 0, "animation", "properties", "border.draw"))
    assert track["future"] == 1
    assert track["speed"] == 900


def test_verse_number_explains_why_there_are_no_cards(qapp):
    document, editor, panel = _pair(qapp)
    panel.set_block("verse_num")
    assert panel._cards == {}
    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert any("Verse number is not animated" in text for text in texts)


def test_split_editor_writes_to_the_selected_block(qapp):
    document, editor, panel = _pair(qapp)
    panel.set_block("text")
    assert panel._split_editor is not None
    panel._on_split_changed({
        "by": "word", "stagger_ms": 90,
        "first": {"entry": {"use": "fade_in"}},
    })
    split = document.get((
        "containers", 0, "blocks", "text", "animation", "split"))
    assert split["by"] == "word"
    assert split["future"] == 1
    assert split["first"]["entry"]["use"] == "fade_in"
    assert document.get((
        "containers", 0, "blocks", "text", "animation", "entry")) == {
            "use": "fade_up"}

    panel._on_split_changed(None)
    animation = document.get((
        "containers", 0, "blocks", "text", "animation"))
    assert "split" not in animation
    assert animation["entry"] == {"use": "fade_up"}


def test_split_is_not_offered_on_container_or_body(qapp):
    document, editor, panel = _pair(qapp)
    assert panel._split_editor is None
    panel.set_block("body")
    assert panel._split_editor is None


def test_block_edit_preserves_unknown_keys(qapp):
    document, editor, panel = _pair(qapp)
    panel.set_block("text")
    panel._write_slot("entry", {"use": "fade_down"})
    animation = document.get((
        "containers", 0, "blocks", "text", "animation"))
    assert animation["entry"] == {"use": "fade_down"}
    assert animation["split"]["future"] == 1
    assert document.get(("containers", 0, "blocks", "text"))[
        "unknown_block"] == 2
    assert document.snapshot()["unknown_top"] == {"keep": True}


def _leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _leaves(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{prefix}[{index}]")
    else:
        yield prefix


@pytest.mark.parametrize(
    "kind,name,path", SHIPPED,
    ids=[f"{kind}/{name}" for kind, name, path in SHIPPED])
def test_shipped_theme_per_element_edits_survive_normalize(
        qapp, kind, name, path):
    raw = json.loads(path.read_text())
    document = ThemeDocument(raw)
    panel = AnimationPanel()
    panel.bind_document(document)
    containers = [c for c in document.containers() if isinstance(c, dict)]
    if not containers:
        pytest.skip(f"{name} is a v1 theme with no containers")

    blocks = [block for block in schema.BLOCK_IDS.get(kind, ())
              if block in RENDERED_BLOCKS or block == "title"]
    for container in containers:
        panel.set_container(str(container.get("id", "")))
        for block in blocks:
            panel.set_block(block)
            panel._write_slot("entry", {"use": "fade_up"})

    working = document.snapshot()
    resolved, report = schema.normalize_theme(
        copy.deepcopy(working), kind=kind, name=name)
    assert not report.errors
    by_id = {str(container.get("id", "")): container
             for container in resolved.get("containers") or []
             if isinstance(container, dict)}
    for container in containers:
        saved = by_id[str(container.get("id", ""))]
        for block in blocks:
            entry = saved["blocks"][block]["animation"]["entry"]
            if isinstance(entry, dict):
                assert entry.get("use") == "fade_up", (name, block)
            else:
                assert entry in ("fade_up", "none"), (name, block)


def test_body_edit_round_trips_a_none_animation_tree_byte_identically():
    """No parameter edit may introduce or rewrite an animation value.

    Every slot starts canonical None. Editing an unrelated Body property
    must leave the whole animation subtree byte-identical, including the
    unknown keys the Designer does not understand yet.
    """
    raw = _theme()
    raw["containers"][0]["animation"] = {
        "entry": None, "sustain": None, "out": None,
        "transition": {"in": None, "out": None},
        "future": {"keep": [1, 2]},
    }
    for block in raw["containers"][0]["blocks"].values():
        if isinstance(block, dict):
            block["animation"] = {
                "entry": None, "transition": {"in": None, "out": None},
            }

    document = ThemeDocument(raw)
    before = document.snapshot()["containers"][0]
    document.set(("containers", 0, "blocks", "body", "gap"), 27,
                 source="body")
    after = document.snapshot()["containers"][0]

    assert json.dumps(before["animation"], sort_keys=True) == \
        json.dumps(after["animation"], sort_keys=True)
    for key, block in before["blocks"].items():
        if isinstance(block, dict) and "animation" in block:
            assert json.dumps(block["animation"], sort_keys=True) == \
                json.dumps(after["blocks"][key]["animation"], sort_keys=True)

    resolved, report = schema.normalize_theme(
        document.snapshot(), kind="scripture", name="Per element")
    assert resolved["containers"][0].get("animation", {}) == {
        "future": {"keep": [1, 2]}}
    assert all("animation" not in b for b in
               resolved["containers"][0]["blocks"].values()
               if isinstance(b, dict))
    assert report.warnings == []
