#!/usr/bin/env python3
"""
build_bm25.py — Build the BM25 inverted index from the Bible SQLite database.

This script reads all verses from bible.db, normalizes them using the same
normalization pipeline that will be used at live-search time (symmetry is
critical for correct BM25 retrieval), builds a BM25Okapi index, and
serializes it to disk.

Normalization rules (symmetric with core/search_engine.py at runtime):
  1. Strip apostrophes (e.g. "God's" → "Gods")
  2. Replace hyphens, dashes, slashes, colons with spaces
  3. Lowercase
  4. Strip custom stop-words: {"the", "is", "a", "and", "to", "of", "in", "that"}
  5. RETAIN archaic vocabulary: thou, hath, unto, thy, etc.

Outputs:
  data/indexes/bm25.pkl           — Pickled BM25Okapi object
  data/indexes/verse_lookup.pkl   — List mapping index position → (version, book, chapter, verse_num, text)
  data/indexes/bm25_fingerprint.json — Build metadata + source DB fingerprints for runtime integrity check

Usage:
  python build_bm25.py [--db-path PATH] [--output-dir PATH]
  python build_bm25.py
  python build_bm25.py --db-path data/bible/bible.db --output-dir data/indexes
"""

import argparse
import hashlib
import json
import os
import pickle
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from core.text_utils import normalize_text, tokenize, STOP_WORDS
from core.constants import FTS_TRANSLATIONS, FUZZY_TRANSLATIONS

# Safety net: normalize book names that vary across translations
BOOK_NAME_ALIASES = {"Psalm": "Psalms"}

def _normalize_book(book: str) -> str:
    return BOOK_NAME_ALIASES.get(book, book)


# ─── Database Loading ─────────────────────────────────────────────────────────

def load_verses(db_path: str, translations: list[str] | None = None) -> list[dict]:
    """Load all verses from the Bible database.

    Args:
        db_path: Path to the SQLite database.
        translations: Optional list of translation codes to filter by.
            When None, all translations are loaded.

    Returns:
        List of dicts: {"version", "book", "chapter", "verse_num", "text"}
        ordered by version, book, chapter, verse_num.
    """
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if translations:
        placeholders = ",".join("?" for _ in translations)
        rows = conn.execute(
            f"SELECT version, book, chapter, verse_num, text FROM verses "
            f"WHERE version IN ({placeholders}) "
            f"ORDER BY version, book, chapter, verse_num",
            translations,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT version, book, chapter, verse_num, text FROM verses "
            "ORDER BY version, book, chapter, verse_num"
        ).fetchall()
    
    verses = [
        {
            "version": r["version"],
            "book": _normalize_book(r["book"]),
            "chapter": r["chapter"],
            "verse_num": r["verse_num"],
            "text": r["text"],
        }
        for r in rows
    ]
    
    conn.close()
    return verses


def load_source_fingerprints(db_path: str) -> dict:
    """Load source fingerprints from the database for integrity tracking."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    fingerprints = {}
    try:
        for row in conn.execute("SELECT version, sha256, verse_count FROM source_fingerprints ORDER BY version"):
            fingerprints[row["version"]] = {
                "sha256": row["sha256"],
                "verse_count": row["verse_count"],
            }
    except sqlite3.OperationalError:
        print("[WARNING] No source_fingerprints table found in database.")
    
    conn.close()
    return fingerprints


# ─── Index Building ───────────────────────────────────────────────────────────

def build_bm25_index(db_path: str, output_dir: str, translations: list[str] | None = None):
    """Build the BM25 inverted index and save to disk.

    Produces three files:
      - bm25.pkl:              The pickled BM25Okapi object
      - verse_lookup.pkl:      Index position → (version, book, chapter, verse_num, text)
      - bm25_fingerprint.json: Build metadata for runtime integrity verification

    Args:
        translations: Restrict the index to these translation codes.
            When None, all translations in the DB are indexed (legacy behavior).
    """
    from rank_bm25 import BM25Okapi
    
    t0 = time.perf_counter()
    
    # ── Load verses ───────────────────────────────────────────────────────
    print("  Loading verses from database...")
    verses = load_verses(db_path, translations)
    print(f"  Loaded {len(verses):,} verses"
          + (f" ({len(translations)} translations: {', '.join(translations)})" if translations else " (all translations)"))
    
    # ── Build verse lookup ────────────────────────────────────────────────
    # verse_lookup[i] corresponds to tokenized_corpus[i]
    verse_lookup = [
        (v["version"], v["book"], v["chapter"], v["verse_num"], v["text"])
        for v in verses
    ]
    
    # ── Tokenize ──────────────────────────────────────────────────────────
    print("  Tokenizing corpus...")
    t_tok = time.perf_counter()
    tokenized_corpus = [tokenize(v["text"]) for v in verses]
    tok_elapsed = time.perf_counter() - t_tok
    print(f"  Tokenized {len(tokenized_corpus):,} verses in {tok_elapsed:.2f}s")
    
    # Sanity check: report token stats
    token_counts = [len(t) for t in tokenized_corpus]
    total_tokens = sum(token_counts)
    avg_tokens = total_tokens / len(token_counts) if token_counts else 0
    empty_count = sum(1 for t in token_counts if t == 0)
    print(f"  Total tokens: {total_tokens:,}")
    print(f"  Avg tokens/verse: {avg_tokens:.1f}")
    if empty_count > 0:
        print(f"  [WARNING] {empty_count} verses produced zero tokens after normalization")
    
    # ── Build BM25 index ──────────────────────────────────────────────────
    print("  Building BM25Okapi index...")
    t_bm25 = time.perf_counter()
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_elapsed = time.perf_counter() - t_bm25
    print(f"  BM25 index built in {bm25_elapsed:.2f}s")
    
    # ── Serialize ─────────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    
    bm25_path = os.path.join(output_dir, "bm25.pkl")
    lookup_path = os.path.join(output_dir, "verse_lookup.pkl")
    fingerprint_path = os.path.join(output_dir, "bm25_fingerprint.json")
    
    print(f"  Saving BM25 index to {bm25_path}...")
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    print(f"  Saving verse lookup to {lookup_path}...")
    with open(lookup_path, "wb") as f:
        pickle.dump(verse_lookup, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    # ── Fingerprint ───────────────────────────────────────────────────────
    # Hash the pickled BM25 file for runtime integrity verification
    bm25_hash = _file_sha256(bm25_path)
    lookup_hash = _file_sha256(lookup_path)
    source_fps = load_source_fingerprints(db_path)
    
    fingerprint = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "db_path": os.path.abspath(db_path),
        "verse_count": len(verses),
        "translations": sorted(translations) if translations else None,
        "total_tokens": total_tokens,
        "stop_words": sorted(STOP_WORDS),
        "bm25_sha256": bm25_hash,
        "verse_lookup_sha256": lookup_hash,
        "source_fingerprints": source_fps,
    }
    
    with open(fingerprint_path, "w", encoding="utf-8") as f:
        json.dump(fingerprint, f, indent=2)
    
    # ── Report ────────────────────────────────────────────────────────────
    bm25_size_mb = os.path.getsize(bm25_path) / (1024 * 1024)
    lookup_size_mb = os.path.getsize(lookup_path) / (1024 * 1024)
    total_elapsed = time.perf_counter() - t0
    
    print(f"\n  ── BM25 Index Build Complete ──")
    print(f"  Verses indexed:    {len(verses):,}")
    print(f"  BM25 index size:   {bm25_size_mb:.2f} MB")
    print(f"  Verse lookup size: {lookup_size_mb:.2f} MB")
    print(f"  Total size:        {bm25_size_mb + lookup_size_mb:.2f} MB")
    print(f"  Total build time:  {total_elapsed:.2f}s")
    print(f"  Fingerprint saved: {fingerprint_path}")
    
    # ── Quick smoke test ──────────────────────────────────────────────────
    _smoke_test(bm25, verse_lookup)

    # ── Per-version BM25 indexes ─────────────────────────────────────────
    _build_per_version_indexes(verses, output_dir)


def build_fuzzy_bm25_index(db_path: str, output_dir: str, translations: list[str] | None = None):
    """Build the fuzzy-lane BM25 index over the same translations as FAISS.

    Produces three files:
      - fuzzy_bm25.pkl:              The pickled BM25Okapi object
      - fuzzy_verse_lookup.pkl:      Index position → (version, book, chapter, verse_num, text)
      - fuzzy_bm25_fingerprint.json: Build metadata for runtime integrity verification
    """
    from rank_bm25 import BM25Okapi

    t0 = time.perf_counter()

    if translations is None:
        translations = FUZZY_TRANSLATIONS

    print(f"  Loading verses for {len(translations)} translations: {', '.join(translations)}...")
    verses = load_verses(db_path, translations)
    print(f"  Loaded {len(verses):,} verses")

    verse_lookup = [
        (v["version"], v["book"], v["chapter"], v["verse_num"], v["text"])
        for v in verses
    ]

    print("  Tokenizing corpus...")
    tokenized_corpus = [tokenize(v["text"]) for v in verses]
    total_tokens = sum(len(t) for t in tokenized_corpus)
    print(f"  Tokenized {len(tokenized_corpus):,} verses ({total_tokens:,} tokens)")

    print("  Building BM25Okapi index...")
    bm25 = BM25Okapi(tokenized_corpus)

    os.makedirs(output_dir, exist_ok=True)

    bm25_path = os.path.join(output_dir, "fuzzy_bm25.pkl")
    lookup_path = os.path.join(output_dir, "fuzzy_verse_lookup.pkl")
    fingerprint_path = os.path.join(output_dir, "fuzzy_bm25_fingerprint.json")

    print(f"  Saving fuzzy BM25 index to {bm25_path}...")
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"  Saving fuzzy verse lookup to {lookup_path}...")
    with open(lookup_path, "wb") as f:
        pickle.dump(verse_lookup, f, protocol=pickle.HIGHEST_PROTOCOL)

    bm25_hash = _file_sha256(bm25_path)
    lookup_hash = _file_sha256(lookup_path)
    # Match FAISS fingerprint format: source fingerprints for this lane's translations only
    source_fps = {
        k: v for k, v in load_source_fingerprints(db_path).items()
        if k in set(translations)
    }

    fingerprint = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "db_path": os.path.abspath(db_path),
        "verse_count": len(verses),
        "translations": sorted(translations),
        "total_tokens": total_tokens,
        "stop_words": sorted(STOP_WORDS),
        "bm25_sha256": bm25_hash,
        "verse_lookup_sha256": lookup_hash,
        "source_fingerprints": source_fps,
    }

    with open(fingerprint_path, "w", encoding="utf-8") as f:
        json.dump(fingerprint, f, indent=2)

    bm25_size_mb = os.path.getsize(bm25_path) / (1024 * 1024)
    lookup_size_mb = os.path.getsize(lookup_path) / (1024 * 1024)
    total_elapsed = time.perf_counter() - t0

    print(f"\n  ── Fuzzy BM25 Index Build Complete ──")
    print(f"  Verses indexed:    {len(verses):,}")
    print(f"  Translations:      {', '.join(sorted(translations))}")
    print(f"  Total size:        {bm25_size_mb + lookup_size_mb:.2f} MB")
    print(f"  Total build time:  {total_elapsed:.2f}s")
    print(f"  Fingerprint saved: {fingerprint_path}")

    _smoke_test(bm25, verse_lookup)


def _build_per_version_indexes(verses: list[dict], output_dir: str):
    """Build separate BM25 indexes for each FTS translation version.

    Produces per-version pickle pairs for fast browser-panel search:
      data/indexes/bm25_{VERSION}.pkl
      data/indexes/verse_lookup_{VERSION}.pkl

    Only FTS translations are built — the fuzzy lane searches its own
    combined fuzzy_bm25.pkl, not per-version indexes.
    """
    from rank_bm25 import BM25Okapi

    # Group verses by version
    by_version = defaultdict(list)
    for v in verses:
        by_version[v["version"]].append(v)

    versions = [t for t in FTS_TRANSLATIONS if t in by_version]
    print(f"\n  ── Per-Version Indexes ({len(versions)}/{len(by_version)} FTS versions) ──")

    for version in versions:
        vverses = by_version[version]
        t0 = time.perf_counter()

        v_lookup = [
            (v["version"], v["book"], v["chapter"], v["verse_num"], v["text"])
            for v in vverses
        ]
        v_tokenized = [tokenize(v["text"]) for v in vverses]
        v_bm25 = BM25Okapi(v_tokenized)

        bm25_path = os.path.join(output_dir, f"bm25_{version}.pkl")
        lookup_path = os.path.join(output_dir, f"verse_lookup_{version}.pkl")

        with open(bm25_path, "wb") as f:
            pickle.dump(v_bm25, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(lookup_path, "wb") as f:
            pickle.dump(v_lookup, f, protocol=pickle.HIGHEST_PROTOCOL)

        elapsed = time.perf_counter() - t0
        bm25_mb = os.path.getsize(bm25_path) / (1024 * 1024)
        lookup_mb = os.path.getsize(lookup_path) / (1024 * 1024)
        print(f"    {version}: {len(vverses):,} verses, "
              f"{bm25_mb + lookup_mb:.2f} MB, {elapsed:.2f}s")


def _smoke_test(bm25, verse_lookup: list):
    """Run a quick smoke test to verify the index works."""
    print("\n  ── Smoke Test ──")
    
    test_queries = [
        "for God so loved the world",
        "in the beginning God created",
        "the Lord is my shepherd",
        "thou shalt not kill",
        "blessed are the peacemakers",
    ]
    
    for query in test_queries:
        tokens = tokenize(query)
        scores = bm25.get_scores(tokens)
        
        # Get top 3 results
        import numpy as np
        top_indices = np.argsort(scores)[::-1][:3]
        
        print(f"\n  Query: \"{query}\"")
        print(f"  Tokens: {tokens}")
        for rank, idx in enumerate(top_indices, 1):
            version, book, chapter, verse_num, text = verse_lookup[idx]
            score = scores[idx]
            ref = f"{book} {chapter}:{verse_num}"
            print(f"    #{rank} [{version}] {ref} (score={score:.4f})")
            print(f"        {text[:100]}{'...' if len(text) > 100 else ''}")


def _file_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build BM25 inverted index from the Bible SQLite database."
    )
    parser.add_argument(
        "--db-path",
        default=os.path.join(os.path.dirname(__file__), "bible.db"),
        help="Path to the Bible SQLite database (default: data/bible/bible.db)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "indexes"),
        help="Output directory for index files (default: data/indexes/)",
    )
    parser.add_argument(
        "--translations",
        default=",".join(FTS_TRANSLATIONS),
        help=f"Comma-separated translation codes (default: {','.join(FTS_TRANSLATIONS)})",
    )
    parser.add_argument(
        "--fuzzy",
        action="store_true",
        help="Build the fuzzy-lane BM25 index (fuzzy_bm25.pkl) using --translations",
    )
    args = parser.parse_args()
    
    # Resolve relative paths
    db_path = os.path.abspath(args.db_path)
    output_dir = os.path.abspath(args.output_dir)
    
    translations = [t.strip().upper() for t in args.translations.split(",") if t.strip()]
    
    if args.fuzzy:
        print(f"  Database: {db_path}")
        print(f"  Output:   {output_dir}")
        print(f"  Translations: {', '.join(translations)}")
        print()
        build_fuzzy_bm25_index(db_path, output_dir, translations=translations)
        _update_translations_json(output_dir)
        return
    
    print(f"  Database: {db_path}")
    print(f"  Output:   {output_dir}")
    print(f"  Translations: {', '.join(translations)}")
    print()
    
    build_bm25_index(db_path, output_dir, translations=translations)
    _update_translations_json(output_dir)


def _update_translations_json(output_dir: str):
    """Update translations.json with all translations from the database."""
    import sqlite3
    import json

    db_path = os.path.join(os.path.dirname(__file__), "bible.db")
    translations_path = os.path.join(output_dir, "translations.json")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT DISTINCT version FROM verses ORDER BY version")
        translations = [row[0] for row in cursor.fetchall()]
        conn.close()

        with open(translations_path, "w") as f:
            json.dump({"translations": translations}, f, indent=2)
        print(f"  Updated translations.json with {len(translations)} translations")
    except Exception as e:
        print(f"  Warning: Could not update translations.json: {e}")


if __name__ == "__main__":
    main()