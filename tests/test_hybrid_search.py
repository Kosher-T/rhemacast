"""
tests/test_hybrid_search.py

Tests for the FTS5 + BM25 hybrid search pipeline:
  - Stemming in shared tokenizer
  - Tokenizer symmetry across modules
  - Per-version BM25 lazy loading
  - hybrid_search() parallel fusion
  - FTS5 fallback on missing BM25 index
"""

import os
import pickle
import tempfile
from unittest import mock

import pytest

from core.text_utils import tokenize, normalize_text, STEMMER


# ─── Stemming Tests ───────────────────────────────────────────────────────────


class TestStemming:
    def test_stemming_transform(self):
        """'transform' and 'transformed' should produce identical stems."""
        t1 = tokenize("transform")
        t2 = tokenize("transformed")
        assert t1 == t2

    def test_stemming_love_variants(self):
        """love / loving / beloved should all stem (Porter stemmer preserves 'love')."""
        t_love = tokenize("love")
        t_loving = tokenize("loving")
        t_beloved = tokenize("beloved")
        # Porter stemmer: 'love' → 'love', 'loving' → 'love', 'beloved' → 'belov'
        assert t_love == ["love"]
        assert t_loving == ["love"]
        assert t_beloved == ["belov"]

    def test_stemming_preserves_stop_words(self):
        """Stop-words should be removed before stemming."""
        tokens = tokenize("the love of God")
        assert "the" not in tokens
        assert "of" not in tokens
        assert len(tokens) == 2  # love, god

    def test_stemming_archaic_retained(self):
        """Archaic theological vocabulary should be retained (not in stop-words)."""
        tokens = tokenize("thou hast loved thy servant")
        # thou, hast, loved, thy, servant — all should be present (stemmed)
        assert any("thou" in t for t in tokens)
        assert any("hast" in t for t in tokens)
        assert any("servant" in t for t in tokens)

    def test_normalize_apostrophes(self):
        """Apostrophes and smart quotes should be stripped."""
        norm = normalize_text("God's love\u2019it is\u2018great")
        assert "'" not in norm
        assert "\u2019" not in norm
        assert "\u2018" not in norm
        assert "gods" in norm
        assert "love" in norm

    def test_normalize_punctuation_to_space(self):
        """Hyphens, dashes, slashes, colons become spaces."""
        norm = normalize_text("well-being: a God-given gift")
        assert "well" in norm
        assert "being" in norm
        assert "god" in norm
        assert "given" in norm
        assert "gift" in norm


# ─── Tokenizer Symmetry Tests ────────────────────────────────────────────────


class TestTokenizerSymmetry:
    def test_search_engine_matches_text_utils(self):
        """search_engine.tokenize must produce the same output as text_utils.tokenize."""
        from core.search_engine import tokenize as se_tokenize
        queries = [
            "for God so loved the world",
            "the Lord is my shepherd",
            "transform",
            "blessed are the peacemakers",
        ]
        for q in queries:
            assert se_tokenize(q) == tokenize(q), f"Mismatch on query: {q}"

    def test_build_bm25_matches_text_utils(self):
        """build_bm25.tokenize must produce the same output as text_utils.tokenize."""
        # Import the module-level tokenize from build_bm25
        import importlib
        spec = importlib.util.spec_from_file_location(
            "build_bm25",
            os.path.join(os.path.dirname(__file__), "..", "data", "bible", "build_bm25.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bm25_tokenize = mod.tokenize

        queries = [
            "for God so loved the world",
            "in the beginning God created",
            "thou shalt not kill",
        ]
        for q in queries:
            assert bm25_tokenize(q) == tokenize(q), f"Mismatch on query: {q}"


# ─── BM25 Lazy-Load Tests ────────────────────────────────────────────────────


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


# ─── hybrid_search Tests ──────────────────────────────────────────────────────


class TestHybridSearch:
    def test_hybrid_search_empty_query(self):
        """Empty query returns empty list."""
        from core.bible_service import hybrid_search
        assert hybrid_search("") == []
        assert hybrid_search("   ") == []

    def test_hybrid_search_fts5_only_fallback(self):
        """When BM25 index is missing, returns FTS5 results only."""
        from core.bible_service import hybrid_search

        fts_results = [
            {"book": "Gen", "chapter": 1, "verse": 1, "text": "In the beginning"},
            {"book": "Gen", "chapter": 1, "verse": 2, "text": "The earth was void"},
        ]
        with mock.patch("core.bible_service.search_verses_text", return_value=fts_results), \
             mock.patch("core.bible_service.bm25_search", return_value=[]):
            results = hybrid_search("beginning", "KJV", limit=10)

        assert len(results) == 2
        assert results[0]["book"] == "Gen"

    def test_hybrid_search_fuses_results(self):
        """FTS5 + BM25 results are fused via RRF."""
        from core.bible_service import hybrid_search

        fts_results = [
            {"book": "Gen", "chapter": 1, "verse": 1, "text": "In the beginning"},
        ]
        bm25_results = [
            {"book": "Gen", "chapter": 1, "verse": 1, "text": "In the beginning"},
            {"book": "Gen", "chapter": 1, "verse": 2, "text": "The earth was void"},
        ]
        with mock.patch("core.bible_service.search_verses_text", return_value=fts_results), \
             mock.patch("core.bible_service.bm25_search", return_value=bm25_results):
            results = hybrid_search("beginning", "KJV", limit=10)

        # Both sources contribute; verse 1 appears in both so gets higher RRF score
        assert len(results) >= 1
        # Result keys should be book, chapter, verse, text
        for r in results:
            assert "book" in r
            assert "chapter" in r
            assert "verse" in r
            assert "text" in r

    def test_hybrid_search_version_passed_through(self):
        """Version parameter is forwarded to both search functions."""
        from core.bible_service import hybrid_search

        with mock.patch("core.bible_service.search_verses_text", return_value=[]) as mock_fts, \
             mock.patch("core.bible_service.bm25_search", return_value=[]) as mock_bm25:
            hybrid_search("test", "NKJV", limit=5)

        mock_fts.assert_called_once_with("test", "NKJV", 5)
        mock_bm25.assert_called_once_with("test", "NKJV", 5)

    def test_bm25_search_returns_correct_format(self):
        """bm25_search returns list[dict] with book, chapter, verse, text."""
        from core.bible_service import bm25_search, _bm25_cache

        import numpy as np

        class FakeBM25:
            def get_scores(self, tokens):
                return np.array([5.0, 3.0, 0.0])

        fake_bm25 = FakeBM25()
        mock_lookup = [
            ("KJV", "Gen", 1, 1, "In the beginning"),
            ("KJV", "Gen", 1, 2, "The earth was void"),
            ("KJV", "Gen", 1, 3, "And darkness was upon the face"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "bm25_KJV.pkl"), "wb").close()
            open(os.path.join(tmpdir, "verse_lookup_KJV.pkl"), "wb").close()

            load_results = [fake_bm25, mock_lookup]
            call_count = [0]

            def fake_pickle_load(f):
                val = load_results[call_count[0]]
                call_count[0] += 1
                return val

            _bm25_cache.pop("KJV", None)
            with mock.patch("core.bible_service._INDEXES_DIR", tmpdir), \
                 mock.patch("core.bible_service.pickle.load", side_effect=fake_pickle_load):
                results = bm25_search("beginning", "KJV", limit=2)

        assert len(results) == 2
        assert results[0]["book"] == "Gen"
        assert results[0]["chapter"] == 1
        assert results[0]["verse"] == 1
        assert "text" in results[0]
