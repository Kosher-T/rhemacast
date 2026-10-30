"""FTS book/testament filter: verified-inputs-only filter box mirroring
the navigator book input (highlighted autofill), per-keystroke hide/show
filtering, testament terms, cap bypass, x-clear, new-search respect.
"""

import os
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
import pytest

import core.database as db

_OPEN = []


@pytest.fixture(autouse=True)
def _close():
    yield
    for w in _OPEN:
        try:
            w.cleanup()
        except Exception:
            pass
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


_BOOKS = (["Genesis"] * 3 + ["Exodus"] * 2 + ["Psalms"] * 4
          + ["Matthew"] * 2 + ["Revelation"] * 1)


def _panel(tmp_path, monkeypatch, books=None, cap=10 ** 9):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from ui.panels import fts_search_panel as mod
    books = _BOOKS if books is None else books

    def fake_hybrid(query, version, limit=30):
        return [{"book": b, "chapter": 1, "verse": i + 1,
                 "verse_num": i + 1, "text": f"hit {b} {i}",
                 "confidence": 9.0 - i * 0.01}
                for i, b in enumerate(books)]

    monkeypatch.setattr(mod, "fts_search", fake_hybrid)
    panel = mod.FtsSearchPanel()
    panel._paint_per_frame = cap
    panel.show()
    _qt().processEvents()
    _OPEN.append(panel)
    return panel


def _search(panel, query):
    panel.query_input.setText(query)
    panel._on_search()
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        _qt().processEvents()
        time.sleep(0.01)
        fut = panel._search_future
        if fut is not None and fut.done() and panel._paint is None:
            break
    _qt().processEvents()


def _visible_books(panel):
    out = []
    for i in range(panel.results_list.count()):
        item = panel.results_list.item(i)
        w = panel.results_list.itemWidget(item)
        if type(w).__name__ == "_ResultRow" and not item.isHidden():
            out.append(w._data["book"])
    return out


def _buttons(panel):
    return sum(
        isinstance(panel.results_list.itemWidget(panel.results_list.item(i)),
                   QPushButton)
        for i in range(panel.results_list.count()))


def test_keystroke_filter_by_book(tmp_path, monkeypatch):
    p = _panel(tmp_path, monkeypatch)
    _search(p, "grace")
    assert len(_visible_books(p)) == 12
    QTest.keyClicks(p.filter_input, "ps")
    _qt().processEvents()
    assert p.filter_input.text() == "Psalms"
    assert _visible_books(p) == ["Psalms"] * 4
    assert p.status_label.text() == "4 of 12 verses (filter: Psalms)"


def test_filter_rejects_unverified_chars(tmp_path, monkeypatch):
    p = _panel(tmp_path, monkeypatch)
    _search(p, "grace")
    QTest.keyClicks(p.filter_input, "ps!")
    _qt().processEvents()
    assert p.filter_input.text() == "Psalms"
    assert _visible_books(p) == ["Psalms"] * 4


def test_old_and_new_testament_filters(tmp_path, monkeypatch):
    p = _panel(tmp_path, monkeypatch)
    _search(p, "grace")
    QTest.keyClicks(p.filter_input, "old")
    _qt().processEvents()
    assert p.filter_input.text() == "Old Testament"
    assert sorted(_visible_books(p)) == ["Exodus"] * 2 + ["Genesis"] * 3 + ["Psalms"] * 4
    p.filter_input.clear_filter()
    _qt().processEvents()
    QTest.keyClicks(p.filter_input, "new")
    _qt().processEvents()
    assert p.filter_input.text() == "New Testament"
    assert sorted(_visible_books(p)) == ["Matthew"] * 2 + ["Revelation"]


def test_gospels_filter(tmp_path, monkeypatch):
    books = (["Genesis"] * 2 + ["Matthew"] * 1 + ["Mark"] * 2
             + ["Luke"] * 1 + ["John"] * 3 + ["Acts"] * 2
             + ["Revelation"] * 1)
    p = _panel(tmp_path, monkeypatch, books=books)
    _search(p, "grace")
    QTest.keyClicks(p.filter_input, "gos")
    _qt().processEvents()
    assert p.filter_input.text() == "Gospels"
    assert p.filter_input.current_filter() == "Gospels"
    assert sorted(_visible_books(p)) == ["John"] * 3 + ["Luke"] + ["Mark"] * 2 + ["Matthew"]
    assert p.status_label.text() == "7 of 12 verses (filter: Gospels)"


def test_clear_button_restores_all(tmp_path, monkeypatch):
    p = _panel(tmp_path, monkeypatch)
    _search(p, "grace")
    QTest.keyClicks(p.filter_input, "exo")
    _qt().processEvents()
    assert _visible_books(p) == ["Exodus"] * 2
    p.filter_clear_btn.click()
    _qt().processEvents()
    assert p.filter_input.text() == ""
    assert len(_visible_books(p)) == 12
    assert "filter" not in p.status_label.text()


def test_new_search_respects_active_filter(tmp_path, monkeypatch):
    p = _panel(tmp_path, monkeypatch)
    _search(p, "grace")
    QTest.keyClicks(p.filter_input, "exo")
    _qt().processEvents()
    _search(p, "faith")
    assert _visible_books(p) == ["Exodus"] * 2
    assert p.status_label.text() == "2 of 12 verses (filter: Exodus)"


def test_filter_surfaces_matches_beyond_cap(tmp_path, monkeypatch):
    books = ["Genesis"] * 2 + ["Psalms"] * 8 + ["Exodus"] * 2
    p = _panel(tmp_path, monkeypatch, books=books, cap=10 ** 9)
    p._paint_max_initial = 5
    _search(p, "grace")
    # Parked at the cap with a show-more affordance.
    assert _buttons(p) == 1
    QTest.keyClicks(p.filter_input, "psa")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        _qt().processEvents()
        time.sleep(0.01)
        if p._paint is None:
            break
    _qt().processEvents()
    assert _visible_books(p) == ["Psalms"] * 8
    assert _buttons(p) == 0  # no stale affordance while filtered
    assert p.status_label.text() == "8 of 12 verses (filter: Psalms)"
    p.filter_clear_btn.click()
    _qt().processEvents()
    assert len(_visible_books(p)) == 12


def test_commit_keys_never_navigate(tmp_path, monkeypatch):
    from ui.widgets import predictive_input as pi
    p = _panel(tmp_path, monkeypatch)
    fired = []
    p.filter_input.advance_to_chapter.connect(lambda: fired.append("adv"))
    p.filter_input.push.connect(lambda: fired.append("push"))
    p.filter_input.book_resolved.connect(lambda s: fired.append("res"))
    QTest.keyClicks(p.filter_input, "gen")
    for key in (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_Return):
        QTest.keyClick(p.filter_input, key)
    assert fired == []
    assert p.filter_input.current_filter() == "Genesis"
    assert isinstance(p.filter_input, pi.BookInput)


def test_testament_split_guards_66_books():
    from ui.widgets.predictive_input import (
        BIBLE_BOOKS, OLD_TESTAMENT_BOOKS, NEW_TESTAMENT_BOOKS,
        GOSPELS_BOOKS)
    assert len(BIBLE_BOOKS) == 66
    assert len(OLD_TESTAMENT_BOOKS) == 39
    assert len(NEW_TESTAMENT_BOOKS) == 27
    assert "Genesis" in OLD_TESTAMENT_BOOKS
    assert "Malachi" in OLD_TESTAMENT_BOOKS
    assert "Matthew" in NEW_TESTAMENT_BOOKS
    assert "Revelation" in NEW_TESTAMENT_BOOKS
    assert GOSPELS_BOOKS == {"Matthew", "Mark", "Luke", "John"}
    assert GOSPELS_BOOKS <= NEW_TESTAMENT_BOOKS


def test_boosted_row_shows_star():
    """Popularity-boosted rows badge ★ (visible persistence proof)."""
    _qt()
    from ui.panels.fts_search_panel import _ResultRow
    plain = _ResultRow(
        {"book": "Luke", "chapter": "15", "verse_num": "11",
         "text": "t", "confidence": 90.0, "translations": []}, "luke")
    boosted = _ResultRow(
        {"book": "Luke", "chapter": "15", "verse_num": "11",
         "text": "t", "confidence": 90.0, "boosted": True,
         "translations": []}, "luke")
    try:
        plain_txt = plain.findChildren(__import__(
            "PyQt6.QtWidgets", fromlist=["QLabel"]).QLabel)[0].text()
        assert plain_txt == "90%"
        star_txt = boosted.findChildren(__import__(
            "PyQt6.QtWidgets", fromlist=["QLabel"]).QLabel)[0].text()
        assert star_txt == "★90%", star_txt
    finally:
        plain.close()
        plain.deleteLater()
        boosted.close()
        boosted.deleteLater()
        _qt().processEvents()
