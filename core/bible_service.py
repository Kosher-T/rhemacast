"""
core/bible_service.py

Data access layer for the Bible browser panel.
Queries bible.db (SQLite) for chapter/verse lookups and natural language search.
"""

import csv
import os
import pickle
import re
import shutil
import sqlite3
import logging
import sys
import numpy as np
from typing import List, Dict, Optional

from core.text_utils import tokenize

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_BIBLE_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "bible", "bible.db")

_INDEXES_DIR = os.path.join(_PROJECT_ROOT, "data", "indexes")

_JSON_DIR = os.path.join(_PROJECT_ROOT, "data", "bible", "json")

# Default translations (fallback if bible.db query fails)
_DEFAULT_TRANSLATIONS = ["AMP", "ESV", "KJV", "NIV", "NKJV", "NLT"]

# Compact per-version search structures: inverted postings as numpy
# arrays (indices int32 + freqs uint16) plus BM25 globals. Built once
# from the pickled index, then the heavyweight object is dropped
# (~3MB/version live instead of ~10x that). Scoring is pure numpy
# (GIL-free), so all translations score truly in parallel.
_postings_cache: Dict[str, dict] = {}
_ref_index_cache: Dict[str, dict] = {}

# Lazy-loaded per-version BM25 caches: {version: (bm25_index, verse_lookup)}
_bm25_cache: Dict[str, tuple] = {}




def _book_index(version: str) -> dict:
    """Normalized book names: full name → (number_or_None, alpha_name).

    Keys are lowercase alphanumeric ("1 samuel", "psalms"). Cached.
    """
    import re as _re
    cache = _book_index_cache.get(version.upper())
    if cache is not None:
        return cache
    try:
        conn = _get_connection()
        names = [r[0] for r in conn.execute(
            "SELECT DISTINCT book FROM verses WHERE version = ?",
            (version.upper(),)).fetchall()]
        conn.close()
    except Exception:
        names = []
    index = {}
    for name in names:
        norm = _re.sub(r"[^a-z0-9 ]", "", (name or "").lower())
        norm = " ".join(norm.split())
        if not norm:
            continue
        parts = norm.split(" ", 1)
        if parts[0] in ("1", "2", "3", "i", "ii", "iii", "1st", "2nd",
                        "3rd", "first", "second", "third") and len(parts) > 1:
            num = {"1": "1", "i": "1", "1st": "1", "first": "1",
                   "2": "2", "ii": "2", "2nd": "2", "second": "2",
                   "3": "3", "iii": "3", "3rd": "3", "third": "3"}[parts[0]]
            index[norm] = (num, parts[1])
        else:
            index[norm] = (None, norm)
    _book_index_cache[version.upper()] = index
    return index




def _ref_index(version: str) -> Optional[dict]:
    """(book, chapter, verse_num) → corpus idx for FTS rowid mapping."""
    version = version.upper()
    if version in _ref_index_cache:
        return _ref_index_cache[version]
    bm25, verse_lookup = _load_bm25_index(version)
    if not verse_lookup:
        return None
    mapping = {}
    for idx, entry in enumerate(verse_lookup):
        try:
            _ver, book, chapter, verse_num, _text = entry
            mapping[(book, chapter, verse_num)] = idx
        except (TypeError, ValueError):
            continue
    _ref_index_cache[version] = mapping
    return mapping


def _score_postings(compact: dict, tokens: list) -> tuple:
    """Exact BM25Okapi scores + per-doc matched-term counts.

    Same formula and accumulation order as BM25Okapi.get_scores —
    bit-comparable outputs — but vectorized per term over postings
    (numpy, GIL-free) instead of a Python loop over the corpus.
    Returns (scores float64[N], hits int32[N]).
    """
    n = compact["corpus_size"]
    scores = np.zeros(n, dtype=np.float64)
    hits = np.zeros(n, dtype=np.int32)
    k1, b, avgdl = compact["k1"], compact["b"], compact["avgdl"]
    doc_len = compact["doc_len"]
    postings = compact["postings"]
    idf = compact["idf"]
    for q in tokens:
        slot = postings.get(q)
        if slot is None:
            continue
        term_idf = idf.get(q) or 0
        if not term_idf:
            continue
        idx, freq = slot
        freq = freq.astype(np.float64)
        denom = freq + k1 * (1.0 - b + b * doc_len[idx] / avgdl)
        scores[idx] += term_idf * (freq * (k1 + 1.0) / denom)
        hits[idx] += 1
    return scores, hits


def _get_connection() -> sqlite3.Connection:
    """Returns a read-only connection to the Bible database."""
    conn = sqlite3.connect(f"file:{_BIBLE_DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_available_translations() -> List[str]:
    """Return the list of translations available in bible.db, dynamically."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT DISTINCT version FROM verses ORDER BY version ASC"
        )
        translations = [row["version"] for row in cursor.fetchall()]
        conn.close()
        return translations if translations else _DEFAULT_TRANSLATIONS
    except Exception as e:
        logger.error(f"Failed to query available translations: {e}")
        return _DEFAULT_TRANSLATIONS


# Backward-compatible: module-level constant populated lazily
AVAILABLE_TRANSLATIONS = get_available_translations()


def get_chapter(version: str, book: str, chapter: int) -> List[Dict]:
    """
    Retrieve all verses for a given book and chapter in the specified translation.
    Returns a list of dicts with keys: chapter, verse, text.
    """
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT chapter, verse_num, text FROM verses "
            "WHERE version = ? AND book = ? AND chapter = ? "
            "ORDER BY verse_num ASC",
            (version.upper(), book, chapter)
        )
        results = [
            {"chapter": row["chapter"], "verse": row["verse_num"], "text": row["text"]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Failed to query chapter: {e}")
        return []


def get_all_verses(version: str) -> List[Dict]:
    """
    Retrieve the entire bible for a given translation in canonical order.
    Returns a list of dicts with keys: book, chapter, verse, text.
    """
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT book, chapter, verse_num, text FROM verses "
            "WHERE version = ? "
            "ORDER BY id ASC",
            (version.upper(),)
        )
        results = [
            {"book": row["book"], "chapter": row["chapter"],
             "verse": row["verse_num"], "text": row["text"]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Failed to query all verses: {e}")
        return []


def get_verse(version: str, book: str, chapter: int, verse: int) -> Optional[Dict]:
    """Retrieve a single verse."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT chapter, verse_num, text FROM verses "
            "WHERE version = ? AND book = ? AND chapter = ? AND verse_num = ?",
            (version.upper(), book, chapter, verse)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"chapter": row["chapter"], "verse": row["verse_num"], "text": row["text"]}
        return None
    except Exception as e:
        logger.error(f"Failed to query verse: {e}")
        return None


def get_books(version: str = "KJV") -> List[str]:
    """Return the distinct list of books for a translation, in canonical order."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT DISTINCT book FROM verses WHERE version = ? ORDER BY id ASC",
            (version.upper(),)
        )
        # Use a seen-set to preserve insertion order (canonical)
        seen = set()
        books = []
        for row in cursor.fetchall():
            b = row["book"]
            if b not in seen:
                seen.add(b)
                books.append(b)
        conn.close()
        return books
    except Exception as e:
        logger.error(f"Failed to query books: {e}")
        return []


def get_chapter_count(version: str, book: str) -> int:
    """Return the number of chapters in a book."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT MAX(chapter) as max_ch FROM verses WHERE version = ? AND book = ?",
            (version.upper(), book)
        )
        row = cursor.fetchone()
        conn.close()
        return row["max_ch"] if row and row["max_ch"] else 0
    except Exception as e:
        logger.error(f"Failed to query chapter count: {e}")
        return 0


def get_verse_count(version: str, book: str, chapter: int) -> int:
    """Return the number of verses in a chapter."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT MAX(verse_num) as max_v FROM verses "
            "WHERE version = ? AND book = ? AND chapter = ?",
            (version.upper(), book, chapter)
        )
        row = cursor.fetchone()
        conn.close()
        return row["max_v"] if row and row["max_v"] else 0
    except Exception as e:
        logger.error(f"Failed to query verse count: {e}")
        return 0


def get_next_verse(version: str, book: str, chapter: int, verse: int) -> Optional[Dict]:
    """Return the verse immediately after the given reference in canonical order."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT book, chapter, verse_num, text FROM verses "
            "WHERE version = ? AND id > ("
            "  SELECT id FROM verses "
            "  WHERE version = ? AND book = ? AND chapter = ? AND verse_num = ?"
            ") ORDER BY id ASC LIMIT 1",
            (version.upper(), version.upper(), book, chapter, verse)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"book": row["book"], "chapter": row["chapter"],
                    "verse": row["verse_num"], "text": row["text"]}
        return None
    except Exception as e:
        logger.error(f"Failed to query next verse: {e}")
        return None


def get_prev_verse(version: str, book: str, chapter: int, verse: int) -> Optional[Dict]:
    """Return the verse immediately before the given reference in canonical order."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT book, chapter, verse_num, text FROM verses "
            "WHERE version = ? AND id < ("
            "  SELECT id FROM verses "
            "  WHERE version = ? AND book = ? AND chapter = ? AND verse_num = ?"
            ") ORDER BY id DESC LIMIT 1",
            (version.upper(), version.upper(), book, chapter, verse)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"book": row["book"], "chapter": row["chapter"],
                    "verse": row["verse_num"], "text": row["text"]}
        return None
    except Exception as e:
        logger.error(f"Failed to query prev verse: {e}")
        return None


def search_verses_text(query: str, version: str = "KJV", limit: int = 20) -> List[Dict]:
    """
    Simple FTS5 search on verse text within a specific translation.
    Falls back to LIKE query if FTS is not available.
    """
    from core.text_utils import split_search_words
    words = split_search_words(query)
    if not words:
        return []

    try:
        conn = _get_connection()

        # Sanitized AND (never raw user text: FTS syntax errors used to
        # collapse into a full-table LIKE scan per keystroke).
        fts_query = " ".join(f'"{w}"' for w in words)

        # Try FTS5 first (verses_fts table exists in bible.db)
        try:
            cursor = conn.execute(
                "SELECT v.book, v.chapter, v.verse_num, v.text "
                "FROM verses_fts fts "
                "JOIN verses v ON v.rowid = fts.rowid "
                "WHERE fts.text MATCH ? AND v.version = ? "
                "ORDER BY rank "
                "LIMIT ?",
                (fts_query, version.upper(), limit)
            )
            results = [
                {"chapter": row["chapter"], "verse": row["verse_num"],
                 "text": row["text"], "book": row["book"]}
                for row in cursor.fetchall()
            ]
            conn.close()
            return results
        except sqlite3.OperationalError:
            pass
        
        # Fallback: LIKE query over the sanitized words (raw user text
        # could smuggle %/_ wildcards).
        like_q = f"%{' '.join(words)}%"
        cursor = conn.execute(
            "SELECT book, chapter, verse_num, text FROM verses "
            "WHERE version = ? AND text LIKE ? "
            "LIMIT ?",
            (version.upper(), like_q, limit)
        )
        results = [
            {"chapter": row["chapter"], "verse": row["verse_num"],
             "text": row["text"], "book": row["book"]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Failed to search verses: {e}")
        return []


# ─── BM25 + Hybrid Search ────────────────────────────────────────────────────


def _load_bm25_index(version: str):
    """Lazy-load a per-version BM25 index from disk. Returns (bm25, verse_lookup) or (None, None)."""
    version = version.upper()
    if version in _bm25_cache:
        return _bm25_cache[version]

    bm25_path = os.path.join(_INDEXES_DIR, f"bm25_{version}.pkl")
    lookup_path = os.path.join(_INDEXES_DIR, f"verse_lookup_{version}.pkl")

    if not os.path.exists(bm25_path) or not os.path.exists(lookup_path):
        logger.warning(f"Per-version BM25 index not found for {version} — run build_bm25.py")
        return None, None

    try:
        with open(bm25_path, "rb") as f:
            bm25 = pickle.load(f)
        with open(lookup_path, "rb") as f:
            verse_lookup = pickle.load(f)
        _bm25_cache[version] = (bm25, verse_lookup)
        logger.info(f"Loaded BM25 index for {version}: {len(verse_lookup):,} verses")
        return bm25, verse_lookup
    except Exception as e:
        logger.error(f"Failed to load BM25 index for {version}: {e}")
        return None, None


def bm25_search(query: str, version: str = "KJV", limit: int = 20) -> List[Dict]:
    """Search a per-version BM25 index with stemmed tokenization.

    Returns list[dict] with keys: book, chapter, verse, text.
    """
    bm25, verse_lookup = _load_bm25_index(version)
    if not bm25 or not verse_lookup:
        return []

    tokens = tokenize(query)
    if not tokens:
        return []

    scores = bm25.get_scores(tokens)
    top_indices = np.argsort(scores)[::-1][:limit]

    results = []
    for idx in top_indices:
        _ver, book, chapter, verse_num, text = verse_lookup[idx]
        if scores[idx] <= 0:
            break
        results.append({"book": book, "chapter": chapter, "verse": verse_num, "text": text})
    return results


def _variant_forms(word: str) -> list:
    """British/American spelling counterparts (KJV uses -our/-ise/-re).

    Rule-based and deliberately generous — over-generation only adds
    recall alternatives (bounded per group), never removes. Each
    alternative is stemmed by callers before use.
    """
    out = []
    seen = {word}
    pairs = (("or", "our"), ("ize", "ise"), ("er", "re"))
    for a, b in pairs:
        if word.endswith(a) and len(word) > len(a) + 1:
            cand = word[: -len(a)] + b
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
        if word.endswith(b) and len(word) > len(b) + 1:
            cand = word[: -len(b)] + a
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out[:2]


def _prefilter_groups(query: str) -> List[str]:
    """MATCH-ready groups: each content word as a stemmed prefix, paired
    with its raw surface form and British/American spelling variants:
    `(stem* OR var1* OR "raw")` when they differ, so accented text
    matches either spelling and inflections match their family on the
    unstemmed index. FTS syntax is neutralized by construction (stems
    are alnum; raw forms are double-quoted)."""
    import re as _re
    from core.text_utils import split_search_words, fold_diacritics, STEMMER
    groups: List[str] = []
    seen = set()

    def _stem_term(surface: str):
        term = f"{STEMMER.stemWord(surface)}*"
        if term not in seen:
            seen.add(term)
            return term
        return None

    for tok in (query or "").split():
        parts = split_search_words(tok)
        raw = tok.replace('"', '""').strip()
        raw_group = None
        if raw and _re.search(r"\w", raw, _re.UNICODE) \
                and raw.lower() != fold_diacritics(tok).lower() \
                and raw not in seen:
            raw_group = f'"{raw}"'
            seen.add(raw)
        members = []
        stems_here = []
        for w in parts:
            stem = STEMMER.stemWord(w)
            stems_here.append(stem)
            term = _stem_term(w)
            if term is not None:
                members.append(term)
        # Variants from stems too ("colors"→"color"→"colour").
        for stem in stems_here:
            for variant in _variant_forms(stem):
                vterm = _stem_term(variant)
                if vterm is not None:
                    members.append(vterm)
        if raw_group is not None:
            members.append(raw_group)
        if not members:
            continue
        groups.append(members[0] if len(members) == 1
                      else f"({' OR '.join(members)})")
        if len(groups) >= 32:
            break
    return groups


def _group_stem(group: str) -> str:
    """Bare stem of a prefilter group (for stopword checks)."""
    return group.lstrip("(").split("*")[0].split()[0].strip('"').lower()


def _fts_candidate_ids(query: str, version: str, limit: int,
                       match_all: bool = False) -> tuple[List[int], set]:
    """FTS5 recall prefilter: (verse rowids rank-first, relaxed rowids).

    AND-first, OR-top-up: the AND of the terms is fast and already
    contains the best hits; only a thin AND set pays for per-term
    top-ups (same terms ORed would bury single-term hits past the cap).
    Terms with zero hits anywhere get progressively relaxed prefixes
    (word[:-1]*, word[:-2]* while len ≥ 2) so typos still seed the pool;
    relaxed hits are reported separately — the rerank gates its rescue
    lane on that provenance, never on raw scores alone.
    Bare stopwords are skipped (they match everything and rank nothing
    — BM25 strips them too, so recall is unaffected); quoted raw
    alternatives always stay (accented recall). match_all (AND) is the
    stopword-only fallback (no top-up: ORing stopwords is pure noise).
    """
    from core.text_utils import STOP_WORDS
    groups = _prefilter_groups(query)
    if not groups:
        return [], set()
    if not match_all:
        # Drop bare stopword groups (they match everything and rank
        # nothing — BM25 strips them too, so recall is unaffected).
        # Quoted raw alternatives always stay (accented recall).
        kept = [g for g in groups if _group_stem(g) not in STOP_WORDS
                or g.startswith("(")]
        groups = kept or groups
    and_q = " ".join(groups)
    if match_all:
        # Degenerate query: arbitrary slice, no rank sort (sorting tens
        # of thousands of stopword matches is pure cost; nothing here
        # can be meaningfully ordered without scoring tokens anyway).
        return _fts_match_ids(and_q, version, 100, order=False), set()
    ids = _fts_match_ids(and_q, version, limit)
    relaxed: set = set()
    seen = set(ids)
    if len(groups) == 1:
        # Single word: the AND already exhausted the exact form, so only
        # relaxation can add anything (the typo-rescue case).
        if not ids and not groups[0].startswith("("):
            stem = _group_stem(groups[0])
            if len(stem) >= 3:
                cut = stem[:-1]
                while len(cut) >= 2:
                    hits = _fts_match_ids(cut + "*", version, 100)
                    if hits:
                        for rid in hits:
                            if rid not in seen:
                                seen.add(rid)
                                ids.append(rid)
                                relaxed.add(rid)
                        break
                    cut = cut[:-1]
        return ids, relaxed
    # Per-term top-up (not one OR sweep): each query word contributes
    # its own best hits, so verses matching only ONE word — the
    # indirect case BM25 is loved for — still surface. An OR sweep
    # would bury them past the cap under multi-match verses.
    # Short stems (< 3 chars) sit out: ubiquitous, expensive to rank,
    # and noise as single-term recall (they stay in the AND above).
    topup = [g for g in groups if len(_group_stem(g)) >= 3]
    per_term = max(50, (limit - len(ids)) // max(1, len(topup)) + 1)
    for group in topup:
        if len(ids) >= limit:
            break
        hits = _fts_match_ids(group, version, per_term)
        is_relaxed = False
        if not hits and not group.startswith("("):
            # Zero-hit bare stem (typo or rare form): progressively
            # relax trailing chars until something matches. Only ids
            # arriving via THIS path join the rescue set below.
            cut = _group_stem(group)[:-1]
            while not hits and len(cut) >= 2:
                hits = _fts_match_ids(cut + "*", version, per_term)
                if hits:
                    is_relaxed = True
                cut = cut[:-1]
        for rid in hits:
            if rid not in seen:
                seen.add(rid)
                ids.append(rid)
                if is_relaxed:
                    relaxed.add(rid)
                if len(ids) >= limit:
                    break
    return ids, relaxed


def _fts_match_ids(match_q: str, version: str, limit: int,
                   order: bool = True) -> List[int]:
    """Run one FTS MATCH query, return rowids rank-first (or []).

    order=False skips the rank sort (arbitrary slice) for degenerate
    queries where sorting is pure cost.
    """
    order_sql = "ORDER BY rank " if order else ""
    try:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT fts.rowid AS rowid "
            "FROM verses_fts fts "
            "JOIN verses v ON v.id = fts.rowid "
            "WHERE fts.text MATCH ? AND v.version = ? "
            f"{order_sql}LIMIT ?",
            (match_q, version.upper(), limit),
        ).fetchall()
        conn.close()
        return [r["rowid"] for r in rows]
    except sqlite3.OperationalError as e:
        logger.warning("FTS prefilter failed for %r: %s", match_q, e)
        return []


def _fetch_verse_dicts(version: str, rowids: List[int],
                       limit: int) -> List[Dict]:
    """Fetch verse dicts for rowids (DB order), formatted FTS-rank-first."""
    if not rowids:
        return []
    try:
        conn = _get_connection()
        placeholders = ",".join("?" for _ in rowids)
        rows = conn.execute(
            "SELECT id AS rowid, book, chapter, verse_num, text FROM verses "
            f"WHERE version = ? AND rowid IN ({placeholders})",
            (version.upper(), *rowids),
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning("Verse fetch failed: %s", e)
        return []
    by_id = {r["rowid"]: r for r in rows}
    out = []
    for rid in rowids:
        r = by_id.get(rid)
        if r is None:
            continue
        out.append({"rowid": rid, "book": r["book"], "chapter": r["chapter"],
                    "verse": r["verse_num"], "verse_num": r["verse_num"],
                    "text": r["text"], "confidence": 1.0})
        if len(out) >= limit:
            break
    return out






def _grams_of_folded(s: str) -> set:
    """Trigram set of folded spaceless text (typo-tolerant)."""
    import re as _re
    t = _re.sub(r"[^a-z0-9]", "", s or "")
    if len(t) < 3:
        return {t} if t else set()
    return {t[i:i + 3] for i in range(len(t) - 2)}


def _trigram_profile(text: str) -> set:
    """Character-3-gram set of folded spaceless text (typo-tolerant)."""
    from core.text_utils import fold_diacritics
    return _grams_of_folded(fold_diacritics(text or "").lower())


def _trigram_dice(query_grams: set, verse_grams: set) -> float:
    if not query_grams or not verse_grams:
        return 0.0
    return 2.0 * len(query_grams & verse_grams) / (
        len(query_grams) + len(verse_grams))


def _surface_words(text: str) -> list:
    """Lowercased word surfaces (unicode letters, interior apostrophes)."""
    from core.text_utils import fold_diacritics
    return _SURFACE_RE.findall(fold_diacritics(text or "").lower())


_SURFACE_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)

_GROUP_PART_RE = re.compile(r'"([^"]+)"|([^\W_]+)\*', re.UNICODE)


def _group_match_specs(groups: List[str]) -> list:
    """Decompose MATCH groups into tests the verse text can be scored by.

    Each spec is `(stem_prefixes, raw_phrases)`. A verse carries the
    group when any of its words stems to a prefix FTS5 would accept for
    `stem*`, or when a quoted raw alternative appears as a token phrase.
    This is how coverage is counted from the verse itself instead of
    inferred from which probe happened to return the row.
    """
    specs = []
    for group in groups:
        prefixes = []
        raws = []
        for match in _GROUP_PART_RE.finditer(group or ""):
            if match.group(1) is not None:
                raws.append(tuple(_surface_words(match.group(1))))
            else:
                prefixes.append(match.group(2).lower())
        specs.append((tuple(dict.fromkeys(prefixes)),
                      tuple(dict.fromkeys(raws))))
    return specs


def _coverage_count(text: str, specs: list, stem_cache: dict) -> int:
    """How many query groups this verse literally carries.

    Pure prefix matching, mirroring the FTS5 `stem*` rule: one covered
    group per query word, no partial credit and no proximity weighting.
    `stem_cache` is shared across the result pool so each surface word is
    stemmed once.
    """
    from core.text_utils import STEMMER
    words = []
    for surface in _surface_words(text):
        words.extend(part for part in surface.split("'") if part)
    stems = [stem_cache.setdefault(w, STEMMER.stemWord(w)) for w in words]
    covered = 0
    for prefixes, raws in specs:
        if any(stem.startswith(prefix)
               for stem in stems for prefix in prefixes):
            covered += 1
            continue
        for raw in raws:
            if not raw:
                continue
            if len(raw) == 1:
                hit = raw[0] in words
            else:
                hit = any(tuple(words[i:i + len(raw)]) == raw
                          for i in range(len(words) - len(raw) + 1))
            if hit:
                covered += 1
                break
    return covered


def _partial_pool_groups(groups: List[str]) -> List[str]:
    """Groups that seed the partial-match OR pool.

    Longest stems first: they discriminate, and short function words
    only enlarge the scan. A query with fewer than two long words keeps
    its short ones, so "noah ark" still probes both terms; the cap keeps
    the number of OR operands independent of query length.
    """
    from core.constants import FTS_PARTIAL_MIN_STEM, FTS_PARTIAL_TERMS
    chosen = [g for g in groups
              if len(_group_stem(g)) >= FTS_PARTIAL_MIN_STEM]
    if len(chosen) < 2:
        chosen_set = set(chosen)
        rest = sorted((g for g in groups if g not in chosen_set),
                      key=lambda g: (-len(_group_stem(g)), g))
        chosen.extend(rest[:2 - len(chosen)])
    chosen.sort(key=lambda g: (-len(_group_stem(g)), g))
    return chosen[:FTS_PARTIAL_TERMS]


def _matched_surfaces(text: str, query_stems: set,
                      query_grams: set) -> list:
    """Verse surfaces explaining the hit: stem matches plus the most
    typo-similar word per query word (Dice >= 0.3). Powers highlight.
    Query grams are precomputed once per search (never per word)."""
    from core.text_utils import STEMMER
    out = []
    for w in _surface_words(text):
        if STEMMER.stemWord(w) in query_stems:
            out.append(w)
            continue
        if len(w) >= 4 and _trigram_dice(
                query_grams, _trigram_profile(w)) >= 0.3:
            out.append(w)
    seen = set()
    uniq = []
    for w in out:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


def _prompt_overlap(query_tokens: set, prompt: str) -> float:
    """Overlap coefficient between a query and a logged prompt.

    |intersection| / min(|A|, |B|): a shorter prompt fully contained in
    a longer query (or vice versa — the operator added just one more
    thing) scores 1.0. Symmetric with search tokenization, so
    diacritics fold on both sides. Takes the best of raw-word and
    stemmed overlap so inflection drift across sessions ("loved" vs
    "love") still counts; raw-word behavior is unchanged.
    """
    from core.text_utils import split_search_words, tokenize, STEMMER
    logged = set(split_search_words(prompt))
    if not logged or not query_tokens:
        return 0.0
    raw = len(query_tokens & logged) / min(len(query_tokens), len(logged))
    if raw >= 1.0:
        return raw
    stemmed_q = {STEMMER.stemWord(w) for w in query_tokens}
    stemmed_logged = set(tokenize(prompt))
    if not stemmed_logged or not stemmed_q:
        return raw
    stem = len(stemmed_q & stemmed_logged) / min(len(stemmed_q),
                                                 len(stemmed_logged))
    return max(raw, stem)


def popularity_boosts(query: str) -> dict:
    """{(book, chapter, verse): boost} from operator pick history.

    Every logged prompt resembling the query contributes
    log(1 + points) × similarity for its verse; multiple prompts per
    verse accumulate (old phrasings are kept, never collapsed). Empty
    when nothing resembles. Never raises.
    """
    from core.text_utils import split_search_words
    from core.constants import POPULARITY_SIM_THRESHOLD
    from core.database import read_verse_popularity
    import math
    try:
        tokens = set(split_search_words(query))
        if not tokens:
            return {}
        boosts: dict = {}
        for row in read_verse_popularity():
            sim = _prompt_overlap(tokens, row.get("prompt", ""))
            if sim < POPULARITY_SIM_THRESHOLD:
                continue
            try:
                pts = float(row.get("points") or 0)
            except (TypeError, ValueError):
                continue
            if pts <= 0:
                continue
            key = (str(row.get("book") or "").lower(),
                   str(row.get("chapter") or ""),
                   str(row.get("verse") or ""))
            boosts[key] = boosts.get(key, 0.0) + math.log1p(pts) * sim
        return boosts
    except Exception:
        return {}


def apply_popularity(results: list, boosts: dict) -> list:
    """Fold popularity into confidence and re-sort (stable).

    Boost is confidence-space: weight × log-dampened points ×
    similarity — one or two picks nudge, dozens eventually top.
    Mutates confidence in place (the badge then reflects why a verse
    leads). Never raises.
    """
    from core.constants import POPULARITY_WEIGHT
    try:
        if not boosts or not results:
            return results
        for r in results:
            key = (str(r.get("book") or "").lower(),
                   str(r.get("chapter") or ""),
                   str(r.get("verse_num", r.get("verse")) or ""))
            bump = boosts.get(key)
            if bump:
                base = r.get("confidence", 0) or 0
                raw = base + POPULARITY_WEIGHT * bump
                # The badge is a percentage, so it is capped — but the cap
                # must not flatten ordering. Two verses both sitting at
                # 100% would tie and be separated only by input order,
                # which throws away what the operator just taught us.
                # So the uncapped score is kept for ranking.
                r["confidence_rank"] = raw
                r["confidence"] = round(min(100.0, raw), 1)
                r["boosted"] = True
        results.sort(key=lambda r: r.get("confidence_rank")
                     if r.get("confidence_rank") is not None
                     else (r.get("confidence", 0) or 0), reverse=True)
        return results
    except Exception:
        return results








def _fts_ranked(match_q: str, version: str, limit: int) -> List[tuple]:
    """One FTS5 MATCH query as `[(rowid, score)]`, best first.

    `score` is `-bm25(verses_fts)`, i.e. positive and larger-is-better
    (FTS5's raw bm25 is negative-better). This is the whole relevance
    signal for the FTS lane: SQLite's own keyword scorer, computed over
    the Porter-stemmed index. Returns [] on an FTS error rather than
    raising — the panel treats a failed lane as "no hits".
    """
    try:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT fts.rowid AS rowid, bm25(verses_fts) AS score "
            "FROM verses_fts fts "
            "JOIN verses v ON v.id = fts.rowid "
            "WHERE fts.text MATCH ? AND v.version = ? "
            "ORDER BY rank LIMIT ?",
            (match_q, version.upper(), limit),
        ).fetchall()
        conn.close()
        return [(r["rowid"], -r["score"]) for r in rows]
    except sqlite3.OperationalError as e:
        logger.warning("FTS query failed for %r: %s", match_q, e)
        return []


def fts_search(query: str, version: str = "KJV",
               limit: int = 20) -> List[Dict]:
    """FTS5 keyword search over the Porter-stemmed verse index.

    Ranking is keyword match and nothing else:

      1. coverage — how many distinct query words the verse actually
         carries (most-matches-wins);
      2. SQLite FTS5's own bm25 over those terms.

    Nothing learned, blended or semantic is mixed in. A verse that
    literally contains the words the operator typed outranks one that is
    merely about them — which is the whole point of having the Nave and
    Strong's lanes beside this one.

    Recall is AND-first: the AND of the query terms is what an operator
    searching for a phrase actually wants. When that set is thin, one
    bounded OR sweep over the query's most discriminating words fills the
    pool with partial matches, and coverage is then counted from each
    verse's own text — so a verse carrying five of six words beats a
    verse carrying one, even if the operator mistyped the sixth.
    """
    from core.text_utils import split_search_words, STOP_WORDS, tokenize
    words = split_search_words(query)
    if not words:
        return []
    all_groups = _prefilter_groups(query)
    # Bare stopwords match everything and rank nothing. Quoted raw
    # alternatives always stay (accented recall).
    groups = [g for g in all_groups
              if _group_stem(g) not in STOP_WORDS or g.startswith("(")]
    if not groups:
        # Stopword-only query: any verse "matches". An arbitrary slice is
        # honest here — ordering stopword matches by keyword score is
        # meaningless, so we don't pretend otherwise.
        return _fetch_verse_dicts(
            version, _fts_match_ids(" ".join(all_groups), version, limit,
                                    order=False), limit)

    # FTS5 will not read a parenthesised group as an implicit-AND operand
    # ("a* (b* OR c*)" is a syntax error), so the conjunction is explicit.
    # Over-fetch before the adjacency tie-break: the exact phrase can sit
    # just below bm25's cutoff and should still be allowed to win.
    from core.constants import FTS_AND_POOL_EXTRA
    and_pool = max(limit * 3, limit + FTS_AND_POOL_EXTRA)
    ranked = _fts_ranked(" AND ".join(groups), version, and_pool)
    and_ids = [rid for rid, _ in ranked]
    ids = list(and_ids)
    score = {rid: sc for rid, sc in ranked}

    if len(groups) > 1 and len(ids) < limit:
        # Thin AND: one bounded OR sweep so verses carrying MOST of the
        # words still enter the pool. Without it, a single irrelevant word
        # ("mountain" where the operator meant "rock") excludes a 5-of-6
        # verse from the AND set, and per-term probes only surface
        # single-word hits — the exact miss that buried Matthew 16:18.
        from core.constants import FTS_PARTIAL_POOL
        pool = max(FTS_PARTIAL_POOL, limit * 4)
        pool_groups = _partial_pool_groups(groups)
        for rid, sc in _fts_ranked(" OR ".join(pool_groups), version, pool):
            if rid not in score:
                score[rid] = sc
                ids.append(rid)

    if len(groups) > 1 and len(ids) < limit:
        # Still short (rare words): bounded per-term filler. Each probe is
        # a prefix scan, so this stays a last resort — coverage below does
        # not depend on which probe happened to return a row.
        from core.constants import FTS_TOPUP_TERMS
        probes = sorted(groups,
                        key=lambda g: (-len(_group_stem(g)), g))[:FTS_TOPUP_TERMS]
        per_term = max(50, (limit - len(ids)) // max(1, len(probes)) + 1)
        for group in probes:
            for rid, sc in _fts_ranked(group, version, per_term):
                if rid not in score:
                    score[rid] = sc
                    ids.append(rid)

    verses = {v["rowid"]: v for v in _fetch_verse_dicts(version, ids, len(ids))}
    distinct = max(1, len(groups))

    # Coverage is counted from the verse text itself, not inferred from
    # which probe returned the row. A verbatim 5-of-6 match therefore
    # outranks a 1-of-6 single-word hit. AND rows are full coverage by
    # construction: the conjunction proved every group matched.
    if len(and_ids) >= limit:
        coverage = {rid: distinct for rid in and_ids}
    else:
        specs = _group_match_specs(groups)
        stem_cache = {}
        coverage = {rid: _coverage_count(v["text"], specs, stem_cache)
                    for rid, v in verses.items()}
        for rid in and_ids:
            if rid in coverage:
                coverage[rid] = distinct

    # Adjacency: among verses carrying the SAME number of query words, the
    # one holding them side by side ("living water") is a sharper keyword
    # hit than one scattering them. Tied-break only — it must never let a
    # partial-coverage verse outrank a fuller one. Still pure keyword
    # matching: one extra FTS5 phrase probe, no learned score.
    adjacent = set()
    if len(words) > 1:
        # One quoted phrase, not a quote per word: FTS5 reads `"a" "b"`
        # as an AND of two phrases, which is just the AND we already ran.
        phrase = '"' + " ".join(words) + '"'
        adjacent = {rid for rid, _ in _fts_ranked(phrase, version, limit * 4)}

    order = sorted(ids, key=lambda rid: (coverage.get(rid, 0),
                                         rid in adjacent,
                                         score.get(rid, 0.0)), reverse=True)

    query_grams = _trigram_profile(" ".join(words))
    match_stems = set(tokenize(query)) | {
        v for g in groups for v in _variant_forms(_group_stem(g))}
    results = []
    for position, rid in enumerate(order[:limit]):
        v = verses.get(rid)
        if v is None:
            continue
        # Strictly decreasing in emitted position so the panel's
        # confidence badge never contradicts the row order.
        conf = (100.0 * (0.35 + 0.65 * min(1.0, coverage.get(rid, 0) / distinct))
                * (1.0 - 0.5 * position / max(1, limit)))
        results.append({
            "book": v["book"], "chapter": v["chapter"],
            "verse": v["verse_num"], "verse_num": v["verse_num"],
            "text": v["text"],
            "confidence": round(conf, 1),
            "coverage": coverage.get(rid, 0),
            "matched": _matched_surfaces(v["text"], match_stems, query_grams),
        })
    return results


# ─── Keyword lane (Nave's topics + Strong's lemmas) ──────────────────────────

_keywords_compact = None
_keywords_missing_logged = False


def _load_keywords() -> Optional[dict]:
    """Lazy-load the keyword postings compact (once per process)."""
    global _keywords_compact, _keywords_missing_logged
    if _keywords_compact is not None:
        return _keywords_compact
    kw_path = os.path.join(_INDEXES_DIR, "keywords.pkl")
    if not os.path.exists(kw_path):
        if not _keywords_missing_logged:
            logger.warning("Keyword index not found — run build_keywords.py")
            _keywords_missing_logged = True
        return None
    try:
        with open(kw_path, "rb") as f:
            _keywords_compact = pickle.load(f)
        logger.info(f"Loaded keyword index: "
                    f"{len(_keywords_compact['postings']):,} terms, "
                    f"{_keywords_compact['corpus_size']:,} verses")
    except Exception as e:
        logger.warning(f"Keyword index load failed: {e}")
        return None
    return _keywords_compact


def fts_translations() -> List[str]:
    """Translations the FTS lane searches: the operator's choice.

    Stored as JSON in `search.fts_translations`. Read live rather than
    cached so changing it in Settings takes effect on the next query, and
    clamped to what is actually installed so a translation that was
    removed from bible.db cannot poison the lane into returning nothing.
    """
    import json
    from core.constants import (FTS_TRANSLATIONS, FTS_MAX_TRANSLATIONS)
    from core.database import get_setting
    raw = get_setting("search.fts_translations", None)
    chosen: List[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                chosen = [str(v).strip() for v in parsed if str(v).strip()]
        except (TypeError, ValueError):
            chosen = []
    if not chosen:
        chosen = list(FTS_TRANSLATIONS)
    # De-duplicate, keep order, cap.
    seen = set()
    ordered = []
    for v in chosen:
        key = v.upper()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    ordered = ordered[:FTS_MAX_TRANSLATIONS]
    available = set(get_available_translations())
    kept = [v for v in ordered if v in available]
    return kept or [v for v in FTS_TRANSLATIONS if v in available] or \
        list(FTS_TRANSLATIONS)[:1]


def set_fts_translations(values) -> List[str]:
    """Persist the operator's FTS translation choice. Returns what stuck."""
    import json
    from core.constants import FTS_MAX_TRANSLATIONS
    from core.database import set_setting
    seen, ordered = set(), []
    for v in values or []:
        key = str(v).strip().upper()
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    ordered = ordered[:FTS_MAX_TRANSLATIONS]
    set_setting("search.fts_translations", json.dumps(ordered))
    return ordered


def keyword_display_translation() -> str:
    """Translation used to render keyword-lane hits (operator setting)."""
    from core.database import get_setting
    want = (get_setting("search.keyword_display_translation", "KJV")
            or "KJV").upper()
    try:
        conn = _get_connection()
        row = conn.execute(
            "SELECT 1 FROM verses WHERE version = ? LIMIT 1",
            (want,)).fetchone()
        conn.close()
        if row:
            return want
    except Exception:
        pass
    return "KJV"


def keyword_search(query: str, limit: int = 30):
    """Score the keyword index for a query (once per query, not per version).

    Returns (results, elapsed_ms, display_version). Each result carries
    verse text fetched live from the operator's display translation, in
    the same dict shape as fts_search (confidence normalized 0–100).
    Missing index → ([], 0.0, display_version): the lane degrades away.
    """
    import time as _time
    from core.text_utils import split_search_words, STOP_WORDS
    from core.constants import KEYWORD_COVERAGE_MIX
    t0 = _time.perf_counter()
    display = keyword_display_translation()
    compact = _load_keywords()
    if compact is None:
        return [], 0.0, display
    words = split_search_words(query)
    if not words or all(w.strip('"').lower() in STOP_WORDS for w in words):
        return [], (_time.perf_counter() - t0) * 1000, display
    tokens = tokenize(query)
    if not tokens:
        return [], (_time.perf_counter() - t0) * 1000, display
    variant_words = []
    for stem in set(tokens):
        variant_words.extend(_variant_forms(stem))
    variant_tokens = tokenize(" ".join(variant_words)) if variant_words else []
    all_tokens = tokens + variant_tokens
    scores, hits = _score_postings(compact, all_tokens)
    distinct = len(set(tokens)) or 1
    coverage = np.minimum(1.0, hits.astype(np.float64) / distinct)
    blended = scores * (KEYWORD_COVERAGE_MIX
                        + (1.0 - KEYWORD_COVERAGE_MIX) * coverage)
    order = np.argsort(blended)[::-1][:limit]
    order = [i for i in order if blended[i] > 0]
    if not order:
        return [], (_time.perf_counter() - t0) * 1000, display
    best = float(blended[order[0]])
    # Fetch display-translation texts for the hit coordinates in one query.
    coords = [(compact["lookup"][i][1], compact["lookup"][i][2],
               compact["lookup"][i][3]) for i in order]
    texts = {}
    try:
        conn = _get_connection()
        # Row-value IN keeps the covering index seeks (~0.5ms); a
        # disjunct OR chain degrades to a 31k-row index scan (~35ms).
        place = ",".join(["(?,?,?)"] * len(coords))
        params = [p for c in coords for p in c]
        for r in conn.execute(
                "SELECT book, chapter, verse_num, text FROM verses "
                "WHERE version = ? AND (book, chapter, verse_num) "
                f"IN ({place})",
                (display, *params)).fetchall():
            texts[(r["book"], r["chapter"], r["verse_num"])] = r["text"]
        conn.close()
    except Exception as e:
        logger.warning("Keyword text fetch failed: %s", e)
    match_stems = set(tokens) | set(variant_tokens)
    query_grams = _trigram_profile(" ".join(words))
    results = []
    for i in order:
        _ver, book, chapter, verse_num, _kw = compact["lookup"][i]
        text = texts.get((book, chapter, verse_num), "")
        results.append({
            "book": book, "chapter": chapter,
            "verse": verse_num, "verse_num": verse_num,
            "text": text,
            "confidence": round(min(100.0, 100.0 * float(blended[i]) / best), 1),
            "matched": _matched_surfaces(text, match_stems, query_grams),
            "keyword": True,
        })
    return results, (_time.perf_counter() - t0) * 1000, display


# ─── Translation Import ──────────────────────────────────────────────────────


def refresh_available_translations() -> List[str]:
    """Re-query bible.db and update the module-level AVAILABLE_TRANSLATIONS."""
    global AVAILABLE_TRANSLATIONS
    AVAILABLE_TRANSLATIONS = get_available_translations()
    return AVAILABLE_TRANSLATIONS


def import_translation_file(filepath: str) -> str:
    """Import a Bible source file into the app.

    Steps:
      1. Convert to JSON (XML/XMM via bible_to_json, CSV inline, JSON copied)
      2. Load JSON into bible.db
      3. Rebuild FTS index

    Returns the translation abbreviation (e.g. "NKJV").
    Raises on any failure.
    """
    ext = os.path.splitext(filepath)[1].lower()
    os.makedirs(_JSON_DIR, exist_ok=True)

    if ext in (".xml", ".xmm"):
        json_path = _import_xml(filepath)
    elif ext == ".csv":
        json_path = _import_csv(filepath)
    elif ext == ".json":
        json_path = _import_json(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # Load into SQLite
    version = _load_into_db(json_path)

    # Rebuild BM25 cache for this version (invalidate so it reloads next search)
    _bm25_cache.pop(version, None)

    # Build BM25 index for just this version (fast, <1s)
    _build_bm25_for_version(version)

    logger.info(f"Imported translation '{version}' from {filepath}")
    return version


def _import_xml(filepath: str) -> str:
    """Convert XML/XMM to JSON via bible_to_json. Returns JSON path."""
    # Add data/bible to sys.path so we can import bible_to_json
    bible_dir = os.path.join(_PROJECT_ROOT, "data", "bible")
    if bible_dir not in sys.path:
        sys.path.insert(0, bible_dir)

    from bible_to_json import convert_file
    return convert_file(filepath, _JSON_DIR)


def _import_csv(filepath: str) -> str:
    """Convert CSV to JSON. Returns JSON path.

    Handles two CSV formats:
      1. Standard: columns book, chapter, verse, text (and optional version)
      2. Reference-based: first column is "Reference" (e.g. "Genesis 1:1"),
         second column is the verse text. Version derived from filename.
    """
    import re as _re

    versions: dict = {}
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # Detect reference-based format (e.g. BSB.csv: "Reference,Berean Standard Bible")
        is_ref_format = len(fieldnames) >= 2 and fieldnames[0].strip().lower() == "reference"

        for row in reader:
            if is_ref_format:
                # Parse "Genesis 1:1" → book="Genesis", chapter="1", verse="1"
                ref_raw = row[fieldnames[0]].strip()
                text_col = fieldnames[1].strip()
                text = row.get(text_col, "").strip()
                if not text:
                    continue

                # Match: "Book Name Ch:V" or "Book Name Ch:V-Range"
                m = _re.match(r"^(.+?)\s+(\d+):(\d+)", ref_raw)
                if not m:
                    continue
                book = m.group(1).strip()
                chap = m.group(2)
                verse = m.group(3)

                # Version from filename (e.g. BSB.csv → "BSB")
                ver = os.path.splitext(os.path.basename(filepath))[0].upper()
            else:
                # Standard format: book, chapter, verse, text columns
                ver = row.get("version", os.path.splitext(os.path.basename(filepath))[0]).upper()
                book = row["book"]
                chap = str(row["chapter"])
                verse = str(row["verse"])
                text = row["text"].strip()

            if ver not in versions:
                versions[ver] = {"translation": ver, "books": {}}
            books = versions[ver]["books"]
            if book not in books:
                books[book] = {}
            if chap not in books[book]:
                books[book][chap] = {}
            books[book][chap][verse] = text

    import json
    out_paths = []
    for ver, data in versions.items():
        out_path = os.path.join(_JSON_DIR, f"{ver.lower()}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        out_paths.append(out_path)
        logger.info(f"CSV → JSON: [{ver}] {out_path}")

    if not out_paths:
        raise ValueError("CSV file contained no valid verse rows")
    return out_paths[0]


def _import_json(filepath: str) -> str:
    """Copy a JSON file into the json directory. Returns destination path."""
    import json as _json

    # Validate it's a Bible JSON
    with open(filepath, "r", encoding="utf-8") as f:
        data = _json.load(f)
    if "translation" not in data or "books" not in data:
        raise ValueError("Invalid Bible JSON: missing 'translation' or 'books' key")

    ver = data["translation"]
    dest = os.path.join(_JSON_DIR, f"{ver.lower()}.json")
    if os.path.abspath(filepath) != os.path.abspath(dest):
        shutil.copy2(filepath, dest)
        logger.info(f"Copied JSON: {filepath} → {dest}")
    return dest


def _load_into_db(json_path: str) -> str:
    """Load a single JSON file into bible.db. Returns version string."""
    import json

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    version = data["translation"]

    conn = sqlite3.connect(_BIBLE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")

    # Create schema if needed
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS verses (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            version    TEXT    NOT NULL,
            book       TEXT    NOT NULL,
            chapter    INTEGER NOT NULL,
            verse_num  INTEGER NOT NULL,
            text       TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_fingerprints (
            version     TEXT PRIMARY KEY,
            sha256      TEXT    NOT NULL,
            filename    TEXT    NOT NULL,
            verse_count INTEGER NOT NULL,
            built_at    TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_verses_lookup
            ON verses(version, book, chapter, verse_num);
        CREATE INDEX IF NOT EXISTS idx_verses_version
            ON verses(version);
        -- No `content=` option: an external-content FTS5 table mirrors its
        -- whole source table and cannot be restricted to the chosen
        -- translations. This table owns its text and holds only what
        -- fts_translations() selects.
        CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
            text,
            tokenize='porter unicode61 remove_diacritics 2'
        );
    """)

    # Delete existing rows for this version (idempotent)
    conn.execute("DELETE FROM verses WHERE version = ?", (version,))

    # Batch insert all verses
    rows = []
    books = data["books"]
    for book_name, chapters in books.items():
        for chap_num, verses in chapters.items():
            for verse_num, text in verses.items():
                rows.append((version, book_name, int(chap_num), int(verse_num), text.strip()))

    conn.executemany(
        "INSERT INTO verses (version, book, chapter, verse_num, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )

    # Record fingerprint
    import hashlib
    from datetime import datetime, timezone
    sha = hashlib.sha256()
    with open(json_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO source_fingerprints
           (version, sha256, filename, verse_count, built_at)
           VALUES (?, ?, ?, ?, ?)""",
        (version, sha.hexdigest(), os.path.basename(json_path), len(rows), now),
    )

    # Add this translation to the search index if it is one the operator
    # searches. Anything else stays out until chosen (and rebuilt).
    if version.upper() in {t.upper() for t in fts_translations()}:
        conn.execute("DELETE FROM verses_fts WHERE rowid IN "
                     "(SELECT id FROM verses WHERE version = ?)", (version,))
        conn.execute(
            "INSERT INTO verses_fts(rowid, text) "
            "SELECT id, text FROM verses WHERE version = ?", (version,))
    conn.commit()
    conn.close()

    logger.info(f"Loaded [{version}] {len(rows):,} verses into {_BIBLE_DB_PATH}")
    return version


def _build_bm25_for_version(version: str):
    """Build BM25 index for a single translation version.

    Reads verses from bible.db, tokenizes, builds BM25Okapi, and writes
    data/indexes/bm25_{VERSION}.pkl + verse_lookup_{VERSION}.pkl.
    Fast (<1s) since it only processes one version.
    """
    import sqlite3
    import pickle
    import time
    from collections import defaultdict
    from rank_bm25 import BM25Okapi
    from core.text_utils import tokenize

    t0 = time.perf_counter()

    conn = sqlite3.connect(str(_BIBLE_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT version, book, chapter, verse_num, text FROM verses "
        "WHERE version = ? ORDER BY book, chapter, verse_num",
        (version,),
    ).fetchall()
    conn.close()

    if not rows:
        logger.warning(f"No verses found for version '{version}', skipping BM25 build")
        return

    verses = [dict(r) for r in rows]

    # Build verse lookup and tokenized corpus
    v_lookup = [
        (v["version"], v["book"], v["chapter"], v["verse_num"], v["text"])
        for v in verses
    ]
    v_tokenized = [tokenize(v["text"]) for v in verses]
    v_bm25 = BM25Okapi(v_tokenized)

    # Write pickle files
    output_dir = os.path.join(_PROJECT_ROOT, "data", "indexes")
    os.makedirs(output_dir, exist_ok=True)

    bm25_path = os.path.join(output_dir, f"bm25_{version}.pkl")
    lookup_path = os.path.join(output_dir, f"verse_lookup_{version}.pkl")

    with open(bm25_path, "wb") as f:
        pickle.dump(v_bm25, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(lookup_path, "wb") as f:
        pickle.dump(v_lookup, f, protocol=pickle.HIGHEST_PROTOCOL)

    elapsed = time.perf_counter() - t0
    bm25_mb = os.path.getsize(bm25_path) / (1024 * 1024)
    lookup_mb = os.path.getsize(lookup_path) / (1024 * 1024)
    logger.info(f"Built BM25 for [{version}]: {len(rows):,} verses, "
                f"{bm25_mb + lookup_mb:.2f} MB, {elapsed:.2f}s")


# ─── Translation Display Names ───────────────────────────────────────────────

_DISPLAY_NAMES_KEY = "bible.translation_display_names"

# Module-level cache: {canonical: display_name}
_display_names_cache: Dict[str, str] = {}
_display_names_loaded = False


def _load_display_names():
    """Load display names from settings into the cache."""
    global _display_names_cache, _display_names_loaded
    if _display_names_loaded:
        return
    from core.database import get_setting
    raw = get_setting(_DISPLAY_NAMES_KEY, "{}")
    try:
        import json as _json
        _display_names_cache = _json.loads(raw)
    except (ValueError, TypeError):
        _display_names_cache = {}
    _display_names_loaded = True


def get_display_name(canonical: str) -> str:
    """Return the display name for a translation, or canonical if no rename."""
    _load_display_names()
    return _display_names_cache.get(canonical, canonical)


def set_display_name(canonical: str, display: str):
    """Set a display name mapping. Updates settings + module cache."""
    global _display_names_cache
    _load_display_names()
    if display and display != canonical:
        _display_names_cache[canonical] = display
    else:
        _display_names_cache.pop(canonical, None)
    from core.database import set_setting
    import json as _json
    set_setting(_DISPLAY_NAMES_KEY, _json.dumps(_display_names_cache))


def get_all_display_names() -> Dict[str, str]:
    """Return the full canonical→display mapping."""
    _load_display_names()
    return dict(_display_names_cache)


# Last rename as (canonical, old_display, new_display) for cascade hooks.
_last_rename: tuple | None = None


def get_last_rename():
    """Return the most recent rename_translation() record, if any."""
    return _last_rename


def _rewrite_item_translation(item: dict, old_display: str, new_display: str) -> bool:
    """Rewrite one schedule-style dict in place. Returns True if changed.

    Only the ref "[Old] ..." prefix is rewritten. The translation field is
    deliberately untouched: schedule items store canonical CODES there, and
    rewriting a code that textually matches would corrupt switching logic.
    (History display rows store display names — those are rewritten by SQL.)
    """
    ref = item.get("ref")
    if isinstance(ref, str):
        prefix, new_prefix = f"[{old_display}]", f"[{new_display}]"
        if ref.startswith(prefix):
            item["ref"] = new_prefix + ref[len(prefix):]
            return True
    return False


def rename_translation(canonical: str, new_display: str) -> str:
    """Rename a translation everywhere, permanently.

    Updates the display-name mapping, rewrites stored copies (schedule files
    on disk, history display rows), and records the rename for UI cascade
    hooks (see get_last_rename). In-memory schedule model + live screens are
    refreshed by the caller (main window). Raises ValueError on bad names.
    Returns the previous display name.
    """
    global _last_rename
    canonical = (canonical or "").strip()
    new_display = (new_display or "").strip()
    if not canonical:
        raise ValueError("No translation specified.")
    if not new_display:
        raise ValueError("Display name cannot be empty.")
    if len(new_display) > 20:
        raise ValueError("Display name must be 20 characters or fewer.")
    try:
        available = [c.upper() for c in get_available_translations()]
    except Exception:
        available = []
    if new_display.upper() in available and new_display.upper() != canonical.upper():
        raise ValueError(f"“{new_display}” collides with a translation code.")
    _load_display_names()
    for code, display in _display_names_cache.items():
        if code != canonical and display.lower() == new_display.lower():
            raise ValueError(f"“{new_display}” is already used by {code}.")

    old_display = get_display_name(canonical)
    set_display_name(canonical, new_display)
    # Verify the write actually landed (a silent settings failure would look
    # exactly like "the rename doesn't stick" — badge updated, mapping lost
    # on restart). _load bypass: read the raw setting back.
    try:
        from core.database import get_setting
        import json as _json2
        raw = get_setting(_DISPLAY_NAMES_KEY, "{}")
        persisted = _json2.loads(raw).get(canonical)
        if persisted != new_display and not (persisted is None and new_display == canonical):
            raise ValueError(
                f"Rename did not persist (read back {persisted!r}). "
                f"Database write failed — check disk/permissions.")
    except ValueError:
        raise
    except Exception as e:
        logger.warning(f"Could not verify rename persistence: {e}")
    _last_rename = (canonical, old_display, new_display)

    if old_display != new_display:
        _rewrite_schedule_files(old_display, new_display)
        _rewrite_history_translations(old_display, new_display)
    return old_display


def _rewrite_schedule_files(old_display: str, new_display: str) -> int:
    """Rewrite stored refs/translations in every saved schedule file."""
    from pathlib import Path
    schedules_dir = Path(__file__).resolve().parent.parent / "data" / "schedules"
    changed_files = 0
    if not schedules_dir.is_dir():
        return 0
    for path in sorted(schedules_dir.glob("*.json")):
        try:
            import json as _json
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
        except Exception as e:
            logger.warning(f"Skipping schedule file during rename: {path.name}: {e}")
            continue
        items = data.get("items", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        changed = False
        for item in items:
            if isinstance(item, dict) and _rewrite_item_translation(item, old_display, new_display):
                changed = True
        if changed:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    _json.dump(data, f, indent=2, ensure_ascii=False)
                changed_files += 1
            except Exception as e:
                logger.warning(f"Failed to rewrite schedule file {path.name}: {e}")
    if changed_files:
        logger.info(f"Rename {old_display!r} → {new_display!r}: rewrote {changed_files} schedule file(s)")
    return changed_files


def _rewrite_history_translations(old_display: str, new_display: str) -> int:
    """Rewrite stored translation labels in history display rows."""
    try:
        from core.database import get_connection
        conn = get_connection()
        cur = conn.execute(
            "UPDATE display_events SET translation=? WHERE translation=?",
            (new_display, old_display),
        )
        count = cur.rowcount or 0
        conn.commit()
        conn.close()
        if count:
            logger.info(f"Rename {old_display!r} → {new_display!r}: rewrote {count} history row(s)")
        return count
    except Exception as e:
        logger.warning(f"Failed to rewrite history translations: {e}")
        return 0


# ─── Translation Order ───────────────────────────────────────────────────────

_ORDER_KEY = "bible.translation_order"

_order_cache: list[str] | None = None


def get_translation_order() -> List[str]:
    """Return the saved translation order, or empty list if none saved."""
    global _order_cache
    if _order_cache is not None:
        return list(_order_cache)
    from core.database import get_setting
    raw = get_setting(_ORDER_KEY, "[]")
    try:
        import json as _json
        _order_cache = _json.loads(raw)
    except (ValueError, TypeError):
        _order_cache = []
    return list(_order_cache)


def set_translation_order(order: List[str]):
    """Persist the translation order to settings."""
    global _order_cache
    _order_cache = list(order)
    from core.database import set_setting
    import json as _json
    set_setting(_ORDER_KEY, _json.dumps(order))
