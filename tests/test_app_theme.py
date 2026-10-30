"""App theme: single source of truth (graphite: grey/black + purple),
selection highlight in result rows and schedule items."""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor

import core.database as db

_app = None


def _qt():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


def test_all_themes_have_all_roles():
    from ui import app_theme
    for name in app_theme.theme_names():
        app_theme.validate_theme(name)  # raises on missing roles


def test_all_colors_parse():
    from ui import app_theme
    for name in app_theme.theme_names():
        for role, value in app_theme.THEMES[name].items():
            assert QColor(value).isValid(), (name, role, value)


def test_graphite_direction():
    from ui import app_theme
    t = app_theme.THEMES["graphite"]
    # Backgrounds are grey/black: dark, channels nearly equal.
    for role in ("bg_app", "bg_raised", "chrome_bg", "chrome_tab_active"):
        c = QColor(t[role])
        assert c.value() < 60, (role, t[role])
        r, g, b, _a = c.getRgb()
        assert max(r, g, b) - min(r, g, b) <= 6, (role, t[role])
    # Accent and selection are purple (hue ~270-300).
    for role in ("accent", "accent_hover", "selection_border"):
        hue = QColor(t[role]).hue()
        assert 260 <= hue <= 300, (role, t[role], hue)


def test_set_theme_rejects_unknown():
    from ui import app_theme
    with pytest.raises(KeyError):
        app_theme.set_theme("nope")
    assert app_theme.active_name() == "graphite"


def test_styles_tokens_track_theme():
    import ui.styles as s
    from ui import app_theme
    assert s.ACCENT == app_theme.color("accent")
    assert s.SELECTION_BG == app_theme.color("selection_bg")
    assert s.SELECTION_TEXT == app_theme.color("selection_text")
    assert s.BG_APP == app_theme.color("bg_app")
    # Legacy aliases follow the accent (purple), not the old cyan/blue.
    assert s.CYAN_400 == app_theme.color("accent")
    assert s.BLUE_500 == app_theme.color("accent")


def test_apply_palette_runs():
    from ui import app_theme
    old = _qt().palette()
    try:
        app_theme.apply_palette(_qt())
        pal = _qt().palette()
        assert pal.color(pal.ColorRole.Highlight) == QColor(
            app_theme.color("accent"))
    finally:
        _qt().setPalette(old)


def test_fts_row_selection_highlight(tmp_path, monkeypatch):
    """Clicking an FTS row selects it with the purple highlight."""
    import time
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from ui.panels import fts_search_panel as mod

    def fake_hybrid(query, version, limit=30):
        return [{"book": "Luke", "chapter": 15, "verse": 11 + i,
                 "verse_num": 11 + i, "text": f"parable text {i}",
                 "confidence": 90.0 - i} for i in range(3)]

    monkeypatch.setattr(mod, "fts_search", fake_hybrid)
    panel = mod.FtsSearchPanel()
    panel._paint_per_frame = 10 ** 9
    panel.show()
    try:
        panel.query_input.setText("prodigal")
        panel._on_search()
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            _qt().processEvents()
            time.sleep(0.01)
            fut = panel._search_future
            if fut is not None and fut.done() and panel._paint is None:
                break
        _qt().processEvents()
        assert panel.results_list.count() == 3
        from PyQt6.QtTest import QTest
        from PyQt6.QtCore import Qt
        row0 = panel.results_list.itemWidget(panel.results_list.item(0))
        pos = row0.rect().center()
        QTest.mouseClick(row0, Qt.MouseButton.LeftButton, pos=pos)
        _qt().processEvents()
        item0 = panel.results_list.item(0)
        assert item0.isSelected()
        assert row0.property("selected") is True
        # Unselected rows stay unhighlighted.
        row1 = panel.results_list.itemWidget(panel.results_list.item(1))
        assert row1.property("selected") is not True
        # The highlight paints the solid theme selection color.
        # Sample the left padding lane (x=2), clear of any label text.
        from ui import app_theme as _at
        _sel = QColor(_at.color("selection_bg")).getRgb()[:3]
        _img = row0.grab().toImage()
        px = _img.pixelColor(
            2, row0.rect().center().y()).getRgb()[:3]
        assert all(abs(a - b) <= 20 for a, b in zip(px, _sel)), (px, _sel)
    finally:
        try:
            panel.cleanup()
        except Exception:
            pass
        panel.close()
        panel.deleteLater()
        _qt().processEvents()


def test_schedule_item_selection_uses_theme():
    _qt()
    from ui.panels.schedule_panel import ScheduleItem
    from ui import app_theme
    item = ScheduleItem({"ref": "Luke 15:11", "translation": "KJV"})
    item.set_selected(True)
    try:
        assert app_theme.color("selection_bg") in item.styleSheet()
        _sel = QColor(app_theme.color("selection_bg")).getRgb()[:3]
        _accent = QColor(app_theme.color("accent")).getRgb()[:3]
        _img = item.grab().toImage()
        y = item.rect().center().y()
        # 3 px accent bar on the left…
        px = _img.pixelColor(1, y).getRgb()[:3]
        assert all(abs(a - b) <= 20 for a, b in zip(px, _accent)), (px, _accent)
        # …and the selection wash across the card body.
        px = _img.pixelColor(6, y).getRgb()[:3]
        assert all(abs(a - b) <= 20 for a, b in zip(px, _sel)), (px, _sel)
        # Translation badge keeps the shared secondary text colour.
        assert "a1a1aa" in item._translation_badge.styleSheet().lower()
    finally:
        item.close()
        item.deleteLater()
        _qt().processEvents()


def test_fuzzy_row_has_set_selected():
    from ui.panels.search_panel import SearchResultWidget
    assert hasattr(SearchResultWidget, "set_selected")


def test_brand_mark_follows_theme():
    """The logo renders the brand artwork recolored from theme roles."""
    from PyQt6.QtGui import QColor
    from ui.widgets import loading_screen as ls
    from ui import app_theme
    # Template carries placeholders, never baked-in brand colors.
    template = open("ui/assets/brand-mark.svg", encoding="utf-8").read()
    assert "__BAR0__" in template and "__TILE__" in template
    assert "38bdf8" not in template and "e0b93d" not in template
    # Substituted bytes carry the theme ramp (accent → light by height).
    accent = QColor(app_theme.color("accent")).name().lower()
    light = QColor(app_theme.color("accent_light")).name().lower()
    body = ls.brand_svg_bytes().decode("utf-8").lower()
    assert "__" not in body
    assert accent in body and light in body
    mark = ls.BrandMark(140)
    try:
        mark.show()
        _qt().processEvents()
        img = mark.grab().toImage()
        # Tallest bar renders near the light accent (artwork hue preserved).
        found = False
        for x in range(0, img.width(), 4):
            for y in range(0, img.height(), 4):
                c = img.pixelColor(x, y)
                if (abs(c.red() - QColor(light).red()) < 40
                        and abs(c.green() - QColor(light).green()) < 40
                        and abs(c.blue() - QColor(light).blue()) < 40
                        and c.alpha() > 128):
                    found = True
                    break
            if found:
                break
        assert found, "no accent-light bar pixels in the painted mark"
        # Pixmap helper renders the same mark transparently.
        pix = ls.mark_pixmap(64)
        assert pix.width() == 64 and not pix.isNull()
        assert pix.toImage().pixelColor(0, 0).alpha() == 0
    finally:
        mark.close()
        mark.deleteLater()
        _qt().processEvents()


def test_loading_screen_static_brand():
    from ui.widgets.loading_screen import LoadingScreen
    screen = LoadingScreen()
    screen.show()
    try:
        _qt().processEvents()
        # No frame clock: the mark is static by design.
        assert getattr(screen, "_frame_timer", None) is None
        # Radial backdrop: center brighter/purpler than a corner.
        bg = screen.grab().toImage()
        w, h = bg.width(), bg.height()
        center = bg.pixelColor(w // 2, int(h * 0.38))
        corner = bg.pixelColor(6, h - 6)
        assert (center.red() + center.blue() >
                corner.red() + corner.blue()), (center.getRgb(), corner.getRgb())
        # Two-tone wordmark uses the light-purple accent.
        from ui import app_theme
        from PyQt6.QtWidgets import QLabel
        labels = screen.findChildren(QLabel)
        assert any(app_theme.color("accent_light").lower() in
                   (lbl.text() or "").lower() for lbl in labels)
    finally:
        screen.close()
        screen.deleteLater()
        _qt().processEvents()


def test_text_selection_is_visible_and_readable():
    """Text selection is a HIGHLIGHT, not a row wash: it must contrast
    with the dark editor background and carry readable text."""
    from ui import app_theme
    from ui.styles import TEXT_SELECTION, SELECTION_BG
    from ui.widgets.predictive_input import BIBLE_BOOKS  # noqa: F401

    def _lum(c):
        def f(v):
            v /= 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(c.red()) + 0.7152 * f(c.green()) + 0.0722 * f(c.blue())

    ts = QColor(TEXT_SELECTION)
    card_bg = QColor(app_theme.color("bg_raised"))
    text = QColor(app_theme.color("text_primary"))

    def ratio(a, b):
        la, lb = _lum(a), _lum(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    # Visible against the card it highlights...
    assert ratio(ts, card_bg) > 1.8, ratio(ts, card_bg)
    # ...and clearly not the subtle row wash.
    assert QColor(TEXT_SELECTION) != QColor(SELECTION_BG)
    # Text on top of it stays readable (WCAG AA large text).
    assert ratio(text, ts) >= 4.5, ratio(text, ts)


def test_lite_designer_text_selection_uses_highlight():
    """Focused cards highlight selected text with the visible color."""
    from ui.styles import TEXT_SELECTION, SELECTION_BG
    from ui.widgets.lite_designer.slide_cards import _display_box_style
    active = _display_box_style(True, 13)
    assert TEXT_SELECTION in active
    assert SELECTION_BG not in active


def test_all_text_selection_rules_use_text_role():
    """No editor may highlight selected text with the row wash."""
    import glob
    import re
    bad = []
    for path in glob.glob("ui/**/*.py", recursive=True):
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(r"selection-background-color:[^\n]*", src):
            line = m.group(0)
            if "SELECTION_BG" in line and "TEXT_SELECTION" not in line:
                bad.append(f"{path}: {line.strip()}")
    assert not bad, bad


def test_translation_button_uses_accent():
    from ui.styles import TRANSLATION_BTN_ACTIVE
    from ui import app_theme
    assert app_theme.color("accent") in TRANSLATION_BTN_ACTIVE
    assert "f59e0b" not in TRANSLATION_BTN_ACTIVE.lower()


def test_selected_hover_stays_put():
    """Hovering a selected row must not brighten it (schedule + FTS)."""
    from ui.panels.schedule_panel import ScheduleItem
    from ui.panels.fts_search_panel import _ResultRow
    item = ScheduleItem({"ref": "Luke 15:11", "translation": "KJV"})
    try:
        assert 'selected="true"]:hover' in item.styleSheet()
    finally:
        item.close()
        item.deleteLater()
        _qt().processEvents()
    row = _ResultRow(
        {"book": "Luke", "chapter": "15", "verse_num": "11",
         "text": "t", "confidence": 90.0, "translations": []}, "luke")
    try:
        assert 'selected="true"]:hover' in row.styleSheet()
    finally:
        row.close()
        row.deleteLater()
        _qt().processEvents()
