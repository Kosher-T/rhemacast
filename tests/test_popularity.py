"""Verse popularity: operator-learned ranking weight.

Store accumulates (prompt, verse, points); matching scores prompt
overlap; boost folds into confidence. DB-backed, never raises.
"""

import logging

import core.database as db


def _fresh_db(tmp_path):
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()


def test_log_pick_upserts_and_accumulates(tmp_path):
    _fresh_db(tmp_path)
    from core.database import log_verse_pick, read_verse_popularity
    log_verse_pick("belly rivers", "John", 7, 38, 1)
    log_verse_pick("belly rivers", "John", 7, 38, 5)
    rows = read_verse_popularity()
    assert len(rows) == 1
    assert rows[0]["points"] == 6.0
    assert rows[0]["picks"] == 2


def test_multi_prompt_same_verse_kept(tmp_path):
    """Old prompts are never collapsed: same verse, two phrasings."""
    _fresh_db(tmp_path)
    from core.database import log_verse_pick, read_verse_popularity
    log_verse_pick("belly rivers", "John", 7, 38, 1)
    log_verse_pick("living water belly", "John", 7, 38, 1)
    rows = [r for r in read_verse_popularity() if r["book"] == "John"]
    assert len(rows) == 2


def test_cap_prunes_oldest(tmp_path, monkeypatch):
    _fresh_db(tmp_path)
    import core.constants as const
    from core.database import log_verse_pick, read_verse_popularity
    monkeypatch.setattr(const, "POPULARITY_MAX_PROMPTS", 3)
    for i in range(5):
        log_verse_pick(f"prompt {i}", "Gen", 1, 1, 1)
    rows = read_verse_popularity()
    assert len(rows) == 3
    assert {r["prompt"] for r in rows} == {"prompt 2", "prompt 3", "prompt 4"}


def test_log_pick_never_raises(tmp_path):
    _fresh_db(tmp_path)
    from core.database import log_verse_pick, read_verse_popularity
    log_verse_pick("", "John", 7, 38, 1)  # blank prompt ignored
    log_verse_pick("q", "", 7, 38, 1)  # blank book ignored
    log_verse_pick(None, None, None, None, None)
    assert read_verse_popularity() == []


def test_overlap_threshold_and_symmetry():
    from core.bible_service import _prompt_overlap
    assert _prompt_overlap({"a", "b"}, "a b c") == 1.0
    assert _prompt_overlap({"a", "b", "c", "d"}, "a b") == 1.0
    assert _prompt_overlap({"a", "x"}, "a b") == 0.5
    assert _prompt_overlap({"x", "y"}, "a b") == 0.0
    assert _prompt_overlap(set(), "a b") == 0.0


def test_boost_curve_nudge_then_dominate(tmp_path):
    """Clustered confidences (real RRF shape): one pick nudges within
    striking distance; dozens topple; weights order navigate < live."""
    _fresh_db(tmp_path)
    from core.bible_service import apply_popularity, popularity_boosts
    from core.database import log_verse_pick

    def _rows():
        return [
            {"book": "John", "chapter": 7, "verse": 38,
             "verse_num": 38, "text": "a", "confidence": 50.0},
            {"book": "Job", "chapter": 5, "verse": 27,
             "verse_num": 27, "text": "b", "confidence": 49.2},
            {"book": "Ezekiel", "chapter": 34, "verse": 8,
             "verse_num": 8, "text": "c", "confidence": 48.4},
            {"book": "Jonah", "chapter": 2, "verse": 1,
             "verse_num": 1, "text": "d", "confidence": 47.7},
            {"book": "Psalms", "chapter": 44, "verse": 25,
             "verse_num": 25, "text": "e", "confidence": 46.9},
        ]

    target = ("jonah", "2", "1")
    log_verse_pick("belly flow", "Jonah", 2, 1, 1)  # one navigate
    boosted = apply_popularity(_rows(), popularity_boosts("belly flow"))
    order = [(r["book"], r["confidence"]) for r in boosted]
    assert order[0][0] == "John"  # not topped by one pick
    assert order[2][0] == "Jonah"  # nudged up one
    assert boosted[2]["confidence"] > 47.7

    for _ in range(20):
        log_verse_pick("belly flow", "Jonah", 2, 1, 5)  # live picks
    boosted = apply_popularity(_rows(), popularity_boosts("belly flow"))
    assert boosted[0]["book"] == "Jonah"  # eventually tops

    # Partial overlap still counts (added one word).
    boosted = apply_popularity(
        _rows(), popularity_boosts("belly flow rivers"))
    assert boosted[0]["book"] == "Jonah"

    # Unrelated prompt untouched.
    untouched = apply_popularity(
        _rows(), popularity_boosts("noah ark"))
    assert [r["book"] for r in untouched] == [
        "John", "Job", "Ezekiel", "Jonah", "Psalms"]
    assert untouched[3]["confidence"] == 47.7


def test_boost_weights_ordering(tmp_path):
    """Same verse, one pick each: live > schedule > navigate."""
    _fresh_db(tmp_path)
    from core.bible_service import apply_popularity, popularity_boosts
    from core.database import log_verse_pick
    from core.constants import (POPULARITY_POINTS_NAVIGATE,
                                POPULARITY_POINTS_SCHEDULE,
                                POPULARITY_POINTS_LIVE)
    assert POPULARITY_POINTS_NAVIGATE < POPULARITY_POINTS_SCHEDULE \
        < POPULARITY_POINTS_LIVE
    log_verse_pick("q one", "Gen", 1, 1, POPULARITY_POINTS_NAVIGATE)
    log_verse_pick("q two", "Gen", 1, 2, POPULARITY_POINTS_SCHEDULE)
    log_verse_pick("q three", "Gen", 1, 3, POPULARITY_POINTS_LIVE)
    boosts = popularity_boosts("q")
    assert boosts[("gen", "1", "1")] < boosts[("gen", "1", "2")] \
        < boosts[("gen", "1", "3")]


def test_boost_diacritic_symmetry(tmp_path):
    _fresh_db(tmp_path)
    from core.bible_service import popularity_boosts
    from core.database import log_verse_pick
    log_verse_pick("Yorùbá praise", "Psa", 100, 1, 5)
    assert ("psa", "100", "1") in popularity_boosts("yoruba praise")
    assert ("psa", "100", "1") in popularity_boosts("yorùbá praise")


def test_inflection_forgiveness(tmp_path):
    """Cross-session rephrasing with different inflections still counts."""
    _fresh_db(tmp_path)
    from core.bible_service import popularity_boosts
    from core.database import log_verse_pick
    log_verse_pick("love one another", "John", 13, 34, 5)
    assert ("john", "13", "34") in popularity_boosts("loved one another")
    assert ("john", "13", "34") in popularity_boosts("loving one another")


def test_boosted_flag_marks_bumped_rows(tmp_path):
    """apply_popularity tags exactly the rows it lifts (★ affordance)."""
    _fresh_db(tmp_path)
    from core.bible_service import apply_popularity, popularity_boosts
    from core.database import log_verse_pick
    log_verse_pick("belly flow", "Jonah", 2, 1, 5)
    rows = [
        {"book": "Jonah", "chapter": 2, "verse": 1,
         "verse_num": 1, "text": "a", "confidence": 40.0},
        {"book": "Job", "chapter": 5, "verse": 27,
         "verse_num": 27, "text": "b", "confidence": 49.2},
    ]
    out = apply_popularity(rows, popularity_boosts("belly flow"))
    by_book = {r["book"]: r for r in out}
    assert by_book["Jonah"].get("boosted") is True
    assert "boosted" not in by_book["Job"]


def test_boosted_confidence_never_exceeds_100():
    """Confidence is a percentage. A heavily-picked verse whose base score
    is already high must not render as "104%".

    The cap is on the DISPLAYED value only: the uncapped score is kept in
    confidence_rank so that capping cannot flatten the ordering. A verse
    far below the cap is unaffected.
    """
    from core.bible_service import apply_popularity

    # keys are stringified book/chapter/verse, as apply_popularity builds them
    results = [{"book": "Gen", "chapter": 1, "verse_num": 1,
                "confidence": 98.0}]
    apply_popularity(results, {("gen", "1", "1"): 50.0})
    assert results[0]["confidence"] == 100.0, results[0]["confidence"]
    assert results[0]["confidence_rank"] > 100.0, "uncapped score kept"
    assert results[0]["boosted"] is True

    low = [{"book": "Gen", "chapter": 1, "verse_num": 2,
            "confidence": 10.0}]
    apply_popularity(low, {("gen", "1", "2"): 0.5})
    assert 10.0 < low[0]["confidence"] < 100.0


def test_cap_does_not_flatten_the_ranking():
    """Two verses that both saturate at 100% must still be ordered by the
    boost, not by input order.

    This is why the cap lives on the display value only: capping both
    would tie them, and a stable sort would then hand the top slot to
    whichever happened to be found first.
    """
    from core.bible_service import apply_popularity

    results = [
        {"book": "Gen", "chapter": 1, "verse_num": 1,
         "text": "unboosted", "confidence": 100.0},
        {"book": "Gen", "chapter": 1, "verse_num": 2,
         "text": "boosted", "confidence": 99.0},
    ]
    apply_popularity(results, {("gen", "1", "2"): 5.0})
    assert [r["text"] for r in results][0] == "boosted", (
        "the boosted verse must win even though both display as 100%")
    assert all(r["confidence"] <= 100.0 for r in results)
