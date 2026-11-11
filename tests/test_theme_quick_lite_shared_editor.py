"""M1-04: Quick Editor and Lite Designer use the shared property editor.

Both popups used to mount the legacy ``ThemePropertiesPanel``. Its collect
path rebuilt reference/translation fonts from its own fallback, so loading
and saving ``default_quiet`` changed both from DM Sans to Nunito. These tests
drive the real popups against the shipped theme with only their QtWebEngine
previews stubbed.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

import core.theme_loader as theme_loader  # noqa: E402
from core import theme_schema as schema  # noqa: E402
from ui.widgets.theme_designer import ThemePropertyEditor  # noqa: E402


# Like the Lite Designer suites, keep every popup referenced. Closing and
# deleting them here destroys the kit's application-wide TooltipManager for
# tests that share this process.
_OPEN_POPUPS = []
_QAPP = None


class _PreviewStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.theme = {}

    def apply_theme(self, theme):
        self.theme = copy.deepcopy(theme)

    def set_verse(self, *_args, **_kwargs):
        pass

    def display_verse(self, *_args, **_kwargs):
        pass


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


@pytest.fixture
def popups(qapp, monkeypatch):
    import ui.widgets.theme_quick_editor as quick_module
    import ui.widgets.lite_designer.lite_designer as lite_module

    monkeypatch.setattr(quick_module, "ThemePreview", _PreviewStub)
    monkeypatch.setattr(lite_module, "ThemePreview", _PreviewStub)
    monkeypatch.setattr(lite_module, "DisplayView", _PreviewStub)

    opened = _OPEN_POPUPS

    def open_quick():
        widget = quick_module.ThemeQuickEditor("default_quiet")
        opened.append(widget)
        return widget

    def open_lite():
        widget = lite_module.LiteDesigner(
            theme_name="default_quiet",
            default_tab="theme",
            freeform_enabled=False,
        )
        opened.append(widget)
        return widget

    yield open_quick, open_lite


def _quiet_fonts(theme):
    resolved, _report = schema.normalize_theme(
        copy.deepcopy(theme), kind=theme.get("kind") or schema.SCRIPTURE,
        name=theme.get("name"))
    blocks = resolved["containers"][0]["blocks"]
    return {
        block: blocks[block]["font_family"]
        for block in ("reference", "translation")
    }


def _quiet_font_families_are_absent(theme):
    blocks = theme["containers"][0]["blocks"]
    return all("font_family" not in blocks[block]
               for block in ("reference", "translation"))


def test_quick_editor_uses_shared_editor_and_preserves_quiet_fonts(popups):
    open_quick, _ = popups
    raw = theme_loader.get_theme("default_quiet")
    expected = {"reference": "'DM Sans', sans-serif",
                "translation": "'DM Sans', sans-serif"}
    assert _quiet_font_families_are_absent(raw)
    assert _quiet_fonts(raw) == expected

    quick = open_quick()
    assert isinstance(quick._props, ThemePropertyEditor)
    loaded = quick._props.get_theme()
    assert _quiet_font_families_are_absent(loaded)
    assert _quiet_fonts(loaded) == expected

    quick._props.set_field("containers.0.blocks.text.size", "50px")

    edited = quick._props.get_theme()
    assert edited["containers"][0]["blocks"]["text"]["size"] == "50px"
    assert _quiet_font_families_are_absent(edited)
    assert _quiet_fonts(edited) == expected
    assert quick._working_theme == edited


def test_lite_theme_page_uses_shared_editor_and_preserves_quiet_fonts(popups):
    _, open_lite = popups
    raw = theme_loader.get_theme("default_quiet")
    expected = {"reference": "'DM Sans', sans-serif",
                "translation": "'DM Sans', sans-serif"}
    assert _quiet_font_families_are_absent(raw)
    assert _quiet_fonts(raw) == expected

    lite = open_lite()
    assert isinstance(lite._props, ThemePropertyEditor)
    loaded = lite._props.get_theme()
    assert _quiet_font_families_are_absent(loaded)
    assert _quiet_fonts(loaded) == expected

    lite._props.set_field("containers.0.blocks.text.size", "50px")

    edited = lite._props.get_theme()
    assert edited["containers"][0]["blocks"]["text"]["size"] == "50px"
    assert _quiet_font_families_are_absent(edited)
    assert _quiet_fonts(edited) == expected
    assert lite._working_theme == edited
