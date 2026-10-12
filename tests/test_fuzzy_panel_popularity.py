"""Fuzzy panel popularity: weighted picks logged, boost reorders."""

import os
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
import pytest

import core.database as db

_OPEN = []


@pytest.fixture(autouse=True)
def _close():
    yield
    for w in _OPEN:
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    _qt().processEvents()


_app = None


def _qt():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


def _panel(tmp_path, monkeypatch):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from ui.panels import search_panel as mod
    import core.search_engine as se

    def fake_bm25(query, top_k=10):
        return [(4, "KJV", "Gen", 1, 1, 5.0, "In the beginning"),
                (3, "KJV", "Gen", 1, 2, 4.0, "Earth was void")]

    def fake_faiss(query, top_k=10):
        return [(2, "KJV", "Gen", 1, 2, 0.9, "Earth was void"),
                (1, "KJV", "Gen", 1, 1, 0.8, "In the beginning")]

    def fake_topical(query, top_k=3):
        return []

    monkeypatch.setattr(se, "fuzzy_bm25_search", fake_bm25)
    monkeypatch.setattr(se, "faiss_search", fake_faiss)
    monkeypatch.setattr(se, "topical_search", fake_topical)
    panel = mod.SearchPanel()
    panel.show()
    _qt().processEvents()
    _OPEN.append(panel)
    monkeypatch.setattr(panel, "_ensure_indexes_loaded", lambda: True)
    return panel


def _verse_texts(panel):
    return [r["text"] for r in panel._verse_results]


def test_fuzzy_picks_logged_with_weights(tmp_path, monkeypatch):
    from core.database import read_verse_popularity
    panel = _panel(tmp_path, monkeypatch)
    panel.query_input.setText("beginning earth")
    panel._on_search()
    assert panel._verse_results, "expected fused results"
    verse = {"book": "Gen", "chapter": 1, "verse_num": 2, "verse": 2,
             "text": "Earth was void", "confidence": 5.0}
    panel.verse_to_navigator.emit(dict(verse))
    panel.verse_to_schedule.emit(dict(verse))
    panel.verse_to_live.emit(dict(verse))
    rows = [r for r in read_verse_popularity() if r["book"] == "Gen"]
    assert len(rows) == 1
    assert rows[0]["prompt"] == "beginning earth"
    assert rows[0]["points"] == 1 + 3 + 5
    assert rows[0]["picks"] == 3


def test_fuzzy_boost_reorders(tmp_path, monkeypatch):
    from core.database import log_verse_pick
    panel = _panel(tmp_path, monkeypatch)
    panel.query_input.setText("beginning earth")
    panel._on_search()
    first = _verse_texts(panel)
    assert first[0] == "In the beginning"
    for _ in range(15):
        log_verse_pick("beginning earth", "Gen", 1, 2, 5)
    panel._on_search()
    again = _verse_texts(panel)
    assert again[0] == "Earth was void"
    assert again != first
