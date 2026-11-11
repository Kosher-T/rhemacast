"""Theme Designer preview-manager state machine (no WebEngine)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from ui.theme_kit.preview_manager import PreviewManager, phase_for_paths
from ui.widgets.theme_designer.animation_panel import AnimationPanel
from ui.widgets.theme_designer.document import ThemeDocument


def _theme() -> dict:
    return {
        "schema_version": 2,
        "kind": "scripture",
        "animations": {
            "fade_up": {"type": "fade_up", "duration_ms": 200},
            "fade_out": {"type": "fade_out", "duration_ms": 200},
            "wipe": {"type": "wipe", "duration_ms": 200},
        },
        "containers": [{
            "id": "main",
            "animation": {
                "entry": "fade_up",
                "transition": {"in": "wipe", "out": "fade_out"},
                "out": "fade_out",
            },
            "blocks": {
                "text": {"animation": {"entry": "fade_up"}},
            },
        }],
    }


class FakePreview:
    def __init__(self):
        self.calls: list[tuple] = []

    def apply_theme(self, theme, *, sample_id=None):
        self.calls.append(("load", sample_id))

    def apply_theme_in_place(self, theme):
        self.calls.append(("in-place",))

    def show_sample(self, sample_id, theme):
        self.calls.append(("sample", sample_id))

    def replay_phase(self, phase):
        self.calls.append(("replay", phase))


_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


@pytest.fixture
def manager(qapp):
    preview = FakePreview()
    manager = PreviewManager(preview, None, debounce_ms=15, loop_ms=40)
    # Offscreen QApplication reports ApplicationInactive; the real app is
    # active while its window has focus.
    manager.set_active(True)
    manager.load_theme(_theme(), "medium")
    yield manager, preview
    manager.shutdown()


def _replays(preview: FakePreview) -> list[str]:
    return [call[1] for call in preview.calls if call[0] == "replay"]


def test_phase_for_paths_maps_each_animation_kind():
    theme = _theme()
    assert phase_for_paths(
        (("containers", 0, "animation", "entry"),), theme) == "entry"
    assert phase_for_paths(
        (("containers", 0, "animation", "transition", "in"),), theme
    ) == "transition_in"
    assert phase_for_paths(
        (("containers", 0, "blocks", "text", "animation", "out"),), theme
    ) == "out"
    assert phase_for_paths(
        (("containers", 0, "blocks", "text", "animation", "split", "by"),),
        theme) == "entry"
    assert phase_for_paths(
        (("containers", 0, "blocks", "text", "font_family"),), theme) is None
    assert phase_for_paths((("animations", "wipe", "duration_ms"),), theme
                           ) == "transition_in"


def test_block_target_writes_block_animation_not_container(qapp):
    document = ThemeDocument(_theme())
    panel = AnimationPanel()
    panel.bind_document(document)
    panel._target.set_value("text", emit=True)
    panel._write_slot("entry", "fade_up")

    assert document.get(("containers", 0, "blocks", "text", "animation",
                         "entry")) == "fade_up"
    assert document.get(("containers", 0, "animation")) == {
        "entry": "fade_up",
        "transition": {"in": "wipe", "out": "fade_out"},
        "out": "fade_out",
    }
    panel.deleteLater()


def test_phase_card_replay_routes_to_manager(qapp):
    document = ThemeDocument(_theme())
    panel = AnimationPanel()
    panel.bind_document(document)
    seen = []
    panel.replay_requested.connect(seen.append)
    panel.card("entry").replay.emit("fade_up")
    assert seen == ["entry"]
    panel.deleteLater()


def test_style_edit_updates_in_place_without_replay(manager):
    manager, preview = manager
    manager._set_focus_inside(True)
    manager.update_theme(_theme(), (
        ("containers", 0, "blocks", "text", "font_family"),))
    QTest.qWait(40)
    assert ("in-place",) in preview.calls
    assert _replays(preview) == []


def test_animation_edit_debounces_then_replays_once(manager):
    manager, preview = manager
    manager.update_theme(_theme(), (
        ("containers", 0, "animation", "entry"),))
    manager.update_theme(_theme(), (
        ("containers", 0, "animation", "entry", "duration_ms"),))
    QTest.qWait(8)
    assert _replays(preview) == []
    QTest.qWait(30)
    assert _replays(preview) == ["entry"]


def test_focus_loop_repeats_and_blur_stops_it(manager):
    manager, preview = manager
    manager._set_focus_inside(True)
    manager.update_theme(_theme(), (
        ("containers", 0, "animation", "entry"),))
    # debounce (15 ms) + at least two 40 ms loop ticks with scheduling slack
    QTest.qWait(120)
    assert len(_replays(preview)) >= 2
    manager._set_focus_inside(False)
    before = len(_replays(preview))
    QTest.qWait(80)
    assert len(_replays(preview)) == before


def test_hidden_preview_pauses_and_resumes_loop(manager):
    manager, preview = manager
    manager._set_focus_inside(True)
    manager.update_theme(_theme(), (
        ("containers", 0, "animation", "entry"),))
    QTest.qWait(50)
    manager.set_visible(False)
    before = len(_replays(preview))
    QTest.qWait(80)
    assert len(_replays(preview)) == before
    manager.set_visible(True)
    QTest.qWait(80)
    assert len(_replays(preview)) > before


def test_inactive_window_pauses_loop(manager):
    manager, preview = manager
    manager._set_focus_inside(True)
    manager.update_theme(_theme(), (
        ("containers", 0, "animation", "entry"),))
    QTest.qWait(50)
    manager.set_active(False)
    before = len(_replays(preview))
    QTest.qWait(80)
    assert len(_replays(preview)) == before


def test_sample_swap_stops_replay_loop(manager):
    manager, preview = manager
    manager._set_focus_inside(True)
    manager.update_theme(_theme(), (
        ("containers", 0, "animation", "entry"),))
    QTest.qWait(50)
    manager.set_sample("longest", _theme())
    assert ("sample", "longest") in preview.calls
    before = len(_replays(preview))
    QTest.qWait(80)
    assert len(_replays(preview)) == before


def test_shutdown_stops_every_timer(manager):
    manager, preview = manager
    manager._set_focus_inside(True)
    manager.update_theme(_theme(), (
        ("containers", 0, "animation", "entry"),))
    QTest.qWait(50)
    manager.shutdown()
    before = len(_replays(preview))
    QTest.qWait(80)
    assert len(_replays(preview)) == before
