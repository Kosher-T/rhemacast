"""Keyword lane: Nave's topics + Strong's lemmas as a translation-independent
search service, display-translation rendering, graceful degradation, and the
Keyword page staying pure FTS (no postings scorer merged in).
"""

import os

import pytest

import core.database as db

_REQ = [
    "data/bible/bible.db",
    "data/indexes/keywords.pkl",
]


def _needs_index():
    return pytest.mark.skipif(
        any(not os.path.exists(p) for p in _REQ),
        reason="requires bible.db + keywords.pkl")


@pytest.fixture
def _realdb(tmp_path, monkeypatch):
    """App settings DB isolated; verse reads use the real bible.db."""
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    import core.bible_service as bs
    monkeypatch.setattr(bs, "_keywords_compact", None)
    yield bs
    bs._keywords_compact = None


@_needs_index()
def test_prodigal_reaches_luke_15(_realdb):
    bs = _realdb
    res, ms, disp = bs.keyword_search("prodigal son")
    assert disp == "KJV"
    assert ms < 1000
    refs = [(r["book"], r["chapter"], r["verse_num"]) for r in res[:5]]
    assert all(b == "Luke" and c == 15 for b, c, _v in refs), refs
    assert res[0]["text"], "keyword hits carry display text"
    assert res[0]["keyword"] is True
    confs = [r["confidence"] for r in res]
    assert confs == sorted(confs, reverse=True)
    assert all(0 < c <= 100 for c in confs)


@_needs_index()
def test_lemma_synonym_beyond_verse_text(_realdb):
    """'agape' matches love-commandment verses via Strong's G25/G26."""
    bs = _realdb
    res, _ms, _disp = bs.keyword_search("agape love")
    books = {(r["book"], r["chapter"], r["verse_num"]) for r in res[:6]}
    assert ("John", 13, 34) in books or ("John", 15, 12) in books, books


@_needs_index()
def test_empty_and_stopword_queries(_realdb):
    bs = _realdb
    assert bs.keyword_search("")[0] == []
    assert bs.keyword_search("the and of")[0] == []


def test_missing_index_degrades(tmp_path, monkeypatch):
    import core.bible_service as bs
    monkeypatch.setattr(bs, "_load_keywords", lambda: None)
    res, ms, disp = bs.keyword_search("prodigal son")
    assert res == [] and ms == 0.0 and disp == "KJV"


@_needs_index()
def test_display_translation_setting(_realdb):
    bs = _realdb
    db.set_setting("search.keyword_display_translation", "ESV")
    res, _ms, disp = bs.keyword_search("prodigal son")
    assert disp == "ESV"
    assert res and all(r["version"] if "version" in r else True for r in res)
    # Text actually comes from ESV, not KJV.
    first = res[0]
    conn = bs._get_connection()
    row = conn.execute(
        "SELECT text FROM verses WHERE version = 'ESV' AND book = ? "
        "AND chapter = ? AND verse_num = ?",
        (first["book"], first["chapter"], first["verse_num"])).fetchone()
    conn.close()
    assert first["text"] == row["text"]
    assert bs.keyword_display_translation() == "ESV"


@_needs_index()
def test_invalid_display_translation_falls_back(_realdb):
    bs = _realdb
    db.set_setting("search.keyword_display_translation", "XX")
    res, _ms, disp = bs.keyword_search("prodigal son")
    assert disp == "KJV"
    assert res


@_needs_index()
def test_panel_renders_sweep_only(tmp_path):
    """The Keyword lane shows the FTS sweep, and nothing else.

    The panel used to merge a second, postings-scorer result set on top
    of the per-translation sweep; one stray query word from that scorer
    could pull unrelated verses above real hits, which is the "sticky
    after a typo" behaviour the operator reported. The lane is pure FTS
    now, so the sweep bucket IS the result list.
    """
    import time
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(["t"])
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from ui.panels import fts_search_panel as mod
    assert not hasattr(mod, "keyword_search"), (
        "the Keyword lane is pure FTS; the postings scorer must not be "
        "imported here")
    panel = mod.FtsSearchPanel()
    panel._paint_per_frame = 10 ** 9
    panel.show()
    try:
        hit11 = {"book": "Luke", "chapter": 15, "verse": 11,
                 "verse_num": 11, "text": "sweep text eleven",
                 "confidence": 90.0}
        hit12 = {"book": "Luke", "chapter": 15, "verse": 12,
                 "verse_num": 12, "text": "sweep text twelve",
                 "confidence": 70.0}
        gen = panel._search_gen + 1
        panel._search_gen = gen
        panel._gen_queries[gen] = "prodigal"
        panel._on_sweep_done(gen, {"KJV": [dict(hit11), dict(hit12)]},
                             5.0, True)
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
            if panel._paint is None:
                break
        app.processEvents()
        rows = []
        for i in range(panel.results_list.count()):
            w = panel.results_list.itemWidget(panel.results_list.item(i))
            if type(w).__name__ == "_ResultRow":
                rows.append((w._data["book"], w._data["verse_num"],
                             w._data["text"]))
        assert [(b, v) for b, v, _t in rows] == [("Luke", "11"),
                                                 ("Luke", "12")]
        assert {t for _b, _v, t in rows} == {
            "sweep text eleven", "sweep text twelve"}
    finally:
        try:
            panel.cleanup()
        except Exception:
            pass
        panel.close()
        panel.deleteLater()
        app.processEvents()
