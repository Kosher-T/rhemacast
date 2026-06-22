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
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone


# ─── Normalization ────────────────────────────────────────────────────────────

# Custom stop-words — deliberately small set to preserve theological vocabulary.
# Archaic words (thou, hath, unto, thy, ye, hast, doth, etc.) are RETAINED
# because they are semantically meaningful for Bible search.
STOP_WORDS = frozenset({"the", "is", "a", "and", "to", "of", "in", "that"})

# Regex: hyphens (‐‑‒–—―), slashes, colons → space
_PUNCTUATION_TO_SPACE = re.compile(r"[\-\u2010\u2011\u2012\u2013\u2014\u2015/:]")

# Regex: strip all remaining non-alphanumeric except spaces
_STRIP_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def normalize_text(text: str) -> str:
    """Normalize a verse text for BM25 tokenization.
    
    This function MUST be kept symmetric with the live search normalization
    in core/search_engine.py. Any change here must be mirrored there.
    
    Returns:
        Normalized, lowercased string with stop-words removed.
    """
    # 1. Strip apostrophes (before lowering, so we catch ' and ')
    text = text.replace("'", "").replace("\u2019", "").replace("\u2018", "")
    
    # 2. Replace hyphens/dashes/slashes/colons with spaces
    text = _PUNCTUATION_TO_SPACE.sub(" ", text)
    
    # 3. Lowercase
    text = text.lower()
    
    # 4. Strip remaining non-alphanumeric characters (parentheses, brackets, etc.)
    text = _STRIP_NON_ALNUM.sub("", text)
    
    # 5. Collapse multiple spaces
    text = " ".join(text.split())
    
    return text


def tokenize(text: str) -> list[str]:
    """Tokenize normalized text into words, stripping stop-words.
    
    Returns:
        List of tokens with stop-words removed.
    """
    normalized = normalize_text(text)
    return [w for w in normalized.split() if w not in STOP_WORDS]


# ─── Database Loading ─────────────────────────────────────────────────────────

def load_verses(db_path: str) -> list[dict]:
    """Load all verses from the Bible database.
    
    Returns:
        List of dicts: {"version", "book", "chapter", "verse_num", "text"}
        ordered by version, book, chapter, verse_num.
    """
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute(
        "SELECT version, book, chapter, verse_num, text FROM verses "
        "ORDER BY version, book, chapter, verse_num"
    ).fetchall()
    
    verses = [
        {
            "version": r["version"],
            "book": r["book"],
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

def build_bm25_index(db_path: str, output_dir: str):
    """Build the BM25 inverted index and save to disk.
    
    Produces three files:
      - bm25.pkl:              The pickled BM25Okapi object
      - verse_lookup.pkl:      Index position → (version, book, chapter, verse_num, text)
      - bm25_fingerprint.json: Build metadata for runtime integrity verification
    """
    from rank_bm25 import BM25Okapi
    
    t0 = time.perf_counter()
    
    # ── Load verses ───────────────────────────────────────────────────────
    print("  Loading verses from database...")
    verses = load_verses(db_path)
    print(f"  Loaded {len(verses):,} verses")
    
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
    args = parser.parse_args()
    
    # Resolve relative paths
    db_path = os.path.abspath(args.db_path)
    output_dir = os.path.abspath(args.output_dir)
    
    print(f"  Database: {db_path}")
    print(f"  Output:   {output_dir}")
    print()
    
    build_bm25_index(db_path, output_dir)


if __name__ == "__main__":
    main()