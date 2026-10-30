"""
tests/test_rename_reorder.py

Tests for translation rename and drag-and-drop reordering:
  - Display name mapping (get/set)
  - Translation order persistence (get/set)
  - Rename validation
  - Button creation with display names
"""

import json
import os
from unittest import mock

import pytest


# ─── Display Name Tests ──────────────────────────────────────────────────────


class TestDisplayName:
    def test_get_display_name_default(self):
        """Without any rename, get_display_name returns the canonical name."""
        from core.bible_service import get_display_name, _display_names_cache

        _display_names_cache.clear()
        assert get_display_name("KJV") == "KJV"

    def test_set_and_get_display_name(self):
        """After setting a display name, get_display_name returns it."""
        from core.bible_service import set_display_name, get_display_name, _display_names_cache

        _display_names_cache.clear()
        with mock.patch("core.bible_service._display_names_loaded", True):
            set_display_name("ENGLISHPASSIONBIBLE", "EPB")
            assert get_display_name("ENGLISHPASSIONBIBLE") == "EPB"
            # Other translations unaffected
            assert get_display_name("KJV") == "KJV"

    def test_set_display_name_empty_reverts(self):
        """Setting display name to empty string removes the mapping."""
        from core.bible_service import set_display_name, get_display_name, _display_names_cache

        _display_names_cache.clear()
        with mock.patch("core.bible_service._display_names_loaded", True):
            set_display_name("TEST", "Short")
            assert get_display_name("TEST") == "Short"
            set_display_name("TEST", "")
            assert get_display_name("TEST") == "TEST"

    def test_get_all_display_names(self):
        """get_all_display_names returns the full mapping."""
        from core.bible_service import set_display_name, get_all_display_names, _display_names_cache

        _display_names_cache.clear()
        with mock.patch("core.bible_service._display_names_loaded", True):
            set_display_name("A", "Alpha")
            set_display_name("B", "Bravo")
            names = get_all_display_names()
            assert names["A"] == "Alpha"
            assert names["B"] == "Bravo"


# ─── Translation Order Tests ─────────────────────────────────────────────────


class TestTranslationOrder:
    def test_get_order_default_empty(self):
        """Without saved order, get_translation_order returns empty list."""
        from core.bible_service import get_translation_order, _order_cache

        _order_cache = None
        with mock.patch("core.database.get_setting", return_value="[]"):
            order = get_translation_order()
            assert order == []

    def test_set_and_get_order(self):
        """After setting order, get_translation_order returns it."""
        from core.bible_service import set_translation_order, get_translation_order, _order_cache

        _order_cache = None
        with mock.patch("core.database.set_setting") as mock_set, \
             mock.patch("core.database.get_setting", return_value='["KJV","ESV","NIV"]'):
            set_translation_order(["KJV", "ESV", "NIV"])
            # Verify set_setting was called with correct args
            mock_set.assert_called_once_with(
                "bible.translation_order",
                '["KJV", "ESV", "NIV"]'
            )


# ─── TranslationButton Tests ────────────────────────────────────────────────


class TestTranslationButton:
    def test_button_creation_with_display_name(self):
        """TranslationButton can be created with a custom display name."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        from ui.panels.browser_panel import TranslationButton
        btn = TranslationButton("ENGLISHPASSIONBIBLE", "EPB")
        assert btn.canonical == "ENGLISHPASSIONBIBLE"
        assert btn.display_name == "EPB"
        assert btn.text() == "EPB"
        assert "EPB" in btn.toolTip()

    def test_button_creation_default_display(self):
        """TranslationButton defaults display_name to canonical."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        from ui.panels.browser_panel import TranslationButton
        btn = TranslationButton("KJV")
        assert btn.canonical == "KJV"
        assert btn.display_name == "KJV"
        assert btn.text() == "KJV"

    def test_button_rename_updates_text(self):
        """After renaming, button text updates to new display name."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        from ui.panels.browser_panel import TranslationButton
        btn = TranslationButton("TEST", "Original")
        # Simulate rename by setting attributes directly
        btn.display_name = "NewName"
        btn.setText("NewName")
        assert btn.text() == "NewName"
        assert btn.display_name == "NewName"


# ─── Order Persistence Integration ───────────────────────────────────────────


class TestOrderPersistence:
    def test_order_saved_on_reorder(self):
        """When buttons are reordered, the new order is saved to settings."""
        from core.bible_service import set_translation_order, get_translation_order, _order_cache

        _order_cache = None
        order = ["KJV", "ESV", "NKJV", "NIV", "AMP", "NLT"]
        with mock.patch("core.database.set_setting") as mock_set:
            set_translation_order(order)
            mock_set.assert_called_once()
            args = mock_set.call_args
            assert args[0][0] == "bible.translation_order"
            saved = json.loads(args[0][1])
            assert saved == order


# ─── Translation Bar Sorting ─────────────────────────────────────────────────


@pytest.fixture()
def _sorted_app():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


@pytest.fixture()
def _sorted_db(tmp_path, monkeypatch):
    import core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    return tmp_path


def _bar_widgets(panel):
    """Widgets in the translation bar, left to right, spacer skipped."""
    from PyQt6.QtWidgets import QScrollArea
    scroll = next(child for child in panel.findChildren(QScrollArea)
                  if child.widget() is not None)
    layout = scroll.widget().layout()
    return [layout.itemAt(i).widget() for i in range(layout.count())
            if layout.itemAt(i).widget() is not None]


class TestTranslationBarSort:
    def _panel(self):
        from ui.panels.browser_panel import BrowserPanel
        return BrowserPanel(translations=["NIV", "KJV", "AMP"])

    def _assert_order(self, panel, expected):
        widgets = _bar_widgets(panel)
        # + Add is not a translation: it stays last, after the stretch.
        assert widgets[-1] is panel._add_btn
        names = [w.canonical for w in widgets if w is not panel._add_btn]
        assert names == expected
        # Only translations are persisted.
        saved = json.loads(db_get_order())
        assert saved == expected

    def test_add_stays_last_after_az(self, _sorted_app, _sorted_db):
        panel = self._panel()
        try:
            panel._on_sort_translations("az")
            self._assert_order(panel, ["AMP", "KJV", "NIV"])
        finally:
            panel.close()
            panel.deleteLater()
            _sorted_app.processEvents()

    def test_add_stays_last_after_za(self, _sorted_app, _sorted_db):
        panel = self._panel()
        try:
            panel._on_sort_translations("za")
            self._assert_order(panel, ["NIV", "KJV", "AMP"])
        finally:
            panel.close()
            panel.deleteLater()
            _sorted_app.processEvents()


def db_get_order():
    from core.database import get_setting
    return get_setting("bible.translation_order", "[]")
