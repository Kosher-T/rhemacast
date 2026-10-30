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
    assert partial.pointSize() == 13
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


def test_translation_bar_follows_panel_labels(qapp, tmpdb):
    """Translation buttons + Add read the panel-label group, live."""
    from PyQt6.QtGui import QFontDatabase
    from ui.app_theme import notify_interface_font_changed
    from ui.panels.browser_panel import BrowserPanel

    fam = QFontDatabase.families()[0]
    db.set_setting("panel.labels.font_family", fam)
    db.set_setting("panel.labels.font_size", "17")

    panel = BrowserPanel(translations=["KJV", "NIV"])
    try:
        btn = panel._translation_buttons["KJV"]
        qss = btn.styleSheet()
        assert f"font-family: '{fam}';" in qss
        assert "font-size: 17px;" in qss
        assert "font-weight: 700;" in qss
        # + Add shares the group; its inactive weight default is 600.
        add_qss = panel._add_btn.styleSheet()
        assert f"font-family: '{fam}';" in add_qss
        assert "font-size: 17px;" in add_qss
        assert "font-weight: 600;" in add_qss

        # Saved change reaches the built bar without a rebuild.
        db.set_setting("panel.labels.font_size", "19")
        notify_interface_font_changed("panel.labels")
        assert "font-size: 19px;" in btn.styleSheet()
        assert "font-size: 19px;" in panel._add_btn.styleSheet()
        # Active state repaint keeps the group font.
        btn.set_active(True)
        assert "font-size: 19px;" in btn.styleSheet()
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_search_inputs_follow_panel_groups(qapp, tmpdb):
    """Search-box placeholders read their panel groups, live."""
    from PyQt6.QtGui import QFontDatabase
    from ui.app_theme import notify_interface_font_changed
    from ui.panels.search_panel import SearchPanel
    from ui.panels.fts_search_panel import FtsSearchPanel
    from ui.panels.deck_list_panel import DeckListPanel

    fam = QFontDatabase.families()[0]
    db.set_setting("search.result_font_family", fam)
    db.set_setting("search.result_font_size", "15")
    db.set_setting("slides.deck_font_family", fam)
    db.set_setting("slides.deck_font_size", "15")

    sem = SearchPanel()
    fts = FtsSearchPanel()
    deck = DeckListPanel()
    try:
        qss = sem.query_input.styleSheet()
        assert f"font-family: '{fam}';" in qss
        assert "font-size: 15px;" in qss
        for box in (fts.query_input, fts.filter_input):
            qss = box.styleSheet()
            assert f"font-family: '{fam}';" in qss
            assert "font-size: 15px;" in qss
        qss = deck.search_box.styleSheet()
        assert f"font-family: '{fam}';" in qss
        assert "font-size: 15px;" in qss

        # A saved change repaints the already-built boxes.
        db.set_setting("search.result_font_size", "16")
        notify_interface_font_changed("search.result")
        assert "font-size: 16px;" in sem.query_input.styleSheet()
        assert "font-size: 16px;" in fts.query_input.styleSheet()
        assert "font-size: 16px;" in fts.filter_input.styleSheet()
        db.set_setting("slides.deck_font_size", "17")
        notify_interface_font_changed("slides.deck")
        assert "font-size: 17px;" in deck.search_box.styleSheet()
    finally:
        for widget in (sem, fts, deck):
            widget.close()
            widget.deleteLater()
        qapp.processEvents()


def test_navigator_follows_bible_verse_group(qapp, tmpdb):
    """Navigator book/chapter/verse + colon read the Bible-verse group."""
    from PyQt6.QtGui import QFontDatabase
    from ui.app_theme import notify_interface_font_changed
    from ui.widgets.predictive_input import PredictiveScriptureInput

    nav = PredictiveScriptureInput()
    try:
        # Unset keeps the navigator's own 13/600 fields, 14/500 colon.
        for field in (nav.book_input, nav.chapter_input, nav.verse_input):
            qss = field.styleSheet()
            assert "font-size: 13px;" in qss
            assert "font-weight: 600;" in qss
        assert "font-size: 14px;" in nav._separator.styleSheet()
        assert "font-weight: 500;" in nav._separator.styleSheet()

        width_before = nav.book_input.width()
        fam = QFontDatabase.families()[0]
        db.set_setting("bible.verse_font_family", fam)
        db.set_setting("bible.verse_font_weight", "400")
        db.set_setting("bible.verse_text_size", "16")
        notify_interface_font_changed("bible.verse")

        for field in (nav.book_input, nav.chapter_input, nav.verse_input):
            qss = field.styleSheet()
            assert f"font-family: '{fam}';" in qss
            assert "font-size: 16px;" in qss
            assert "font-weight: 400;" in qss
        assert "font-size: 16px;" in nav._separator.styleSheet()
        # Font-metric-fitted widths are refitted for the larger size.
        assert nav.book_input.width() > width_before

        # A fresh navigator starts already fitted to the saved group.
        nav2 = PredictiveScriptureInput()
        try:
            assert "font-size: 16px;" in nav2.book_input.styleSheet()
            assert nav2.book_input.width() > width_before
        finally:
            nav2.close()
            nav2.deleteLater()
            qapp.processEvents()
    finally:
        nav.close()
        nav.deleteLater()
        qapp.processEvents()


def test_settings_interface_groups(qapp, tmpdb):
    from PyQt6.QtGui import QFont, QFontDatabase
    from ui.tabs.settings_tab import SettingsTab
    w = SettingsTab()
    try:
        qapp.processEvents()
        assert sorted(w._font_groups) == [
            "bible.ref", "bible.verse", "panel.labels", "schedule.cards",
            "search.ref", "search.result", "slides.deck", "slides.editor",
            "slides.strip", "tabs.names",
        ]
        verse = w._font_groups["bible.verse"]
        assert verse["weight"].currentData() == 400
        assert verse["size"].value() == 13
        ref = w._font_groups["bible.ref"]
        assert ref["weight"].currentData() == 700
        assert ref["size"].value() == 12
        # Chrome groups: same defaults as the pre-settings look.
        labels = w._font_groups["panel.labels"]
        assert labels["weight"].currentData() == 600
        assert labels["size"].value() == 13
        cards = w._font_groups["schedule.cards"]
        assert cards["weight"].currentData() == 600
        assert cards["size"].value() == 12
        tabs = w._font_groups["tabs.names"]
        assert tabs["weight"].currentData() == 600
        assert tabs["size"].value() == 12
        # preview tracks the controls, saves land under legacy keys
        sizes, bibles = [], []
        w.font_size_changed.connect(lambda a, b: sizes.append((a, b)))
        w.bible_font_changed.connect(lambda: bibles.append(True))
        verse["size"].setValue(14)
        assert db.get_setting("bible.verse_text_size") == "14"
        assert sizes == [(14, 12)] and bibles == [True]
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


def test_chrome_groups_apply_and_refresh(qapp, tmpdb):
    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtCore import Qt
    from ui.app_theme import notify_interface_font_changed
    from core.schedule_model import ScheduleModel
    from ui.panels.schedule_panel import SchedulePanel
    from ui.panels.text_tabs import build_text_tab_row, text_tab_qss
    from ui.styles import panel_header_label_style

    fam = QFontDatabase.families()[0]
    db.set_setting("panel.labels.font_family", fam)
    db.set_setting("panel.labels.font_weight", "700")
    db.set_setting("panel.labels.font_size", "17")
    db.set_setting("tabs.names.font_family", fam)
    db.set_setting("tabs.names.font_size", "15")
    db.set_setting("schedule.cards.font_size", "16")

    header_qss = panel_header_label_style()
    assert f"font-family: '{fam}';" in header_qss
    assert "font-size: 17px;" in header_qss
    assert "font-weight: 700;" in header_qss

    row, _group, buttons = build_text_tab_row([("a", "Outputs", "x")])
    model = ScheduleModel()
    panel = SchedulePanel(model=model)
    model.add_item({"ref": "JHN 3:16", "translation": "NKJV", "_sched_uid": "u1"})
    qapp.processEvents()
    li = panel.list_widget.item(0)
    item = li.data(Qt.ItemDataRole.UserRole + 1)
    try:
        assert f"font-family: '{fam}';" in buttons["a"].styleSheet()
        assert "font-size: 15px;" in buttons["a"].styleSheet()
        assert "font-size: 16px;" in item._ref_label.styleSheet()
        # Selection repaint keeps the card font (colour only changes).
        item.set_selected(True)
        assert "font-size: 16px;" in item._translation_badge.styleSheet()
        # A saved change reaches already-built chrome without a rebuild.
        db.set_setting("tabs.names.font_size", "18")
        notify_interface_font_changed("tabs.names")
        assert "font-size: 18px;" in buttons["a"].styleSheet()
        assert buttons["a"].styleSheet() == text_tab_qss()
        db.set_setting("schedule.cards.font_size", "18")
        notify_interface_font_changed("schedule.cards")
        assert "font-size: 18px;" in item._ref_label.styleSheet()
        assert "font-size: 18px;" in item._translation_badge.styleSheet()
        # The panel header reads the same group.
        db.set_setting("panel.labels.font_size", "19")
        notify_interface_font_changed("panel.labels")
        assert "font-size: 19px;" in panel._title_label.styleSheet()
    finally:
        row.close()
        panel.close()
        row.deleteLater()
        panel.deleteLater()
        qapp.processEvents()
