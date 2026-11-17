"""Designer fixes for hidden controls and the freeform show-title toggle."""

import copy
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt6.QtWidgets import QApplication

from core.theme_schema import normalize_theme

_EDITORS = []
_QAPP = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication(["test"])
    return _QAPP


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    for editor in _EDITORS:
        try:
            editor.deleteLater()
        except RuntimeError:
            pass
    _EDITORS.clear()


def _editor(theme):
    from ui.widgets.theme_designer import ThemePropertyEditor

    editor = ThemePropertyEditor()
    _EDITORS.append(editor)
    editor.load_theme(theme)
    return editor


def _scripture_theme():
    return {
        "schema_version": 2,
        "name": "hidden-values",
        "kind": "scripture",
        "canvas": {"width": 1920, "height": 1080,
                   "background": "transparent", "fit": "contain"},
        "containers": [{
            "id": "main", "kind": "freeform", "visible": True,
            "position": {"anchor": "center", "x": 0, "y": 0},
            "width": 1200, "height": 600,
            "blocks": {
                "body": {"visible": False},
                "text": {"visible": True, "size": 40},
                "verse_num": {
                    "visible": True, "mode": "inline",
                    "position": "below_verse", "size": "0.6em",
                },
            },
        }],
    }


def _freeform_theme(show_title=None):
    theme = {
        "schema_version": 2,
        "name": "slide-probe",
        "kind": "freeform",
        "canvas": {"width": 1920, "height": 1080},
        "containers": [{
            "id": "main", "visible": True,
            "blocks": {"title": {"visible": True}, "text": {"visible": True}},
        }],
    }
    if show_title is not None:
        theme["slide"] = {"show_title": show_title}
    return theme


def test_hidden_controls_keep_their_values_through_edit_and_reload(qapp):
    editor = _editor(_scripture_theme())
    editor._pages.set_value("container")
    container_paths = editor.field_paths()
    assert "containers.0.kind" not in container_paths
    assert "containers.0.label" in container_paths

    editor._pages.set_value("blocks")
    editor._on_block("body")
    assert "containers.0.blocks.body.visible" not in editor.field_paths()
    editor._on_block("verse_num")
    assert "containers.0.blocks.verse_num.position" not in editor.field_paths()

    editor.set_field("canvas.width", 1600)
    before = editor.get_theme()
    assert before["containers"][0]["kind"] == "freeform"
    assert before["containers"][0]["blocks"]["body"]["visible"] is False
    assert before["containers"][0]["blocks"]["verse_num"]["position"] == "below_verse"

    resolved, report = normalize_theme(copy.deepcopy(before), kind="scripture")
    assert not report.errors, report.errors
    after = _editor(resolved).get_theme()
    assert after["containers"][0]["kind"] == "freeform"
    assert after["containers"][0]["blocks"]["body"]["visible"] is False
    assert after["containers"][0]["blocks"]["verse_num"]["position"] == "below_verse"
    assert after["canvas"]["width"] == 1600


def test_show_title_toggle_does_not_write_an_absent_key_until_changed(qapp):
    editor = _editor(_freeform_theme())
    assert editor._show_title_switch.value() is True
    assert "slide" not in editor.get_theme()

    editor._show_title_switch.set_value(False, emit=True)
    assert editor.get_theme()["slide"] == {"show_title": False}


def test_show_title_toggle_reads_and_round_trips_a_stored_value(qapp):
    editor = _editor(_freeform_theme(show_title=False))
    assert editor._show_title_switch.value() is False

    editor._show_title_switch.set_value(True, emit=True)
    saved = editor.get_theme()
    assert saved["slide"]["show_title"] is True

    resolved, report = normalize_theme(copy.deepcopy(saved), kind="freeform")
    assert not report.errors, report.errors
    reloaded = _editor(resolved)
    assert reloaded._show_title_switch.value() is True
    assert reloaded.get_theme()["slide"]["show_title"] is True


def test_show_title_toggle_is_absent_for_scripture(qapp):
    editor = _editor(_scripture_theme())
    assert not hasattr(editor, "_show_title_switch")
