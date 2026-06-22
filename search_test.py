#!/usr/bin/env python3
"""
search_test.py — Phase 1.4 Index Validation Script

Validates BM25 and FAISS indexes by running known verse fragments and
paraphrased queries, then verifying the correct verses appear in the top-5
results. Also demonstrates RRF fusion ranking for manual inspection.

Usage:
  python search_test.py
  python search_test.py --top-k 10

Expects:
  data/indexes/bm25.pkl
  data/indexes/verse_lookup.pkl
  data/indexes/faiss.index
  data/bible/bible.db
"""

import os
import pickle
import sys
import time

import numpy as np

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(SCRIPT_DIR, "data", "indexes")
DB_PATH = os.path.join(SCRIPT_DIR, "data", "bible", "bible.db")

BM25_PATH = os.path.join(INDEX_DIR, "bm25.pkl")
LOOKUP_PATH = os.path.join(INDEX_DIR, "verse_lookup.pkl")
FAISS_PATH = os.path.join(INDEX_DIR, "faiss.index")

# Import the same normalization pipeline used by the BM25 index builder
sys.path.insert(0, os.path.join(SCRIPT_DIR, "data", "bible"))
from build_bm25 import tokenize  # noqa: E402


# ─── BM25 Known Verse Fragments ──────────────────────────────────────────────
# Each entry: (query fragment, expected_version, expected_book, expected_chapter, expected_verse)
BM25_TEST_CASES = [
    ("For God so loved the world",             "KJV", "John",           3,  16),
    ("In the beginning God created",           "KJV", "Genesis",        1,  1),
    ("The LORD is my shepherd",                "KJV", "Psalms",         23, 1),
    ("Thou shalt not kill",                    "KJV", "Exodus",         20, 13),
    ("Blessed are the peacemakers",            "KJV", "Matthew",        5,  9),
    ("I can do all things through Christ",     "KJV", "Philippians",    4,  13),
    ("Trust in the LORD with all thine heart", "KJV", "Proverbs",       3,  5),
    ("all things work together for good",      "KJV", "Romans",         8,  28),
    ("the thoughts that I think toward you",   "KJV", "Jeremiah",       29, 11),
    ("they that wait upon the LORD shall renew their strength",   "KJV", "Isaiah",         40, 31),
]


# ─── FAISS Paraphrased Verse Queries ─────────────────────────────────────────
# Paraphrased / modern English rewording → expected semantic match
FAISS_TEST_CASES = [
    ("God loved the world so much he gave his only son",
     "John", 3, 16),
    ("the earth was empty and without form in the beginning",
     "Genesis", 1, 2),
    ("the good shepherd cares for his flock",
     "Psalms", 23, 1),
    ("you must not commit murder",
     "Exodus", 20, 13),
    ("those who make peace are blessed",
     "Matthew", 5, 9),
    ("I have strength for everything through the one who empowers me",
     "Philippians", 4, 13),
    ("rely on God completely and don't depend on your own wisdom",
     "Proverbs", 3, 5),
    ("everything works out for the benefit of those who love God",
     "Romans", 8, 28),
    ("God has plans to give you hope and a future, not harm",
     "Jeremiah", 29, 11),
    ("those who hope in the Lord will find renewed strength and soar",
     "Isaiah", 40, 31),
]


# ─── RRF Fusion Test Phrases ─────────────────────────────────────────────────
# Run through both BM25 and FAISS, then fuse with RRF for manual inspection
RRF_TEST_PHRASES = [
    "For God so loved the world",
    "the Lord is my shepherd I shall not want",
    "blessed are those who are persecuted",
    "love is patient love is kind",
    "go and make disciples of all nations",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def load_bm25():
    """Load the BM25 index and verse lookup from disk."""
    print("  Loading BM25 index...")
    t0 = time.perf_counter()
    with open(BM25_PATH, "rb") as f:
        bm25 = pickle.load(f)
    with open(LOOKUP_PATH, "rb") as f:
        verse_lookup = pickle.load(f)
    elapsed = time.perf_counter() - t0
    print(f"  BM25 index loaded in {elapsed:.2f}s ({len(verse_lookup):,} verses)")
    return bm25, verse_lookup


def load_faiss():
    """Load the FAISS index and sentence transformer model."""
    import faiss
    from sentence_transformers import SentenceTransformer

    print("  Loading FAISS index...")
    t0 = time.perf_counter()
    index = faiss.read_index(FAISS_PATH)
    elapsed_idx = time.perf_counter() - t0
    print(f"  FAISS index loaded in {elapsed_idx:.2f}s ({index.ntotal:,} vectors)")

    print("  Loading all-MiniLM-L6-v2 sentence transformer...")
    t1 = time.perf_counter()
    try:
        model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            backend="onnx",
            model_kwargs={"provider": "CPUExecutionProvider"},
        )
    except Exception:
        print("  [WARNING] ONNX backend failed, falling back to default...")
        model = SentenceTransformer("all-MiniLM-L6-v2")
    elapsed_model = time.perf_counter() - t1
    print(f"  Model loaded in {elapsed_model:.2f}s")

    return index, model


def bm25_search(bm25, verse_lookup, query: str, top_k: int = 5):
    """Search BM25 index. Returns list of (rank, version, book, chapter, verse, score, text)."""
    tokens = tokenize(query)
    scores = bm25.get_scores(tokens)
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for rank, idx in enumerate(top_indices, 1):
        version, book, chapter, verse_num, text = verse_lookup[idx]
        results.append((rank, version, book, chapter, verse_num, scores[idx], text))
    return results


def faiss_search(index, model, verse_lookup, query: str, top_k: int = 5):
    """Search FAISS index. Returns list of (rank, version, book, chapter, verse, score, text)."""
    import faiss as _faiss

    q_emb = model.encode([query]).astype(np.float32)
    _faiss.normalize_L2(q_emb)
    scores, indices = index.search(q_emb, top_k)

    results = []
    for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
        version, book, chapter, verse_num, text = verse_lookup[idx]
        results.append((rank, version, book, chapter, verse_num, float(score), text))
    return results


def rrf_fuse(bm25_results, faiss_results, k: int = 60):
    """Reciprocal Rank Fusion of BM25 and FAISS results.

    Returns sorted list of (rrf_score, version, book, chapter, verse, text,
                            bm25_rank, faiss_rank).
    """
    # Build a dict keyed by (version, book, chapter, verse)
    candidates = {}

    for rank, version, book, chapter, verse_num, score, text in bm25_results:
        key = (version, book, chapter, verse_num)
        candidates[key] = {
            "version": version, "book": book, "chapter": chapter,
            "verse_num": verse_num, "text": text,
            "bm25_rank": rank, "faiss_rank": None,
        }

    for rank, version, book, chapter, verse_num, score, text in faiss_results:
        key = (version, book, chapter, verse_num)
        if key in candidates:
            candidates[key]["faiss_rank"] = rank
        else:
            candidates[key] = {
                "version": version, "book": book, "chapter": chapter,
                "verse_num": verse_num, "text": text,
                "bm25_rank": None, "faiss_rank": rank,
            }

    # Compute RRF scores
    fused = []
    for key, c in candidates.items():
        rrf = 0.0
        if c["bm25_rank"] is not None:
            rrf += 1.0 / (k + c["bm25_rank"])
        if c["faiss_rank"] is not None:
            rrf += 1.0 / (k + c["faiss_rank"])
        fused.append((
            rrf, c["version"], c["book"], c["chapter"], c["verse_num"],
            c["text"], c["bm25_rank"], c["faiss_rank"],
        ))

    fused.sort(key=lambda x: x[0], reverse=True)
    return fused


def check_in_results(results, book, chapter, verse_num, version=None):
    """Check if a specific verse appears in the result list (any version if not specified)."""
    for r in results:
        r_version, r_book, r_chapter, r_verse = r[1], r[2], r[3], r[4]
        if r_book == book and r_chapter == chapter and r_verse == verse_num:
            if version is None or r_version == version:
                return r[0]  # return the rank
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Test Runners
# ═══════════════════════════════════════════════════════════════════════════════

def run_bm25_tests(bm25, verse_lookup, top_k=5):
    """Run 10 known verse fragments through BM25 → confirm correct verse in Top 5."""
    print("\n" + "=" * 80)
    print("  BM25 LEXICAL SEARCH VALIDATION")
    print("  10 known verse fragments → expect correct verse in Top 5")
    print("=" * 80)

    passed = 0
    failed = 0

    for query, exp_version, exp_book, exp_chapter, exp_verse in BM25_TEST_CASES:
        results = bm25_search(bm25, verse_lookup, query, top_k)
        # Check if expected verse is in results (any version match)
        rank = check_in_results(results, exp_book, exp_chapter, exp_verse, exp_version)

        # Also check across all versions (book name may differ)
        # e.g. "Psalm" vs "Psalms"
        if rank is None:
            # Try without version constraint
            rank = check_in_results(results, exp_book, exp_chapter, exp_verse)

        status = f"✓ PASS (rank #{rank})" if rank else "✗ FAIL"
        if rank:
            passed += 1
        else:
            failed += 1

        print(f"\n  Query: \"{query}\"")
        print(f"  Expected: [{exp_version}] {exp_book} {exp_chapter}:{exp_verse}")
        print(f"  Result: {status}")

        # Print top results for context
        for r in results[:3]:
            rk, ver, bk, ch, vs, sc, txt = r
            print(f"    #{rk} [{ver}] {bk} {ch}:{vs} (score={sc:.4f})")
            print(f"        {txt[:90]}{'...' if len(txt) > 90 else ''}")

    print(f"\n  ── BM25 Summary: {passed}/{passed + failed} passed ──")
    return passed, failed


def run_faiss_tests(index, model, verse_lookup, top_k=5):
    """Run 10 paraphrased verses through FAISS → confirm semantic match in Top 5."""
    print("\n" + "=" * 80)
    print("  FAISS SEMANTIC SEARCH VALIDATION")
    print("  10 paraphrased verses → expect semantic match in Top 5")
    print("=" * 80)

    passed = 0
    failed = 0

    for query, exp_book, exp_chapter, exp_verse in FAISS_TEST_CASES:
        results = faiss_search(index, model, verse_lookup, query, top_k)
        # Semantic search should match any version of the expected verse
        rank = check_in_results(results, exp_book, exp_chapter, exp_verse)

        status = f"✓ PASS (rank #{rank})" if rank else "✗ FAIL"
        if rank:
            passed += 1
        else:
            failed += 1

        print(f"\n  Query: \"{query}\"")
        print(f"  Expected: {exp_book} {exp_chapter}:{exp_verse} (any version)")
        print(f"  Result: {status}")

        for r in results[:3]:
            rk, ver, bk, ch, vs, sc, txt = r
            print(f"    #{rk} [{ver}] {bk} {ch}:{vs} (sim={sc:.4f})")
            print(f"        {txt[:90]}{'...' if len(txt) > 90 else ''}")

    print(f"\n  ── FAISS Summary: {passed}/{passed + failed} passed ──")
    return passed, failed


def run_rrf_tests(bm25, verse_lookup, index, model, top_k=5):
    """Run 5 phrases through both indexes → display RRF fusion for manual verification."""
    print("\n" + "=" * 80)
    print("  RRF FUSION RANKING — MANUAL VERIFICATION")
    print("  5 phrases through BM25 + FAISS → fused with RRF (k=60)")
    print("=" * 80)

    for query in RRF_TEST_PHRASES:
        bm25_results = bm25_search(bm25, verse_lookup, query, top_k)
        faiss_results = faiss_search(index, model, verse_lookup, query, top_k)
        fused = rrf_fuse(bm25_results, faiss_results)

        print(f"\n  Query: \"{query}\"")
        print(f"  {'─' * 74}")

        # Show BM25 top 3
        print(f"  BM25 Top 3:")
        for r in bm25_results[:3]:
            rk, ver, bk, ch, vs, sc, txt = r
            print(f"    #{rk} [{ver}] {bk} {ch}:{vs} (score={sc:.4f})")

        # Show FAISS top 3
        print(f"  FAISS Top 3:")
        for r in faiss_results[:3]:
            rk, ver, bk, ch, vs, sc, txt = r
            print(f"    #{rk} [{ver}] {bk} {ch}:{vs} (sim={sc:.4f})")

        # Show RRF fused top 5
        print(f"  RRF Fused Top 5:")
        for i, (rrf, ver, bk, ch, vs, txt, bm25_rk, faiss_rk) in enumerate(fused[:5], 1):
            bm25_str = f"BM25=#{bm25_rk}" if bm25_rk else "BM25=—"
            faiss_str = f"FAISS=#{faiss_rk}" if faiss_rk else "FAISS=—"
            print(f"    #{i} [{ver}] {bk} {ch}:{vs} (RRF={rrf:.6f}, {bm25_str}, {faiss_str})")
            print(f"        {txt[:90]}{'...' if len(txt) > 90 else ''}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Phase 1.4 Index Validation Script")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to check (default: 5)")
    parser.add_argument("--bm25-only", action="store_true", help="Run only BM25 tests (no FAISS/model loading)")
    args = parser.parse_args()

    # Check prerequisites
    for path, name in [
        (BM25_PATH, "BM25 index"), (LOOKUP_PATH, "Verse lookup"),
        (FAISS_PATH, "FAISS index"),
    ]:
        if not os.path.exists(path):
            print(f"[ERROR] {name} not found: {path}")
            print("        Run the Phase 1 build scripts first.")
            sys.exit(1)

    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║              RhemaCast Phase 1.4 — Index Validation                        ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")

    # Load indexes
    bm25, verse_lookup = load_bm25()

    # BM25 tests
    bm25_passed, bm25_failed = run_bm25_tests(bm25, verse_lookup, args.top_k)

    if not args.bm25_only:
        # Load FAISS (heavier — loads the sentence transformer model)
        index, model = load_faiss()

        # FAISS tests
        faiss_passed, faiss_failed = run_faiss_tests(index, model, verse_lookup, args.top_k)

        # RRF fusion tests
        run_rrf_tests(bm25, verse_lookup, index, model, args.top_k)
    else:
        faiss_passed, faiss_failed = 0, 0

    # Final summary
    total_passed = bm25_passed + faiss_passed
    total_failed = bm25_failed + faiss_failed

    print("\n" + "=" * 80)
    print(f"  FINAL SUMMARY")
    print(f"  BM25:  {bm25_passed}/10 passed")
    if not args.bm25_only:
        print(f"  FAISS: {faiss_passed}/10 passed")
        print(f"  RRF:   5 phrases shown for manual verification")
    print(f"  Total: {total_passed}/{total_passed + total_failed} automated checks passed")
    print("=" * 80)

    sys.exit(1 if total_failed > 0 else 0)


if __name__ == "__main__":
    main()
