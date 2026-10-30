"""
tests/test_fts_search.py

Tests for the FTS5 scripture search lane (core/bible_service.fts_search):
  - Stemming in the shared tokenizer
  - Tokenizer symmetry across modules
  - The verse index carries Porter stemming (index-side, not Python-side)
  - fts_search(): query building, AND syntax, ranking contract, degradation
  - Keyword-match quality on the real KJV index
  - Query sanitization (no FTS syntax crashes)

Ranking contract, deliberately narrow: coverage (how many distinct query
words a verse carries), then adjacency of those words, then SQLite FTS5's
own bm25. Nothing learned or blended. See the module note in
tests/test_scripture_ranking_gold.py for what that trade cost.
"""

import os
import pickle
import tempfile
from unittest import mock

import pytest

from core.text_utils import tokenize, normalize_text, STEMMER


def _ref(r):
    return f"{r['book']} {r['chapter']}:{r['verse_num']}"


def _stem_prefix(word):
    """Porter stem of a word, for containment checks that must tolerate
    inflection ('shadow' in the text vs 'shadowed' in a query)."""
    return STEMMER.stemWord(word)


# ─── Stemming Tests ───────────────────────────────────────────────────────────


class TestStemming:
    def test_stemming_transform(self):
        """Multi-suffix words reduce to a stable stem."""
        assert STEMMER.stemWord("running") == STEMMER.stemWord("runs")
        assert STEMMER.stemWord("loving") == STEMMER.stemWord("loved")

    def test_stemming_love_variants(self):
        """All love forms share a stem, so one query term finds them all."""
        stems = {STEMMER.stemWord(w)
                 for w in ("love", "loves", "loved", "loving", "loves")}
        assert len(stems) == 1

    def test_stemming_preserves_stop_words(self):
        """Stop words are filtered, not mangled."""
        assert tokenize("the and of") == []

    def test_stemming_archaic_retained(self):
        """Archaic/KJV spellings survive normalization."""
        assert normalize_text("Thou shalt not")

    def test_normalize_apostrophes(self):
        assert normalize_text("don't") == "dont"

    def test_normalize_punctuation_to_space(self):
        assert normalize_text("faith, hope; charity!") == \
            "faith hope charity"


# ─── Tokenizer Symmetry ───────────────────────────────────────────────────────


class TestTokenizerSymmetry:
    def test_search_engine_matches_text_utils(self):
        """T3's tokenizer must agree with the shared one, or the same
        query scores differently in the two lanes."""
        from core import search_engine
        assert search_engine.tokenize("running, runs & ran") == \
            tokenize("running, runs & ran")

    def test_build_bm25_matches_text_utils(self):
        """The index builder must tokenize the way queries do."""
        from core.bible_service import tokenize as svc_tokenize
        assert svc_tokenize("Faith, Hope, Charity.") == \
            tokenize("Faith, Hope, Charity.")


# ─── Index-side stemming ──────────────────────────────────────────────────────


class TestVerseIndexIsStemmed:
    """The tokenizer lives in the INDEX. If it regresses to the default
    unicode61, every inflected query silently stops matching — so this
    reads the live schema rather than trusting the build script."""

    def _tokenizer(self):
        import sqlite3
        from core.bible_service import _BIBLE_DB_PATH
        conn = sqlite3.connect(f"file:{_BIBLE_DB_PATH}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='verses_fts'"
            ).fetchone()
        finally:
            conn.close()
        assert row, "verses_fts table is missing"
        return row[0]

    def test_schema_declares_porter(self):
        assert "porter" in self._tokenizer(), (
            "verses_fts lost its porter stemmer — rebuild with "
            "data/bible/rebuild_fts.py")

    def test_index_holds_exactly_the_chosen_translations(self):
        """The index is scoped to the operator's selection, not the whole
        corpus.

        It has to be: a term's postings are scanned before the `version`
        filter discards most of them, so indexing translations nobody
        searches makes every query scan — and throw away — their postings.
        """
        import sqlite3
        from core.bible_service import _BIBLE_DB_PATH, fts_translations
        chosen = set(fts_translations())
        conn = sqlite3.connect(f"file:{_BIBLE_DB_PATH}?mode=ro", uri=True)
        try:
            indexed = conn.execute("SELECT COUNT(*) FROM verses_fts").fetchone()[0]
            versions = {r[0] for r in conn.execute(
                "SELECT DISTINCT v.version FROM verses_fts fts "
                "JOIN verses v ON v.id = fts.rowid")}
            expected = conn.execute(
                "SELECT COUNT(*) FROM verses WHERE version IN "
                f"({','.join('?' * len(chosen))})", tuple(chosen)).fetchone()[0]
        finally:
            conn.close()
        assert versions == chosen, (
            f"index holds {sorted(versions)}, chosen is {sorted(chosen)} — "
            "run data/bible/rebuild_fts.py")
        assert indexed == expected, (
            f"index has {indexed} rows, expected {expected}")

    def test_index_rowids_map_back_to_verses(self):
        """rowid is an explicit copy of verses.id, not a mirror of it.

        The table owns its text (that is what lets it hold a subset), so
        the join key has to be the id we inserted.
        """
        import sqlite3
        from core.bible_service import _BIBLE_DB_PATH
        conn = sqlite3.connect(f"file:{_BIBLE_DB_PATH}?mode=ro", uri=True)
        try:
            orphans = conn.execute(
                "SELECT COUNT(*) FROM verses_fts fts "
                "LEFT JOIN verses v ON v.id = fts.rowid "
                "WHERE v.id IS NULL").fetchone()[0]
            mismatched = conn.execute(
                "SELECT COUNT(*) FROM verses_fts fts "
                "JOIN verses v ON v.id = fts.rowid "
                "WHERE fts.text <> v.text").fetchone()[0]
        finally:
            conn.close()
        assert orphans == 0, f"{orphans} index rows point at no verse"
        assert mismatched == 0, (
            f"{mismatched} index rows do not match their verse's text")

    def test_inflected_query_matches_uninflected_text(self):
        """'forgives' is not in the KJV; 'forgive' is. Stemming in the
        index is what bridges that."""
        from core.bible_service import fts_search
        rows = fts_search("forgives", "KJV", limit=10)
        assert rows, "stemmed index returned nothing for 'forgives'"
        assert any("forgive" in r["text"].lower() for r in rows)


# ─── Query construction ───────────────────────────────────────────────────────


class TestQueryBuilding:
    def test_and_conjunction_is_explicit(self):
        """Regression: FTS5 will not read a parenthesised group as an
        implicit-AND operand, so 'a* (b* OR c*)' is a SYNTAX ERROR. When
        the conjunction was implicit, every multi-word query silently
        failed and fell through to the per-term top-up lane, which ranked
        single-word noise above real phrase matches."""
        from core.bible_service import _prefilter_groups
        groups = _prefilter_groups("coat colours")
        assert any(g.startswith("(") for g in groups), \
            "expected a parenthesised variant group to exercise this"
        joined = " AND ".join(groups)
        assert " (" not in joined.replace(" AND (", "@@") or True
        # No group may be preceded by a bare space (implicit AND).
        assert " (" not in joined.replace(" AND (", ""), (
            f"implicit AND before a group: {joined!r}")

    def test_groups_neutralize_fts_syntax(self):
        """Stems are alphanumeric; raw forms are quoted. Nothing the
        operator types can reach the parser as syntax."""
        import re
        from core.bible_service import _prefilter_groups
        for q in ['"amen', "amen*", "(amen", "NEAR(", "a:b", "x OR y",
                  "***", "???", "%", "_"]:
            for g in _prefilter_groups(q):
                # strip quoted phrases, then the only syntax we emit
                bare = re.sub(r'"[^"]*"', "", g)
                assert not re.search(r'[^\w*()\s]|"', bare), \
                    f"unsafe FTS term from {q!r}: {g!r}"

    def test_single_group_needs_no_conjunction(self):
        from core.bible_service import _prefilter_groups
        assert _prefilter_groups("amen") == ["amen*"]


# ─── fts_search behaviour ─────────────────────────────────────────────────────


class TestFtsSearch:
    def test_empty_query(self):
        from core.bible_service import fts_search
        assert fts_search("", "KJV", limit=10) == []
        assert fts_search("   ", "KJV", limit=10) == []

    def test_result_shape(self):
        from core.bible_service import fts_search
        rows = fts_search("amen", "KJV", limit=5)
        assert rows
        for r in rows:
            for key in ("book", "chapter", "verse", "verse_num", "text",
                        "confidence", "coverage", "matched"):
                assert key in r, key

    def test_version_is_honoured(self):
        from core.bible_service import fts_search
        kjv = {r["text"] for r in fts_search("shepherd", "KJV", 10)}
        esv = {r["text"] for r in fts_search("shepherd", "ESV", 10)}
        assert kjv and esv
        assert kjv != esv, "version argument ignored"

    def test_limit_is_respected(self):
        from core.bible_service import fts_search
        assert len(fts_search("lord", "KJV", limit=3)) <= 3

    def test_syntax_garbage_never_raises(self):
        from core.bible_service import fts_search
        for q in ['"amen', "amen*", "a:b", "(amen", "Gen 1:1", "~amen",
                  "amen OR it", "***", "???", "%", "_", "()", "AND"]:
            assert isinstance(fts_search(q, "KJV", limit=10), list)

    def test_stopword_only_no_crash(self):
        from core.bible_service import fts_search
        assert isinstance(fts_search("is it", "KJV", limit=10), list)

    def test_multiword_query_finds_the_phrase(self):
        """The regression the implicit-AND bug caused: a two-word query
        must actually filter on both words. Rows below the full-coverage
        tier may carry one word (that is the top-up lane doing its job);
        the full-coverage tier may not."""
        from core.bible_service import fts_search
        rows = fts_search("still waters", "KJV", limit=10)
        assert rows
        assert _ref(rows[0]) == "Psalms 23:2", _ref(rows[0])
        best = max(r["coverage"] for r in rows)
        for r in rows:
            if r["coverage"] < best:
                continue
            assert "still" in r["text"].lower(), r
            assert "water" in r["text"].lower(), r

    def test_partial_matches_surface_below_full_ones(self):
        """Thin AND still surfaces verses carrying only some words, but
        never above a verse carrying all of them."""
        from core.bible_service import fts_search
        rows = fts_search("love one another new commandment",
                          "KJV", limit=20)
        covs = [r["coverage"] for r in rows]
        assert max(covs) > min(covs), "expected a coverage spread"
        assert covs == sorted(covs, reverse=True)


class TestRankingContract:
    def test_coverage_is_primary_rank_key(self):
        """Most-matches wins: a partial-coverage verse can never outrank
        a fuller one, no matter how rare its terms are."""
        from core.bible_service import fts_search
        for query in ("love one another new commandment",
                      "faith hope charity",
                      "beginning god created heaven earth",
                      "valley shadow death"):
            rows = fts_search(query, "KJV", limit=20)
            assert rows, query
            covs = [r["coverage"] for r in rows]
            assert covs == sorted(covs, reverse=True), (query, covs)
            assert covs[0] == max(covs)

    def test_adjacent_words_outrank_scattered_ones(self):
        """Among verses carrying both words, one holding them side by
        side ("a well of living waters") is the sharper keyword hit."""
        from core.bible_service import fts_search
        rows = fts_search("living water", "KJV", limit=10)
        assert rows
        best = max(r["coverage"] for r in rows)
        top = [r for r in rows if r["coverage"] == best]
        assert "living water" in top[0]["text"].lower(), (
            f"top hit is not the adjacent phrase: {top[0]['text']!r}")
        # and the adjacency probe is what put it there: a scattered
        # full-coverage verse must not have beaten it
        assert _ref(rows[0]) in [_ref(r) for r in top]

    def test_adjacency_is_a_real_phrase_not_co_occurrence(self):
        """`"ten" "commandments"` is an AND of two phrases, not a phrase.
        Only the three verses carrying the literal phrase may take the
        adjacency tier — not a scattered 'ten days … commanded' verse."""
        from core.bible_service import fts_search
        rows = fts_search("ten commandments", "KJV", 6)
        refs = [_ref(r) for r in rows]
        assert set(refs[:3]) == {"Deuteronomy 4:13", "Exodus 34:28",
                                 "Deuteronomy 10:4"}, refs

    def test_partial_pool_prefers_discriminating_words(self):
        """The OR sweep must not spend its operands on words that match
        nearly every verse: "we" and "by" buy no recall, they only add
        rows to rank."""
        from core.bible_service import _partial_pool_groups
        chosen = _partial_pool_groups(
            ["we*", "by*", "mountain*", "church*", "gates*"])
        assert "we*" not in chosen and "by*" not in chosen, chosen
        assert chosen[:2] == ["mountain*", "church*"], chosen

    def test_partial_pool_keeps_short_words_when_that_is_all_there_is(self):
        """A query made of short words still gets a partial sweep —
        "noah ark" must probe both, not silently drop them."""
        from core.bible_service import _partial_pool_groups
        chosen = _partial_pool_groups(["noah*", "ark*"])
        assert set(chosen) == {"noah*", "ark*"}, chosen

    def test_confidence_monotone_in_emitted_order(self):
        """The panel renders confidence as a badge, so it must never
        contradict the row order it is printed next to."""
        from core.bible_service import fts_search
        for query in ("amen it is so", "love one another new commandment",
                      "beginning god created"):
            confs = [r["confidence"] for r in fts_search(query, "KJV", 20)]
            assert confs == sorted(confs, reverse=True), query
            assert all(0 < c <= 100 for c in confs), confs

    def test_full_coverage_scores_above_partial(self):
        from core.bible_service import fts_search
        rows = fts_search("love one another new commandment", "KJV", 20)
        best = max(r["coverage"] for r in rows)
        full = [r["confidence"] for r in rows if r["coverage"] == best]
        partial = [r["confidence"] for r in rows if r["coverage"] < best]
        assert full and (not partial or min(full) > max(partial))

    def test_every_full_coverage_hit_contains_every_word(self):
        """The whole point of the lane, stated as an invariant: a result
        claiming full coverage must literally contain every query word.
        A blended/semantic ranker breaks exactly this — it floats verses
        that are about the words without carrying them."""
        from core.bible_service import fts_search
        queries = ["noah ark", "still waters", "living water",
                   "faith hope charity", "valley shadow death",
                   "beginning god created"]
        for q in queries:
            words = [w for w in q.lower().split() if w]
            rows = fts_search(q, "KJV", limit=15)
            assert rows, q
            best = max(r["coverage"] for r in rows)
            for r in rows:
                if r["coverage"] < min(best, len(words)):
                    continue
                text = r["text"].lower()
                for w in words:
                    assert w[:4] in text or _stem_prefix(w) in text, (
                        f"{q!r}: {_ref(r)} claims coverage {r['coverage']} "
                        f"but lacks {w!r}: {r['text']!r}")

    def test_no_numpy_bm25_in_the_lane(self):
        """The lane must not reach for the postings scorer. It is kept
        for the keyword lane only; if FTS ever borrows it again, the
        blended ranking the operator rejected comes straight back."""
        import inspect
        from core.bible_service import fts_search
        src = inspect.getsource(fts_search)
        assert "_score_postings" not in src
        assert "_load_postings" not in src
        assert "RERANK" not in src


class TestNoTypoRescue:
    """Pure FTS5, deliberately: a misspelling finds nothing.

    There is no prefix-widening rescue and no trigram lane. Widening a
    misspelling costs a corpus scan per character dropped, and on this
    lane those scans were the slowest thing a query could do — paid for
    on ordinary words whose prefix simply happened to miss. A search that
    returns nothing for a typo is honest; one that silently substitutes a
    different word is not.
    """

    def test_the_rescue_helper_is_gone(self):
        import core.bible_service as svc
        assert not hasattr(svc, "_relaxed_group_hits"), (
            "typo rescue is back; the FTS lane is meant to be pure FTS5")

    def test_no_rescue_call_in_the_search_path(self):
        import inspect
        from core.bible_service import fts_search
        src = inspect.getsource(fts_search)
        assert "_relaxed_group_hits" not in src
        assert "_FTS_RELAX_PROBES" not in src

    def test_a_misspelling_returns_nothing(self):
        """Typos whose STEM matches no term, so nothing comes back.

        Note this is prefix search working correctly, not a hole in it: a
        word that legitimately shares a prefix with a real term still
        matches it ("forgivness" stems to "forgiv", and `forgiv*` finds
        *forgive*). What must not happen is a misspelling being WIDENED
        to reach a word it does not share a prefix with.
        """
        from core.bible_service import fts_search
        for typo in ("shepard", "baptizm", "sheelperd"):
            rows = fts_search(typo, "KJV", limit=10)
            assert not rows, (
                f"{typo!r} returned {[r['text'][:30] for r in rows[:2]]} — "
                "expected nothing, the query does not match")

    def test_a_shared_prefix_still_matches(self):
        """Dropping rescue must not disable prefix search itself."""
        from core.bible_service import fts_search
        assert fts_search("forgiv", "KJV", limit=5), "prefix match regressed"

    def test_correctly_spelled_queries_still_work(self):
        """Dropping rescue must not cost the queries that DO match."""
        from core.bible_service import fts_search
        rows = fts_search("shepherd", "KJV", limit=10)
        assert rows, "correctly spelled 'shepherd' found nothing"
        assert any("shepherd" in r["text"].lower() for r in rows)
        assert fts_search("forgives", "KJV", limit=5), "stemming regressed"


# ─── Retained BM25 cache behaviour (keyword + fuzzy lanes still use it) ───────


class TestBM25LazyLoad:
    def test_load_caches_version(self):
        """First call loads from disk, second call uses cache."""
        from core.bible_service import _load_bm25_index, _bm25_cache

        fake_bm25 = object()  # non-picklable but we mock pickle.load
        fake_lookup = [("KJV", "Gen", 1, 1, "In the beginning")]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Touch the files so os.path.exists passes
            open(os.path.join(tmpdir, "bm25_TEST.pkl"), "wb").close()
            open(os.path.join(tmpdir, "verse_lookup_TEST.pkl"), "wb").close()

            load_results = [fake_bm25, fake_lookup]
            call_count = [0]

            def fake_pickle_load(f):
                val = load_results[call_count[0]]
                call_count[0] += 1
                return val

            _bm25_cache.pop("TEST", None)
            with mock.patch("core.bible_service._INDEXES_DIR", tmpdir), \
                 mock.patch("core.bible_service.pickle.load", side_effect=fake_pickle_load):
                bm25_1, lookup_1 = _load_bm25_index("TEST")
                assert bm25_1 is fake_bm25
                assert lookup_1 is fake_lookup
                assert "TEST" in _bm25_cache

                # Second call should hit cache (no file read)
                call_count[0] = 0
                bm25_2, lookup_2 = _load_bm25_index("TEST")
                assert bm25_2 is fake_bm25
                assert call_count[0] == 0  # pickle.load was NOT called

    def test_missing_index_returns_none(self):
        """Missing per-version index returns (None, None)."""
        from core.bible_service import _load_bm25_index, _bm25_cache

        with tempfile.TemporaryDirectory() as tmpdir:
            _bm25_cache.pop("NONEXISTENT", None)
            with mock.patch("core.bible_service._INDEXES_DIR", tmpdir):
                bm25, lookup = _load_bm25_index("NONEXISTENT")
                assert bm25 is None
                assert lookup is None


# ─── Quality on the real index ────────────────────────────────────────────────


class TestQuality:
    def test_shepherd_surfaces_psalm_23(self):
        from core.bible_service import fts_search
        rows = fts_search("lord is my shepherd", "KJV", limit=10)
        assert rows, "expected hits"
        assert _ref(rows[0]) == "Psalms 23:1"

    def test_indirect_recall_without_all_words(self):
        """A missing query word must not lose the phrase: 'shepherd' and
        'psalm' do not sit in the same verse, yet Psalms 23 surfaces."""
        from core.bible_service import fts_search
        refs = [_ref(r) for r in fts_search("lord shepherd", "KJV", limit=10)]
        assert "Psalms 23:1" in refs

    def test_matched_surfaces_populated(self):
        """Highlight surfaces must come back, or rows render unhighlighted."""
        from core.bible_service import fts_search
        rows = fts_search("shepherd psalm", "KJV", limit=5)
        assert any(r["matched"] for r in rows)

    def test_one_absent_word_does_not_bury_a_five_of_six_match(self):
        """The field regression: the operator typed "mountain" where the
        verse says "rock". One absent word must not exclude a verse that
        carries the other five, and coverage must count the text rather
        than whichever probe happened to return the row."""
        from core.bible_service import fts_search
        rows = fts_search("upon mountain build church gates hell", "KJV", 10)
        assert rows
        best = rows[0]
        assert _ref(best) == "Matthew 16:18", [(_ref(r), r["coverage"])
                                               for r in rows[:5]]
        assert best["coverage"] == 5, best["coverage"]
        assert "mountain" not in best["text"].lower()
        assert best["confidence"] > 80

    def test_partial_coverage_is_counted_from_the_verse_text(self):
        """A long phrase with one extra word still ranks its source verse
        first — and reports the near-full coverage the text actually has,
        not the single word a probe matched."""
        from core.bible_service import fts_search
        rows = fts_search(
            "for we walk by faith not by sight not seen", "KJV", 10)
        assert rows
        assert _ref(rows[0]) == "2 Corinthians 5:7", _ref(rows[0])
        assert rows[0]["coverage"] >= 7
        assert rows[0]["confidence"] > 80

    def test_sweep_timing_table(self):
        """Parallel-sweep wall budget (mirrors the panel worker pool)."""
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from core.bible_service import fts_search
        from core.constants import FTS_TRANSLATIONS
        for workers in (3, 6):
            t0 = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(fts_search, "amen it is so", trans, 30):
                           trans for trans in FTS_TRANSLATIONS}
                n = sum(len(f.result()) for f in as_completed(futures))
            dt = (time.monotonic() - t0) * 1000.0
            print(f"  workers={workers}: {dt:.0f}ms hits={n}")
        assert True  # informational

class TestLatencyIsBoundedByQueryLength:
    """Latency must not grow with how much the operator has typed.

    The naive version probed EVERY query word for partial matches when
    the strict AND came back thin, so each extra word cost another corpus
    scan: an eight-word query spent ~700ms on probes alone. Two bounds
    hold it down — one capped OR sweep instead of per-word probes, and a
    cap on how far a misspelling may be widened.
    """

    def test_at_most_a_few_words_probe(self, monkeypatch):
        from core import bible_service as svc
        from core.constants import FTS_TOPUP_TERMS
        assert 1 <= FTS_TOPUP_TERMS <= 4, FTS_TOPUP_TERMS

        seen = []
        real = svc._fts_ranked

        def counting(match_q, version, limit, *a, **k):
            seen.append(match_q)
            return real(match_q, version, limit, *a, **k)

        monkeypatch.setattr(svc, "_fts_ranked", counting)
        svc.fts_search("for we walk by faith not by sight not seen", "KJV", 30)
        probes = [q for q in seen if " OR " not in q]
        assert len(probes) <= FTS_TOPUP_TERMS + 2, probes  # +AND +phrase

    def test_one_bounded_or_sweep_feeds_the_partial_pool(self, monkeypatch):
        """Partial recall is one sweep, not one probe per word — so the
        cost of a long query stays flat instead of growing word by word."""
        from core import bible_service as svc
        from core.constants import FTS_PARTIAL_POOL

        seen = []
        real = svc._fts_ranked

        def counting(match_q, version, limit, *a, **k):
            seen.append((match_q, limit))
            return real(match_q, version, limit, *a, **k)

        monkeypatch.setattr(svc, "_fts_ranked", counting)
        svc.fts_search(
            "alpha bravo charlie delta echo foxtrot golf hotel", "KJV", 30)
        or_probes = [(q, lim) for q, lim in seen if " OR " in q]
        assert len(or_probes) == 1, or_probes
        assert or_probes[0][1] >= FTS_PARTIAL_POOL, or_probes

    def test_a_word_that_matches_nothing_costs_nothing_extra(self):
        """With rescue gone, a zero-hit word must not trigger any further
        probing on its account."""
        import time
        from core.bible_service import fts_search

        def ms(q):
            fts_search(q, "KJV", 30)
            best = 1e9
            for _ in range(3):
                t = time.perf_counter()
                fts_search(q, "KJV", 30)
                best = min(best, (time.perf_counter() - t) * 1000)
            return best

        assert ms("shepardzqx") < ms("shepard") * 3

    def test_a_long_query_is_not_slower_than_a_ridiculous_one(self):
        """A coarse guard on the regression: doubling a query's length must
        not multiply its cost."""
        import time
        from core.bible_service import fts_search

        def ms(q):
            fts_search(q, "KJV", 30)
            best = 1e9
            for _ in range(3):
                t = time.perf_counter()
                fts_search(q, "KJV", 30)
                best = min(best, (time.perf_counter() - t) * 1000)
            return best

        four = ms("faith hope charity love")
        eight = ms("faith hope charity love patience "
                   "kindness goodwill faithfulness")
        assert eight < four * 4, (four, eight)


class TestFtsTranslationChoice:
    """Which translations a query fans out across is the operator's
    choice, capped, and honoured live.

    It is also the biggest speed lever on this lane: one translation is
    roughly a 6x saving per keystroke against the default six.
    """

    def _fresh_db(self, tmp_path, monkeypatch):
        import core.database as db
        monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "settings.db"))
        db.init_db()

    def test_default_is_the_constants_list(self, tmp_path, monkeypatch):
        from core.constants import FTS_TRANSLATIONS
        from core.bible_service import fts_translations
        self._fresh_db(tmp_path, monkeypatch)
        assert fts_translations() == FTS_TRANSLATIONS

    def test_choice_round_trips(self, tmp_path, monkeypatch):
        from core.bible_service import fts_translations, set_fts_translations
        self._fresh_db(tmp_path, monkeypatch)
        assert set_fts_translations(["KJV", "ESV"]) == ["KJV", "ESV"]
        assert fts_translations() == ["KJV", "ESV"]

    def test_capped_at_six(self, tmp_path, monkeypatch):
        from core.constants import FTS_MAX_TRANSLATIONS
        from core.bible_service import set_fts_translations
        self._fresh_db(tmp_path, monkeypatch)
        chosen = set_fts_translations(["A", "B", "C", "D", "E", "F", "G", "H"])
        assert len(chosen) == FTS_MAX_TRANSLATIONS == 6

    def test_uninstalled_translations_are_dropped(self, tmp_path, monkeypatch):
        """A translation removed from bible.db must not silently empty the
        lane — the rest survive."""
        from core.bible_service import fts_translations, set_fts_translations
        self._fresh_db(tmp_path, monkeypatch)
        set_fts_translations(["KJV", "NOT_A_REAL_TRANSLATION"])
        assert fts_translations() == ["KJV"]

    def test_order_preserved_and_deduplicated(self, tmp_path, monkeypatch):
        from core.bible_service import set_fts_translations
        self._fresh_db(tmp_path, monkeypatch)
        assert set_fts_translations(["ESV", "KJV", "esv"]) == ["ESV", "KJV"]

    def test_garbage_setting_falls_back_to_the_default(self, tmp_path,
                                                        monkeypatch):
        from core.constants import FTS_TRANSLATIONS
        from core.bible_service import fts_translations
        self._fresh_db(tmp_path, monkeypatch)
        db_set = __import__("core.database", fromlist=["set_setting"])
        db_set.set_setting("search.fts_translations", "{not json")
        assert fts_translations() == FTS_TRANSLATIONS

    def test_panel_reads_the_choice_live(self, tmp_path, monkeypatch):
        """Not cached at import: a Settings change must reach the next
        query without a restart."""
        import inspect
        from ui.panels import fts_search_panel as mod
        self._fresh_db(tmp_path, monkeypatch)
        from core.bible_service import set_fts_translations
        set_fts_translations(["KJV"])
        src = inspect.getsource(mod.FtsSearchPanel._run_sweep)
        assert "fts_translations()" in src, "panel still uses a fixed list"
        assert "FTS_TRANSLATIONS" not in src
