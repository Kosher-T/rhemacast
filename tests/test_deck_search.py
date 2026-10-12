"""Deck search: prefix-stable recall + vernacular folding.

Uses real tmp databases through the service layer (both FTS tables,
rebuild path included).
"""

import core.database as db


def _fresh_db(tmp_path):
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()


def _seed(tp):
    from core.slide_service import create_deck
    create_deck("# Amazing Grace\n\n\n*Verse\nAmazing grace how sweet the sound\n")
    create_deck("# Amen It Is So\n\n\n*Chorus\nAmen, amen, it is so\n")
    create_deck("# A Mighty King\n\n\n*Verse\nOyo yiri kokroko, he is a mighty king\n")
    create_deck("# Yoruba Praise\n\n\n*Chorus\nYorùbá ni mímọ́, ẹni mimọ́\n")
    create_deck("# Evening Worship\n\n\n*Verse\nSoldier on for the Lord\n\n\n*Chorus\nWe keep worshipping\n")
    create_deck("# I Bow - Judikay\n\n\n*Verse\nI bow before the King\n")
    create_deck("# Crossover Service\n\n\n*Verse\nShout for joy\n")


def _ids(rows):
    return {d["id"] for d in rows}


def test_keystroke_narrowing_property(tmp_path):
    """Every added character narrows (or holds) — never reshuffles."""
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import search_decks
    query = "amen it is so"
    prev = None
    for i in range(1, len(query) + 1):
        cur = _ids(search_decks(query[:i]))
        assert cur, f"empty at prefix {query[:i]!r}"
        if prev is not None:
            assert cur <= prev, (
                f"{query[:i]!r} added results vs {query[:i-1]!r}: "
                f"{cur - prev}")
        prev = cur


def test_single_char_prefix_broad_then_narrows(tmp_path):
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import search_decks
    s = _ids(search_decks("s"))
    assert s, "single-char prefix must match s-words"
    assert _ids(search_decks("so")) <= s


def test_trailing_space_is_noop(tmp_path):
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import search_decks
    # A trailing space starts no new word: identical results (pure filter).
    assert _ids(search_decks("amen ")) == _ids(search_decks("amen"))


def test_diacritics_both_ways(tmp_path):
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import search_decks
    plain = _ids(search_decks("yoruba"))
    folded = _ids(search_decks("yorùbá"))
    assert plain and folded and plain == folded
    titles = [d["title"] for d in search_decks("mimo")]
    assert any("Yoruba" in t for t in titles)


def test_stemming_survives_for_complete_words(tmp_path):
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import search_decks
    # Completed (non-last) words stay porter-stemmed: "soldiers" as a
    # complete word matches the "soldier" lyric.
    assert any("Evening" in d["title"] for d in search_decks("soldiers fo"))
    # Last word is always a pure prefix (filter narrowing).
    assert any("Evening" in d["title"]
               for d in search_decks("lord worshipping"))
    assert any("Evening" in d["title"] for d in search_decks("soldier"))


def test_stem_hole_closed_on_prefix(tmp_path):
    """porter alone misses mid-suffix prefixes (runni*); the unstemmed
    table must still match."""
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import create_deck, search_decks
    create_deck("# Running Song\n\n\n*Verse\nWe are running on\n")
    assert any("Running" in d["title"] for d in search_decks("runni"))
    assert any("Running" in d["title"] for d in search_decks("running"))


def test_syntax_safety(tmp_path):
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import search_decks
    for q in ['"amen', "amen*", "a:b", "(amen", "amen-", "amen+it",
              "~amen", "amen^2", "amen OR it", "***", "   ", ""]:
        assert isinstance(search_decks(q), list)


def test_tags_searchable(tmp_path):
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import create_deck, search_decks
    create_deck("# Tagged Song\n\n\n*Verse\nLa la la\n", tags="crossover christmas")
    assert any("Tagged" in d["title"] for d in search_decks("crossover"))
    assert any("Tagged" in d["title"] for d in search_decks("christma"))


def test_title_match_ranks_first(tmp_path):
    _fresh_db(tmp_path)
    _seed(tmp_path)
    from core.slide_service import search_decks
    rows = search_decks("judikay")
    assert rows and "Judikay" in rows[0]["title"]


def test_legacy_index_rebuilds_with_prefix(tmp_path):
    """An old-definitions DB heals on open: diacritics + prefix work."""
    import sqlite3
    _fresh_db(tmp_path)
    _seed(tmp_path)
    con = sqlite3.connect(str(tmp_path / "app.db"))
    con.executescript("""
        DROP TABLE IF EXISTS slides_fts_prefix;
        DROP TABLE IF EXISTS slides_fts_prefix_data;
        DROP TABLE IF EXISTS slides_fts_prefix_idx;
        DROP TABLE IF EXISTS slides_fts_prefix_docsize;
        DROP TABLE IF EXISTS slides_fts_prefix_config;
        DROP TABLE IF EXISTS slides_fts;
        DROP TABLE IF EXISTS slides_fts_data;
        DROP TABLE IF EXISTS slides_fts_idx;
        DROP TABLE IF EXISTS slides_fts_docsize;
        DROP TABLE IF EXISTS slides_fts_config;
        CREATE VIRTUAL TABLE slides_fts USING fts5(
            title, slide_text, tags,
            content='', content_rowid='id',
            tokenize='porter unicode61',
            contentless_delete=1
        );
    """)
    con.execute(
        "INSERT INTO slides_fts(rowid, title, slide_text, tags) "
        "SELECT id, title, '', '' FROM slide_decks")
    con.commit()
    con.close()
    db.init_db()  # must detect + rebuild both tables
    con = sqlite3.connect(str(tmp_path / "app.db"))
    assert con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='slides_fts_prefix'").fetchone() is not None
    assert "remove_diacritics" in con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='slides_fts'").fetchone()[0]
    con.close()
    from core.slide_service import search_decks
    assert any("Yoruba" in d["title"] for d in search_decks("yoruba"))
    assert any("Yoruba" in d["title"] for d in search_decks("yoru"))
