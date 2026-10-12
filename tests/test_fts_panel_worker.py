"""FTS panel worker: searches run off the GUI thread, generations gate
painting (stale sweeps never render), rapid queries coalesce.
"""

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


def _panel(tmp_path, monkeypatch):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from ui.panels import fts_search_panel as mod
    calls = []

    def fake_hybrid(query, version, limit=30):
        calls.append((query, version))
        time.sleep(0.05)
        return [{"book": "Gen", "chapter": 1, "verse": 1,
                 "verse_num": 1, "text": f"hit for {query} ({version})",
                 "confidence": 9.0}]

    monkeypatch.setattr(mod, "fts_search", fake_hybrid)
    monkeypatch.setattr(
        mod, "keyword_search", lambda query, limit=30: ([], 0.0, "KJV"))
    panel = mod.FtsSearchPanel()
    panel._paint_per_frame = 10 ** 9  # deterministic: paint all at once
    panel.show()
    _qt().processEvents()
    _OPEN.append(panel)
    return panel, calls


def _paint_settled(panel) -> bool:
    """Paint chain done OR parked on the show-more affordance."""
    state = panel._paint
    if state is None:
        return True
    cap = len(state["verses"]) if state.get("expanded") else min(
        len(state["verses"]), panel._paint_max_initial)
    return state.get("pos", 0) >= cap


def _settle(panel, timeout_s: float = 8.0):
    """Process events until no sweep/paint is running or pending."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _qt().processEvents()
        fut = panel._search_future
        if (fut is None or fut.done()) and panel._search_pending is None \
                and _paint_settled(panel):
            _qt().processEvents()
            _qt().processEvents()
            return True
        time.sleep(0.02)
    return False


def _row_texts(panel):
    out = []
    for i in range(panel.results_list.count()):
        widget = panel.results_list.itemWidget(panel.results_list.item(i))
        out.append(widget._data["text"] if hasattr(widget, "_data") else "")
    return out


def test_latest_query_wins_and_renders(tmp_path, monkeypatch):
    panel, calls = _panel(tmp_path, monkeypatch)
    panel.query_input.setText("first query")
    panel._debounce_timer.stop()
    panel._execute_search()
    panel.query_input.setText("second query")
    panel._debounce_timer.stop()
    panel._execute_search()
    assert _settle(panel), "sweep did not settle"
    texts = _row_texts(panel)
    assert texts, "nothing rendered"
    assert all("second query" in t for t in texts), texts
    assert all("first query" not in t for t in texts)
    assert "ms" in panel.status_label.text()


def test_empty_query_clears_and_invalidates(tmp_path, monkeypatch):
    panel, calls = _panel(tmp_path, monkeypatch)
    panel.query_input.setText("something")
    panel._debounce_timer.stop()
    panel._execute_search()
    panel.query_input.setText("")
    panel._execute_search()
    assert _settle(panel)
    assert panel.results_list.count() == 0


def test_sweep_runs_off_gui_thread(tmp_path, monkeypatch):
    """Worker thread ids differ from the GUI thread id."""
    import threading
    panel, calls = _panel(tmp_path, monkeypatch)
    from ui.panels import fts_search_panel as mod
    seen = []

    def fake_hybrid(query, version, limit=30):
        seen.append(threading.get_ident())
        return []

    monkeypatch.setattr(mod, "fts_search", fake_hybrid)
    monkeypatch.setattr(
        mod, "keyword_search", lambda query, limit=30: ([], 0.0, "KJV"))
    panel.query_input.setText("thread check")
    panel._debounce_timer.stop()
    panel._execute_search()
    assert _settle(panel)
    gui_ident = threading.get_ident()
    assert seen and all(i != gui_ident for i in seen)


def test_chunked_paint_matches_oneshot(tmp_path, monkeypatch):
    """Progressive frames paint exactly what one shot would."""
    panel, _calls = _panel(tmp_path, monkeypatch)
    panel._paint_per_frame = 7
    rows = [{"book": "Gen", "chapter": 1, "verse": i, "verse_num": i,
             "text": f"verse text {i}", "confidence": float(90 - i),
             "version": "KJV"}
            for i in range(1, 41)]
    panel.query_input.setText("chunk check")
    panel._debounce_timer.stop()
    panel._render_results("chunk check", rows, 12.0)
    assert _settle(panel)
    assert panel.results_list.count() == 40
    assert panel.results_list.itemWidget(
        panel.results_list.item(0))._data["verse_num"] == "1"
    assert "40 verses" in panel.status_label.text()

    panel2, _ = _panel(tmp_path, monkeypatch)
    panel2._paint_per_frame = 10 ** 9
    panel2._render_results("chunk check", rows, 12.0)
    assert _settle(panel2)
    assert panel2.results_list.count() == 40
    texts = lambda p: [p.results_list.itemWidget(p.results_list.item(i))._data["text"]
                       for i in range(p.results_list.count())]
    assert texts(panel) == texts(panel2)


def test_result_row_highlights_matched_surfaces(tmp_path, monkeypatch):
    from ui.panels.fts_search_panel import _ResultRow
    _qt()
    from PyQt6.QtWidgets import QLabel
    data = {"book": "John", "chapter": 10, "verse_num": 14, "verse": 14,
            "text": "I am the good shepherd", "confidence": 50.0}
    w = _ResultRow(data, "shepard", highlight_words=["shepherd"])
    try:
        html = " ".join(l.text() for l in w.findChildren(QLabel))
        assert "<span" in html and "shepherd" in html
        plain = _ResultRow(data, "shepard")
        try:
            html2 = " ".join(l.text() for l in plain.findChildren(QLabel))
            assert "<span" not in html2  # query word absent: no glow
        finally:
            plain.deleteLater()
    finally:
        w.deleteLater()


def test_render_cap_and_show_more(tmp_path, monkeypatch):
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QPushButton
    panel, _calls = _panel(tmp_path, monkeypatch)
    panel._paint_per_frame = 10
    panel._paint_max_initial = 15
    rows = [{"book": "Gen", "chapter": 1, "verse": i, "verse_num": i,
             "text": f"verse text {i}", "confidence": float(90 - i),
             "version": "KJV"}
            for i in range(1, 41)]
    panel._render_results("cap check", rows, 12.0)
    assert _settle(panel)
    # 15 rows + 1 show-more button row (button text carries the total).
    assert panel.results_list.count() == 16
    btns = panel.results_list.findChildren(
        QPushButton, "ShowMoreButton")
    assert len(btns) == 1 and "40" in btns[0].text()
    QTest.mouseClick(btns[0], Qt.MouseButton.LeftButton)
    assert _settle(panel)
    assert panel.results_list.count() == 40
    assert "40 verses" in panel.status_label.text()


def test_pop_picks_logged_with_weights(tmp_path, monkeypatch):
    from core.database import read_verse_popularity
    panel, _calls = _panel(tmp_path, monkeypatch)
    panel.query_input.setText("belly flow")
    panel._debounce_timer.stop()
    panel._execute_search()
    assert _settle(panel)
    verse = {"book": "Jonah", "chapter": 2, "verse_num": 1, "verse": 1,
             "text": "x", "confidence": 10.0}
    panel.verse_to_navigator.emit(dict(verse))
    panel.verse_to_schedule.emit(dict(verse))
    panel.verse_to_live.emit(dict(verse))
    rows = [r for r in read_verse_popularity() if r["book"] == "Jonah"]
    assert len(rows) == 1
    assert rows[0]["prompt"] == "belly flow"
    assert rows[0]["points"] == 1 + 3 + 5
    assert rows[0]["picks"] == 3


def test_pop_boost_lifts_repeat_pick(tmp_path, monkeypatch):
    """A heavily picked verse climbs to the top on re-search."""
    from ui.panels import fts_search_panel as mod
    from core.database import log_verse_pick
    _qt()
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()

    def fake_hybrid(query, version, limit=30):
        return [{"book": f"Book{version}", "chapter": 1, "verse": 1,
                 "verse_num": 1, "text": f"hit {version}",
                 "confidence": 50.0}]

    monkeypatch.setattr(mod, "fts_search", fake_hybrid)
    monkeypatch.setattr(
        mod, "keyword_search", lambda query, limit=30: ([], 0.0, "KJV"))
    panel = mod.FtsSearchPanel()
    panel._paint_per_frame = 10 ** 9
    panel.show()
    _qt().processEvents()
    _OPEN.append(panel)
    panel.query_input.setText("belly flow")
    panel._debounce_timer.stop()
    panel._execute_search()
    assert _settle(panel)
    first_order = [panel.results_list.itemWidget(
        panel.results_list.item(i))._data["book"]
        for i in range(panel.results_list.count())]
    assert set(first_order) == {f"Book{v}" for v in
                                ["KJV", "NKJV", "ESV", "NLT", "AMP", "BSB"]}
    for _ in range(15):
        log_verse_pick("belly flow", "BookBSB", 1, 1, 5)
    panel._execute_search()
    assert _settle(panel)
    order = [panel.results_list.itemWidget(
        panel.results_list.item(i))._data["book"]
        for i in range(panel.results_list.count())]
    assert order[0] == "BookBSB"


def test_pop_logging_is_private(tmp_path, monkeypatch, caplog):
    import logging
    panel, _calls = _panel(tmp_path, monkeypatch)
    panel.query_input.setText("quiet please")
    panel._debounce_timer.stop()
    panel._execute_search()
    assert _settle(panel)
    with caplog.at_level(logging.DEBUG):
        panel.verse_to_navigator.emit(
            {"book": "Gen", "chapter": 1, "verse": 1, "text": "x"})
    loud = [r for r in caplog.records if r.levelno >= logging.INFO]
    assert not any("Popularity" in r.getMessage() for r in loud)
