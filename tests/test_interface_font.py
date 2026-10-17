"""Per-area interface fonts: shared builders + per-area settings keys."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import pytest

import core.database as db
from ui.app_theme import (
    INTERFACE_FONT_WEIGHTS, build_interface_font, resolve_font_family,
)


@pytest.fixture()
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


@pytest.fixture()
def tmpdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    return tmp_path


def test_resolve_font_family(qapp, tmpdb):
    from PyQt6.QtGui import QFontDatabase
    real = QFontDatabase.families()[0]
    assert resolve_font_family(real) == real
    assert resolve_font_family("NoSuchFontXYZ") == ""
    assert resolve_font_family("") == ""
    assert resolve_font_family(None) == ""


def test_build_valid_combo(qapp, tmpdb):
    from PyQt6.QtGui import QFontDatabase
    family = QFontDatabase.families()[0]
    font = build_interface_font(family, 12, 700)
    assert font.family() == family
    assert font.pointSize() == 12
    assert font.weight() == 700


def test_build_falls_back(qapp, tmpdb):
    system_family = QApplication.font().family()
    font = build_interface_font("NoSuchFontXYZ", 99, "heavy",
                                size_max=16, size_default=10)
    assert font.family() == system_family
    assert font.pointSize() == 10
    assert font.weight() == 400
    partial = build_interface_font(None, 0, -5, weight_default=700)
    assert partial.pointSize() == 10
    assert partial.weight() == 700


def test_area_settings_round_trip(qapp, tmpdb):
    db.set_setting("bible.verse_font_family", "DejaVu Sans")
    db.set_setting("bible.verse_font_weight", "300")
    db.set_setting("search.result_font_family", "DejaVu Sans")
    assert db.get_setting("bible.verse_font_family") == "DejaVu Sans"
    assert db.get_setting("bible.verse_font_weight") == "300"
    assert db.get_setting("search.result_font_family") == "DejaVu Sans"


def test_weight_options_cover_range():
    values = [v for v, _ in INTERFACE_FONT_WEIGHTS]
    assert values == [100, 200, 300, 400, 500, 600, 700, 800, 900]


def test_area_font_explicit_keys(qapp, tmpdb):
    from ui.app_theme import area_font, font_qss
    db.set_setting("bible.verse_font_family", "NoSuchFontXYZ")
    db.set_setting("bible.verse_font_weight", "junk")
    spec = area_font("bible.verse", 12, 400,
                     family_key="bible.verse_font_family",
                     weight_key="bible.verse_font_weight",
                     size_key="bible.verse_text_size")
    assert spec == {"family": "", "weight": 400, "size": 12}
    css = font_qss(spec)
    assert "font-size: 12px;" in css and "font-weight: 400;" in css
    assert "font-family" not in css
    from PyQt6.QtGui import QFontDatabase
    real = QFontDatabase.families()[0]
    db.set_setting("bible.verse_font_family", real)
    spec = area_font("bible.verse", 12, 400,
                     family_key="bible.verse_font_family",
                     weight_key="bible.verse_font_weight",
                     size_key="bible.verse_text_size")
    assert spec["family"] == real
    assert f"font-family: '{real}';" in font_qss(spec)


def test_deck_delegate_font_defaults_and_override(qapp, tmpdb):
    from ui.panels.deck_list_panel import DeckCardDelegate
    d = DeckCardDelegate()
    assert (d._title_family, d._title_weight) == ("", 700)
    d.set_fonts("NoSuchFontXYZ", 300)
    assert (d._title_family, d._title_weight) == ("NoSuchFontXYZ", 300)


def test_browser_panel_applies_saved_fonts(qapp, tmpdb):
    from ui.panels.browser_panel import BrowserPanel
    db.set_setting("bible.verse_font_family", "NoSuchFontXYZ")
    db.set_setting("bible.verse_font_weight", "300")
    db.set_setting("bible.verse_ref_font_weight", "800")
    panel = BrowserPanel(translations=["KJV"])
    try:
        panel.update_verse_fonts()
        assert panel._delegate.verse_font_family == ""
        assert panel._delegate.verse_font_weight == 300
        assert panel._delegate.verse_ref_font_weight == 800
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_settings_interface_groups(qapp, tmpdb):
    from PyQt6.QtGui import QFont, QFontDatabase
    from ui.tabs.settings_tab import SettingsTab
    w = SettingsTab()
    try:
        qapp.processEvents()
        assert sorted(w._font_groups) == [
            "bible.ref", "bible.verse", "search.ref", "search.result",
            "slides.deck", "slides.editor", "slides.strip",
        ]
        verse = w._font_groups["bible.verse"]
        assert verse["weight"].currentData() == 400
        assert verse["size"].value() == 12
        ref = w._font_groups["bible.ref"]
        assert ref["weight"].currentData() == 700
        assert ref["size"].value() == 11
        # preview tracks the controls, saves land under legacy keys
        sizes, bibles = [], []
        w.font_size_changed.connect(lambda a, b: sizes.append((a, b)))
        w.bible_font_changed.connect(lambda: bibles.append(True))
        verse["size"].setValue(14)
        assert db.get_setting("bible.verse_text_size") == "14"
        assert sizes == [(14, 11)] and bibles == [True]
        fams = QFontDatabase.families()
        initial = verse["family"].currentFont().family()
        verse["family"].setCurrentFont(QFont(fams[0]))
        assert verse["preview"].font().family() == \
            verse["family"].currentFont().family()
        if fams[0] != initial:
            assert db.get_setting("bible.verse_font_family") == fams[0]
    finally:
        w.close()
        w.deleteLater()
        qapp.processEvents()
