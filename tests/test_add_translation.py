"""
tests/test_add_translation.py

Tests for the Add Translation feature:
  - import_translation_file() pipeline (XML, CSV, JSON)
  - refresh_available_translations()
  - Dialog creation and file validation
"""

import json
import os
import shutil
import sqlite3
import tempfile
from unittest import mock

import pytest


# ─── import_translation_file Tests ────────────────────────────────────────────


class TestImportJSON:
    def test_import_json_copies_file(self):
        """JSON file is copied to the json directory with correct name."""
        from core.bible_service import _import_json

        data = {"translation": "TEST", "books": {"Genesis": {"1": {"1": "In the beginning"}}}}
        tmpdir = tempfile.mkdtemp()
        try:
            src = os.path.join(tmpdir, "some_source.json")
            with open(src, "w", encoding="utf-8") as f:
                json.dump(data, f)

            with mock.patch("core.bible_service._JSON_DIR", tmpdir):
                dest = _import_json(src)

            assert os.path.exists(dest)
            assert dest.endswith("test.json")
            with open(dest, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded["translation"] == "TEST"
        finally:
            shutil.rmtree(tmpdir)

    def test_import_json_invalid_raises(self):
        """Invalid JSON (missing keys) raises ValueError."""
        from core.bible_service import _import_json

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"foo": "bar"}, f)
            src = f.name

        try:
            with mock.patch("core.bible_service._JSON_DIR", tempfile.mkdtemp()):
                with pytest.raises(ValueError, match="Invalid Bible JSON"):
                    _import_json(src)
        finally:
            os.unlink(src)


class TestImportCSV:
    def test_import_csv_converts_to_json(self):
        """CSV with version,book,chapter,verse,text columns produces JSON."""
        from core.bible_service import _import_csv

        csv_content = "version,book,chapter,verse,text\nTEST,Genesis,1,1,In the beginning\nTEST,Genesis,1,2,The earth was void\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            src = f.name

        try:
            tmpdir = tempfile.mkdtemp()
            with mock.patch("core.bible_service._JSON_DIR", tmpdir):
                dest = _import_csv(src)

            assert os.path.exists(dest)
            with open(dest, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["translation"] == "TEST"
            assert "Genesis" in data["books"]
            assert data["books"]["Genesis"]["1"]["1"] == "In the beginning"
            shutil.rmtree(tmpdir)
        finally:
            os.unlink(src)


class TestLoadIntoDB:
    def test_load_into_db_creates_version(self):
        """Loading a JSON file inserts verses into bible.db."""
        from core.bible_service import _load_into_db

        data = {
            "translation": "TESTDB",
            "books": {
                "Genesis": {"1": {"1": "In the beginning", "2": "The earth was void"}},
                "John": {"3": {"16": "For God so loved the world"}},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            json_path = f.name

        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        try:
            version = _load_into_db.__wrapped__(json_path, db_path) if hasattr(_load_into_db, '__wrapped__') else None
            # Directly test by patching _BIBLE_DB_PATH
            with mock.patch("core.bible_service._BIBLE_DB_PATH", db_path):
                version = _load_into_db(json_path)

            assert version == "TESTDB"

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            count = conn.execute("SELECT COUNT(*) as c FROM verses WHERE version = 'TESTDB'").fetchone()["c"]
            assert count == 3  # Gen 1:1, Gen 1:2, John 3:16

            # FTS index should exist
            fts_count = conn.execute("SELECT COUNT(*) as c FROM verses_fts").fetchone()["c"]
            assert fts_count == 3
            conn.close()
        finally:
            os.unlink(json_path)
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_load_into_db_idempotent(self):
        """Loading the same version twice replaces (not duplicates) verses."""
        from core.bible_service import _load_into_db

        data_v1 = {"translation": "IDEM", "books": {"Genesis": {"1": {"1": "v1 text"}}}}
        data_v2 = {"translation": "IDEM", "books": {"Genesis": {"1": {"1": "v2 text"}}}}

        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        try:
            with mock.patch("core.bible_service._BIBLE_DB_PATH", db_path):
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                    json.dump(data_v1, f)
                    p1 = f.name
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                    json.dump(data_v2, f)
                    p2 = f.name

                _load_into_db(p1)
                _load_into_db(p2)

            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT text FROM verses WHERE version = 'IDEM'").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "v2 text"
            conn.close()
            os.unlink(p1)
            os.unlink(p2)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestRefreshTranslations:
    def test_refresh_updates_list(self):
        """refresh_available_translations() re-queries DB and updates module list."""
        from core import bible_service

        mock_translations = ["AMP", "ESV", "KJV", "NIV", "NKJV", "NLT", "NEW_TRANSLATION"]
        with mock.patch("core.bible_service.get_available_translations", return_value=mock_translations):
            result = bible_service.refresh_available_translations()

        assert "NEW_TRANSLATION" in result
        assert "NEW_TRANSLATION" in bible_service.AVAILABLE_TRANSLATIONS


# ─── Dialog Tests ─────────────────────────────────────────────────────────────


class TestAddTranslationDialog:
    def test_dialog_creation(self):
        """Dialog can be instantiated without errors."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        from ui.dialogs.add_translation_dialog import AddTranslationDialog
        dialog = AddTranslationDialog()
        assert dialog.windowTitle() == "Add Translation"
        assert dialog.selected_path() is None

    def test_selected_path_initially_none(self):
        """selected_path() returns None before any action."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        from ui.dialogs.add_translation_dialog import AddTranslationDialog
        dialog = AddTranslationDialog()
        assert dialog.selected_path() is None
