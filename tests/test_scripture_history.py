"""Scripture history panel in the SCRIPTURE tab's right rail.

Covers the "no consecutive duplicates" recording rule, the DB backfill
(raw log in, collapsed view out — deck slides and clears excluded) and
the single/double click signals. The raw display log itself is never
rewritten; dedupe is a view rule.

Offscreen Qt; WebEngine pre-import first — same ordering rule as the
serialize tests, else later UI imports break in-process.
"""

import os

# Forced (not setdefault): the shell may export QT_QPA_PLATFORM=wayland,
# under which headless windows never activate and real focus is untestable.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import pytest

import core.database as db
import ui.styles  # noqa: F401  (theme must exist before panels import it)

_app = None


def _qt():
    # One QApplication per pytest process: a second instance corrupts
    # native state (WebEngine) and core-dumps the suite.
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    return db.DB_PATH


def _panel(db_path):
    _qt()
    assert db.DB_PATH == db_path
    from ui.panels.scripture_history_panel import ScriptureHistoryPanel
    p = ScriptureHistoryPanel()
    p.show()
    _qt().processEvents()
    return p


def _broadcast_verse(book: str, chapter: str, verse: str,
                     translation: str, text: str = "verse body"):
    """Log one verse display exactly the way _broadcast_to_ws does."""
    payload = {
        "reference": f"{book} {chapter}:{verse}",
        "text": text,
        "translation": translation,
        "theme": "",
    }
    db.log_live_payload(payload, kind="verse")


def test_record_skips_only_consecutive_duplicates(tmp_path, monkeypatch):
    p = _panel(_fresh_db(tmp_path, monkeypatch))

    def verse(v):
        return {"book": "John", "chapter": "3", "verse_num": v,
                "version": "kjv", "text": "..."}

    assert p.record_display(verse("16")) is True
    # Same verse pushed again right away — rows stay one.
    assert p.record_display(verse("16")) is False
    assert len(p._rows) == 1

    # A different verse breaks the streak; the first can come back.
    assert p.record_display(verse("17")) is True
    assert p.record_display(verse("16")) is True
    refs = [r["display_ref"] for r in p._rows]
    assert refs == ["John 3:16", "John 3:17", "John 3:16"]


def test_record_ignores_slides_clears_and_half_verses(tmp_path, monkeypatch):
    p = _panel(_fresh_db(tmp_path, monkeypatch))

    # Slide-flavoured dicts and clears never carry a full reference.
    assert p.record_display({}) is False
    assert p.record_display({"book": "John", "chapter": "3"}) is False
    assert p.record_display(None) is False
    assert p._rows == []
    # And the raw log was never touched.
    assert db.get_scripture_display_history() == []


def test_db_backfill_collapses_consecutive_duplicates(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)

    _broadcast_verse("John", "3", "16", "King James Version")
    _broadcast_verse("John", "3", "16", "King James Version")   # raw repeat
    _broadcast_verse("John", "3", "17", "King James Version")
    _broadcast_verse("John", "3", "16", "King James Version")   # comes back

    assert len(db.get_scripture_display_history()) == 4  # raw log keeps all

    p = _panel(str(tmp_path / "app.db"))
    refs = [r["display_ref"] for r in p._rows]
    assert refs == ["John 3:16", "John 3:17", "John 3:16"]
    # Rows display the translation NAME (never the Schedule [NIV] prefix;
    # backfilled refs keep the same "Book C:V" shape as live records).
    assert all("[" not in r["display_ref"] for r in p._rows)


def test_hydrate_reads_only_the_current_session(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)

    # A session that already ended pushed a verse — dead to this panel.
    db.log_display_event("dead-session", "display", "verse",
                         "[King James Version] John 3:16", "...",
                         "King James Version", "")
    _broadcast_verse("Psalm", "119", "105", "King James Version")

    p = _panel(str(tmp_path / "app.db"))
    refs = [r["display_ref"] for r in p._rows]
    assert refs == ["Psalm 119:105"]


def test_hydrate_excludes_older_app_runs(tmp_path, monkeypatch):
    """A session is one app run: rows stamped before this boot are a
    finished run's details — visible display actions here must never
    resurrect them, even in the same 'global' bucket."""
    _fresh_db(tmp_path, monkeypatch)
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO display_events (session_id, action, ref, text,"
        " translation, theme, kind, timestamp_ms)"
        " VALUES ('global', 'display', 'verse',"
        " '[King James Version] Genesis 1:1', 'old-run',"
        " 'King James Version', 'verse', ?)",
        (db.APP_SESSION_STARTED_MS - 60000,),
    )
    conn.commit()
    conn.close()

    _broadcast_verse("Genesis", "1", "2", "King James Version")

    p = _panel(str(tmp_path / "app.db"))
    refs = [r["display_ref"] for r in p._rows]
    assert refs == ["Genesis 1:2"]


def test_rows_wipe_when_the_session_ends(tmp_path, monkeypatch):
    """A new transcription session wipes the log mid-run."""
    import threading

    _fresh_db(tmp_path, monkeypatch)
    import core.service_manager as sm
    import core.stt_inference as stt

    p = _panel(str(tmp_path / "app.db"))
    assert p.record_display({"book": "John", "chapter": "3",
                             "verse_num": "16", "version": "kjv",
                             "text": "..."}) is True
    assert len(p._rows) == 1

    # Flip to a live transcription session: next record wipes first.
    live = threading.Event()
    live.set()
    monkeypatch.setattr(sm, "service_active", live)
    monkeypatch.setattr(stt, "_stt_running", live)
    monkeypatch.setattr(stt, "session_id", "sess-live", raising=False)

    assert p._current_session() == "sess-live"
    assert p.record_display({"book": "John", "chapter": "3",
                             "verse_num": "17", "version": "kjv",
                             "text": "..."}) is True
    refs = [r["display_ref"] for r in p._rows]
    assert refs == ["John 3:17"], "old session's rows are gone"
    assert p._session_id == "sess-live"

    # The panel revealing again re-checks the session id it holds.
    off = threading.Event()  # session over → back to 'global'
    monkeypatch.setattr(sm, "service_active", off)
    p._on_revealed()
    assert not p._rows, "reveal after session end wipes instead of showing"
    assert p._session_id == "global" or p._rows == []


def test_db_backfill_excludes_slides_and_clears(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)

    _broadcast_verse("Psalm", "119", "105", "King James Version")
    db.log_live_payload({"action": "clear"}, kind="verse")
    db.log_live_payload({"text": "slide words", "reference": "Deck 1 slide 2"},
                        kind="slide")
    _broadcast_verse("John", "3", "16", "King James Version")

    p = _panel(str(tmp_path / "app.db"))
    refs = [r["display_ref"] for r in p._rows]
    assert refs == ["Psalm 119:105", "John 3:16"]


def test_backfill_maps_display_names_to_codes(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from core.bible_service import get_display_name, get_available_translations
    code = None
    for c in get_available_translations():
        if get_display_name(c) == "King James Version":
            code = c
            break

    _broadcast_verse("John", "3", "16", "King James Version")
    p = _panel(str(tmp_path / "app.db"))
    entry = p._rows[0]
    assert entry["display_translation"] == "King James Version"
    assert entry["version"] == code or code is None


def test_click_signals_carry_navigable_scriptures(tmp_path, monkeypatch):
    p = _panel(_fresh_db(tmp_path, monkeypatch))

    selected, pushed = [], []
    p.verse_selected.connect(selected.append)
    p.verse_double_clicked.connect(pushed.append)

    assert p.record_display({"book": "John", "chapter": "3",
                             "verse_num": "16", "version": "kjv",
                             "text": "For God so loved..."}) is True

    row = p._list.itemAt(0).widget()
    QTest.mouseClick(row, Qt.MouseButton.LeftButton)
    QTest.mouseDClick(row, Qt.MouseButton.LeftButton)
    _qt().processEvents()

    assert len(selected) == 1 and len(pushed) == 1
    for entry in selected + pushed:
        assert entry["book"] == "John"
        assert entry["chapter"] == "3"
        assert entry["verse_num"] == "16"
        assert entry["version"] == "kjv"


def test_empty_state_shows_until_first_row(tmp_path, monkeypatch):
    p = _panel(_fresh_db(tmp_path, monkeypatch))
    assert p._empty.isVisible() and not p._scroll.isVisible()

    p.record_display({"book": "Ps", "chapter": "119", "verse_num": "1",
                      "version": "kjv"})
    _qt().processEvents()
    assert not p._empty.isVisible() and p._scroll.isVisible()


def test_new_rows_autoscroll_the_list_to_the_end(tmp_path, monkeypatch):
    """Every insert demands a ride to bottom; when the panel was laid out
    before the viewport had a range (hidden tab, boot backfill) the
    rangeChanged hook finishes it the moment there is something to scroll."""
    p = _panel(_fresh_db(tmp_path, monkeypatch))
    for i in range(5):
        p.record_display({"book": "Prov", "chapter": str(i // 3 + 1),
                          "verse_num": str(i % 3 + 1), "version": "kjv"})

    bar = p._scroll.verticalScrollBar()
    assert p._pending_scroll, "an insert must demand a scroll to end"

    # A range materialising later (layout, show after hidden backfill)
    # completes the demand — no geometry pass available offscreen.
    bar.setRange(0, 0)
    p._on_range_changed(0, 0)
    assert p._pending_scroll, "no range yet: the demand stays"

    bar.setRange(0, 1000)
    p._on_range_changed(0, 1000)
    assert bar.value() == bar.maximum() == 1000
    assert not p._pending_scroll, "demand fulfilled, not re-fired"

    # Subsequent appends keep following the end (a live range completes
    # the demand in the same synchronous call).
    p.record_display({"book": "John", "chapter": "3", "verse_num": "16",
                      "version": "kjv"})
    assert bar.value() == bar.maximum() and not p._pending_scroll
