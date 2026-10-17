"""Thin-stroke SVG icon set: every member resolves, parses, and paints."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import pytest

from ui.icons import ICON_PX, apply_button, icon, icon_path

EXPECTED = (
    "align-center", "align-justify", "align-left", "align-right",
    "arrow-down", "arrow-up", "chevron-left", "chevron-right", "close",
    "eraser", "eye-off", "hr-line", "list-bullet", "list-ordered",
    "minus", "pilcrow", "play", "plus", "record", "redo", "spacing",
    "undo",
)


@pytest.fixture()
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


def test_every_expected_icon_exists_and_parses():
    import xml.etree.ElementTree as ET
    for name in EXPECTED:
        path = icon_path(name)
        assert path.endswith(f"{name}.svg"), name
        root = ET.parse(path).getroot()
        assert root.tag.endswith("svg"), name
        assert root.get("viewBox") == "0 0 24 24", name
        assert len(list(root)) > 0, name  # not an empty canvas


def test_unknown_icon_warns_and_stays_empty(qapp, caplog):
    assert icon_path("nope-not-an-icon") == ""
    with caplog.at_level("WARNING"):
        assert icon("nope-not-an-icon").isNull()


def test_icons_paint(qapp):
    for name in EXPECTED:
        ic = icon(name)
        assert not ic.isNull(), name
        px = ic.pixmap(32, 32)
        assert not px.isNull(), name
        img = px.toImage()
        assert img.width() > 0 and img.height() > 0, name


def test_apply_button_standard_size(qapp):
    from PyQt6.QtWidgets import QPushButton
    btn = QPushButton("⌫")
    apply_button(btn, "eraser", tooltip="Clear formatting")
    assert btn.text() == ""
    assert btn.toolTip() == "Clear formatting"
    assert btn.iconSize().width() == ICON_PX
    assert btn.iconSize().height() == ICON_PX
    assert not btn.icon().isNull()


def test_ribbon_pictographs_use_icons(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = FormatRibbon()
    try:
        for attr in ("_btn_undo", "_btn_redo", "_btn_clear", "_size_minus",
                     "_size_plus", "_spacing_btn", "_btn_bullets",
                     "_btn_numbers", "_btn_hr"):
            btn = getattr(r, attr)
            assert btn.text() == "", attr
            assert not btn.icon().isNull(), attr
        for key, btn in r._align_btns.items():
            assert btn.text() == "", key
            assert not btn.icon().isNull(), key
        # style letters stay text
        assert r._btn_bold.text() == "B"
        assert r._btn_italic.text() == "I"
    finally:
        r.set_editor(None)
        r.deleteLater()
