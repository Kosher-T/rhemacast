#!/usr/bin/env python3
"""
build_faiss.py — Build the FAISS vector index from the Bible SQLite database.

This script reads all verses from bible.db, encodes them into 384-dimensional
vectors using the all-MiniLM-L6-v2 sentence transformer model, builds a FAISS
IndexFlatIP (inner-product / cosine similarity after L2 normalization) index,
and saves everything to disk.

The verse_lookup.pkl created by build_bm25.py is REUSED here — both indexes
share the same ordering, so position i in the FAISS index corresponds to
position i in verse_lookup.pkl.

Dependencies:
  - sentence-transformers  (pip install "sentence-transformers[onnx]")
  - onnxruntime            (pip install onnxruntime)
  - faiss-cpu              (pip install faiss-cpu)
  - numpy

Outputs:
  data/indexes/faiss.index              — FAISS IndexFlatIP (384-dim, cosine sim)
  data/indexes/faiss_fingerprint.json   — Build metadata + source DB fingerprints

Usage:
  python build_faiss.py [--db-path PATH] [--output-dir PATH] [--batch-size N]
  python build_faiss.py
  python build_faiss.py --db-path data/bible/bible.db --output-dir data/indexes --batch-size 256
"""

import argparse
import hashlib
import json
import os
import pickle
import sqlite3
import sys
import time
from datetime import datetime, timezone

import numpy as np


# ─── Database Loading ─────────────────────────────────────────────────────────

def load_verses(db_path: str) -> list[dict]:
    """Load all verses from the Bible database.
    
    Returns:
        List of dicts: {"version", "book", "chapter", "verse_num", "text"}
        ordered by version, book, chapter, verse_num.
    
    IMPORTANT: The ordering MUST match build_bm25.py exactly so that
    index position i maps to the same verse in both BM25 and FAISS.
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


# ─── Consistency Check ────────────────────────────────────────────────────────

def verify_verse_lookup_consistency(verses: list[dict], output_dir: str) -> bool:
    """Verify that the verse ordering matches the existing verse_lookup.pkl.
    
    Both BM25 and FAISS must share the same index ordering. This check
    ensures build_faiss.py loads verses in the same order as build_bm25.py.
    """
    lookup_path = os.path.join(output_dir, "verse_lookup.pkl")
    if not os.path.exists(lookup_path):
        print("  [WARNING] verse_lookup.pkl not found — cannot verify ordering consistency.")
        print("            Run build_bm25.py first to generate it.")
        return True  # Allow build to proceed — lookup will be checked at runtime
    
    with open(lookup_path, "rb") as f:
        verse_lookup = pickle.load(f)
    
    if len(verses) != len(verse_lookup):
        print(f"  [ERROR] Verse count mismatch: DB has {len(verses)}, "
              f"verse_lookup.pkl has {len(verse_lookup)}")
        return False
    
    # Spot-check first, last, and middle entries
    check_positions = [0, len(verses) // 4, len(verses) // 2,
                       3 * len(verses) // 4, len(verses) - 1]
    
    for i in check_positions:
        v = verses[i]
        lookup = verse_lookup[i]  # (version, book, chapter, verse_num, text)
        if (v["version"] != lookup[0] or v["book"] != lookup[1] or
            v["chapter"] != lookup[2] or v["verse_num"] != lookup[3]):
            print(f"  [ERROR] Ordering mismatch at position {i}:")
            print(f"    DB:     ({v['version']}, {v['book']}, {v['chapter']}, {v['verse_num']})")
            print(f"    Lookup: ({lookup[0]}, {lookup[1]}, {lookup[2]}, {lookup[3]})")
            return False
    
    print("  Verse ordering is consistent with verse_lookup.pkl ✓")
    return True


# ─── Index Building ───────────────────────────────────────────────────────────

def build_faiss_index(db_path: str, output_dir: str, batch_size: int = 256):
    """Build the FAISS vector index and save to disk.
    
    Produces two files:
      - faiss.index:              The FAISS IndexFlatIP index
      - faiss_fingerprint.json:   Build metadata for runtime integrity verification
    """
    import faiss
    
    # Import sentence-transformers — this is the dependency most likely to be missing
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[ERROR] sentence-transformers is not installed.")
        print("        Install it with: pip install \"sentence-transformers[onnx]\" onnxruntime")
        sys.exit(1)
    
    t0 = time.perf_counter()
    
    # ── Load verses ───────────────────────────────────────────────────────
    print("  Loading verses from database...")
    verses = load_verses(db_path)
    print(f"  Loaded {len(verses):,} verses")
    
    # ── Consistency check ─────────────────────────────────────────────────
    if not verify_verse_lookup_consistency(verses, output_dir):
        print("[FATAL] Verse ordering does not match verse_lookup.pkl.")
        print("        Rebuild both indexes: run build_bm25.py first, then build_faiss.py.")
        sys.exit(1)
    
    # ── Load embedding model ──────────────────────────────────────────────
    print("  Loading all-MiniLM-L6-v2 sentence transformer (ONNX backend)...")
    t_model = time.perf_counter()
    
    try:
        model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            backend="onnx",
            model_kwargs={"provider": "CPUExecutionProvider"},
        )
    except Exception:
        # Fallback: try without ONNX backend (uses PyTorch if available)
        print("  [WARNING] ONNX backend failed, falling back to default backend...")
        model = SentenceTransformer("all-MiniLM-L6-v2")
    
    model_elapsed = time.perf_counter() - t_model
    print(f"  Model loaded in {model_elapsed:.2f}s")
    
    # Verify embedding dimension
    test_emb = model.encode(["test"])
    emb_dim = test_emb.shape[1]
    print(f"  Embedding dimension: {emb_dim}")
    assert emb_dim == 384, f"Expected 384-dim embeddings, got {emb_dim}"
    
    # ── Encode all verses ─────────────────────────────────────────────────
    # For FAISS semantic search, we encode the RAW text (not normalized).
    # The embedding model handles its own tokenization internally.
    # This is deliberately different from BM25 which uses custom normalization.
    all_texts = [v["text"] for v in verses]
    
    print(f"  Encoding {len(all_texts):,} verses (batch_size={batch_size})...")
    print("  This may take 20–40 minutes on CPU. Please wait.")
    t_encode = time.perf_counter()
    
    embeddings = model.encode(
        all_texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=False,  # We'll normalize manually for clarity
    )
    
    encode_elapsed = time.perf_counter() - t_encode
    print(f"  Encoded {len(embeddings):,} verses in {encode_elapsed:.1f}s "
          f"({len(embeddings) / encode_elapsed:.0f} verses/sec)")
    
    # ── Normalize & build FAISS index ─────────────────────────────────────
    print("  Normalizing embeddings (L2 → unit vectors for cosine similarity)...")
    embeddings = embeddings.astype(np.float32)
    faiss.normalize_L2(embeddings)
    
    print("  Building FAISS IndexFlatIP (inner product ≡ cosine sim after L2 norm)...")
    t_faiss = time.perf_counter()
    index = faiss.IndexFlatIP(emb_dim)
    index.add(embeddings)
    faiss_elapsed = time.perf_counter() - t_faiss
    print(f"  FAISS index built in {faiss_elapsed:.2f}s — {index.ntotal:,} vectors")
    
    # ── Serialize ─────────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    
    faiss_path = os.path.join(output_dir, "faiss.index")
    fingerprint_path = os.path.join(output_dir, "faiss_fingerprint.json")
    
    print(f"  Saving FAISS index to {faiss_path}...")
    faiss.write_index(index, faiss_path)
    
    # ── Fingerprint ───────────────────────────────────────────────────────
    faiss_hash = _file_sha256(faiss_path)
    source_fps = load_source_fingerprints(db_path)
    
    fingerprint = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "db_path": os.path.abspath(db_path),
        "verse_count": len(verses),
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dim": emb_dim,
        "index_type": "IndexFlatIP",
        "faiss_sha256": faiss_hash,
        "encode_time_seconds": round(encode_elapsed, 2),
        "source_fingerprints": source_fps,
    }
    
    with open(fingerprint_path, "w", encoding="utf-8") as f:
        json.dump(fingerprint, f, indent=2)
    
    # ── Report ────────────────────────────────────────────────────────────
    faiss_size_mb = os.path.getsize(faiss_path) / (1024 * 1024)
    total_elapsed = time.perf_counter() - t0
    
    print(f"\n  ── FAISS Index Build Complete ──")
    print(f"  Verses indexed:    {len(verses):,}")
    print(f"  Embedding dim:     {emb_dim}")
    print(f"  Index type:        IndexFlatIP (cosine similarity)")
    print(f"  FAISS index size:  {faiss_size_mb:.2f} MB")
    print(f"  Encode time:       {encode_elapsed:.1f}s")
    print(f"  Total build time:  {total_elapsed:.1f}s")
    print(f"  Fingerprint saved: {fingerprint_path}")
    
    # ── Smoke test ────────────────────────────────────────────────────────
    _smoke_test(model, index, verses)


def _smoke_test(model, index, verses: list[dict]):
    """Run a quick smoke test to verify the FAISS index works."""
    import faiss as _faiss  # already imported in caller scope, but be explicit
    
    print("\n  ── Smoke Test (Semantic Search) ──")
    
    test_queries = [
        "God loved the world so much he gave his son",
        "the earth was formless and empty",
        "the good shepherd lays down his life for the sheep",
        "do not murder",
        "happy are those who work for peace",
    ]
    
    for query in test_queries:
        # Encode and normalize query
        q_emb = model.encode([query]).astype(np.float32)
        _faiss.normalize_L2(q_emb)
        
        # Search
        scores, indices = index.search(q_emb, 3)
        
        print(f"\n  Query: \"{query}\"")
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
            v = verses[idx]
            ref = f"{v['book']} {v['chapter']}:{v['verse_num']}"
            print(f"    #{rank} [{v['version']}] {ref} (sim={score:.4f})")
            print(f"        {v['text'][:100]}{'...' if len(v['text']) > 100 else ''}")


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
        description="Build FAISS vector index from the Bible SQLite database."
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
        "--batch-size",
        type=int,
        default=256,
        help="Encoding batch size (default: 256)",
    )
    args = parser.parse_args()
    
    # Resolve relative paths
    db_path = os.path.abspath(args.db_path)
    output_dir = os.path.abspath(args.output_dir)
    
    print(f"  Database: {db_path}")
    print(f"  Output:   {output_dir}")
    print()
    
    build_faiss_index(db_path, output_dir, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
