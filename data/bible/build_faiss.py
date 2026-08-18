#!/usr/bin/env python3
"""
build_faiss.py — Build FAISS vector index from the Bible SQLite database.

Encodes verses into 384-dim vectors using all-MiniLM-L6-v2, builds an
IndexFlatIP (cosine similarity) FAISS index, and saves to disk.

By default, 5 modern-language translations are indexed for semantic search:
  NLT, MSG, BSB, AMP, NIV
  (DB codes: NLT, BIBLE_ENGLISH_MSG, BSB, AMP, NIV)
  NOTE: ERV (ENGLISHERVBIBLE) replaced by topical/stories index.

The FAISS index has its own verse_lookup (faiss_verse_lookup.pkl) because
it contains a subset of the full database. BM25 keeps the full lookup.

Dependencies:
  - sentence-transformers  (pip install "sentence-transformers[onnx]")
  - onnxruntime-gpu        (pip install onnxruntime-gpu)  — for CUDA
  - faiss-cpu or faiss-gpu (pip install faiss-gpu)
  - numpy

Outputs:
  data/indexes/faiss.index              — FAISS IndexFlatIP (384-dim, cosine sim)
  data/indexes/faiss_fingerprint.json   — Build metadata + source fingerprints
  data/indexes/faiss_verse_lookup.pkl   — Verse lookup for FAISS indices only

Usage:
  python build_faiss.py
  python build_faiss.py --translations NLT,KJV,BSB,ESV,MSG,AMP
  python build_faiss.py --batch-size 512
  python build_faiss.py --cpu   # Force CPU even if CUDA available
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


# ─── Default translations ────────────────────────────────────────────────────

DEFAULT_TRANSLATIONS = ["NLT", "BIBLE_ENGLISH_MSG", "BSB", "AMP", "NIV"]


# ─── Database Loading ─────────────────────────────────────────────────────────

def load_verses(db_path: str, translations: list[str]) -> list[dict]:
    """Load verses for specified translations from the Bible database.

    Returns list of dicts ordered by version, book, chapter, verse_num.
    """
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    placeholders = ",".join("?" for _ in translations)
    rows = conn.execute(
        f"SELECT version, book, chapter, verse_num, text FROM verses "
        f"WHERE version IN ({placeholders}) "
        f"ORDER BY version, book, chapter, verse_num",
        translations,
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


def load_source_fingerprints(db_path: str, translations: list[str]) -> dict:
    """Load source fingerprints for the specified translations."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    fingerprints = {}
    placeholders = ",".join("?" for _ in translations)
    try:
        for row in conn.execute(
            f"SELECT version, sha256, verse_count FROM source_fingerprints "
            f"WHERE version IN ({placeholders}) ORDER BY version",
            translations,
        ):
            fingerprints[row["version"]] = {
                "sha256": row["sha256"],
                "verse_count": row["verse_count"],
            }
    except sqlite3.OperationalError:
        print("[WARNING] No source_fingerprints table found in database.")

    conn.close()
    return fingerprints


# ─── Index Building ───────────────────────────────────────────────────────────

def build_faiss_index(db_path: str, output_dir: str, translations: list[str],
                      batch_size: int = 256, force_cpu: bool = False):
    """Build the FAISS vector index and save to disk.

    Produces three files:
      - faiss.index:              The FAISS IndexFlatIP index
      - faiss_fingerprint.json:   Build metadata for runtime integrity
      - faiss_verse_lookup.pkl:   Index → verse mapping for FAISS only
    """
    import faiss

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[ERROR] sentence-transformers is not installed.")
        print("        Install with: pip install \"sentence-transformers[onnx]\"")
        sys.exit(1)

    t0 = time.perf_counter()

    # ── Load verses ───────────────────────────────────────────────────────
    print(f"  Loading verses for {len(translations)} translations...")
    verses = load_verses(db_path, translations)
    print(f"  Loaded {len(verses):,} verses")

    if not verses:
        print("[ERROR] No verses loaded. Check translation codes.")
        sys.exit(1)

    # Report per-translation counts
    from collections import Counter
    counts = Counter(v["version"] for v in verses)
    for t in sorted(counts):
        print(f"    {t}: {counts[t]:,}")

    # ── Detect CUDA ───────────────────────────────────────────────────────
    use_cuda = False
    provider = "CPUExecutionProvider"
    if not force_cpu:
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if "CUDAExecutionProvider" in providers:
                use_cuda = True
                provider = "CUDAExecutionProvider"
                print("  CUDA detected — using GPU for encoding")
            else:
                print("  CUDA not available — using CPU (use --cpu to suppress this)")
        except ImportError:
            print("  [WARNING] onnxruntime not found — using CPU")

    # ── Load embedding model ──────────────────────────────────────────────
    model_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "all-MiniLM-L6-v2")
    model_path = os.path.abspath(model_path)
    print(f"  Loading embedding model from {model_path} (provider={provider})...")
    t_model = time.perf_counter()

    try:
        model = SentenceTransformer(
            model_path,
            backend="onnx",
            model_kwargs={"provider": provider, "file_name": "onnx/model.onnx"},
        )
    except Exception:
        print("  [WARNING] ONNX backend failed, trying default backend...")
        model = SentenceTransformer(model_path)

    model_elapsed = time.perf_counter() - t_model
    print(f"  Model loaded in {model_elapsed:.2f}s")

    # Verify embedding dimension
    test_emb = model.encode(["test"])
    emb_dim = test_emb.shape[1]
    print(f"  Embedding dimension: {emb_dim}")
    assert emb_dim == 384, f"Expected 384-dim embeddings, got {emb_dim}"

    # ── Encode all verses ─────────────────────────────────────────────────
    all_texts = [v["text"] for v in verses]

    est_cpu_min = len(all_texts) / 250 / 60  # rough CPU estimate
    if use_cuda:
        print(f"  Encoding {len(all_texts):,} verses on GPU (batch_size={batch_size})...")
    else:
        print(f"  Encoding {len(all_texts):,} verses on CPU (batch_size={batch_size})...")
        print(f"  Estimated time: ~{est_cpu_min:.0f} minutes on CPU")

    t_encode = time.perf_counter()

    embeddings = model.encode(
        all_texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=False,
    )

    encode_elapsed = time.perf_counter() - t_encode
    rate = len(embeddings) / encode_elapsed
    print(f"  Encoded {len(embeddings):,} verses in {encode_elapsed:.1f}s "
          f"({rate:.0f} verses/sec)")

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

    # ── Create FAISS-specific verse lookup ────────────────────────────────
    # FAISS indices map to this list, NOT to BM25's verse_lookup.pkl
    faiss_lookup = [
        (v["version"], v["book"], v["chapter"], v["verse_num"], v["text"])
        for v in verses
    ]

    # ── Serialize ─────────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)

    faiss_path = os.path.join(output_dir, "faiss.index")
    lookup_path = os.path.join(output_dir, "faiss_verse_lookup.pkl")
    fingerprint_path = os.path.join(output_dir, "faiss_fingerprint.json")

    print(f"  Saving FAISS index to {faiss_path}...")
    faiss.write_index(index, faiss_path)

    print(f"  Saving FAISS verse lookup to {lookup_path}...")
    with open(lookup_path, "wb") as f:
        pickle.dump(faiss_lookup, f, protocol=pickle.HIGHEST_PROTOCOL)

    # ── Fingerprint ───────────────────────────────────────────────────────
    faiss_hash = _file_sha256(faiss_path)
    source_fps = load_source_fingerprints(db_path, translations)

    fingerprint = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "db_path": os.path.abspath(db_path),
        "verse_count": len(verses),
        "translations": sorted(translations),
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dim": emb_dim,
        "index_type": "IndexFlatIP",
        "provider": provider,
        "faiss_sha256": faiss_hash,
        "encode_time_seconds": round(encode_elapsed, 2),
        "source_fingerprints": source_fps,
    }

    with open(fingerprint_path, "w", encoding="utf-8") as f:
        json.dump(fingerprint, f, indent=2)

    # ── Report ────────────────────────────────────────────────────────────
    faiss_size_mb = os.path.getsize(faiss_path) / (1024 * 1024)
    lookup_size_mb = os.path.getsize(lookup_path) / (1024 * 1024)
    total_elapsed = time.perf_counter() - t0

    print(f"\n  ── FAISS Index Build Complete ──")
    print(f"  Translations:      {', '.join(sorted(translations))}")
    print(f"  Verses indexed:    {len(verses):,}")
    print(f"  Embedding dim:     {emb_dim}")
    print(f"  Provider:          {provider}")
    print(f"  Index type:        IndexFlatIP (cosine similarity)")
    print(f"  FAISS index size:  {faiss_size_mb:.2f} MB")
    print(f"  Verse lookup size: {lookup_size_mb:.2f} MB")
    print(f"  Encode time:       {encode_elapsed:.1f}s")
    print(f"  Total build time:  {total_elapsed:.1f}s")
    print(f"  Fingerprint:       {fingerprint_path}")

    # ── Smoke test ────────────────────────────────────────────────────────
    _smoke_test(model, index, faiss_lookup)


def _smoke_test(model, index, verse_lookup: list[tuple]):
    """Run a quick smoke test to verify the FAISS index works."""
    import faiss as _faiss

    print("\n  ── Smoke Test (Semantic Search) ──")

    test_queries = [
        "God loved the world so much he gave his son",
        "the earth was formless and empty",
        "the good shepherd lays down his life for the sheep",
        "do not murder",
        "happy are those who work for peace",
    ]

    for query in test_queries:
        q_emb = model.encode([query]).astype(np.float32)
        _faiss.normalize_L2(q_emb)

        scores, indices = index.search(q_emb, 3)

        print(f"\n  Query: \"{query}\"")
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
            if idx < 0 or idx >= len(verse_lookup):
                continue
            version, book, chapter, verse_num, text = verse_lookup[idx]
            ref = f"{book} {chapter}:{verse_num}"
            print(f"    #{rank} [{version}] {ref} (sim={score:.4f})")
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
        "--translations",
        default=",".join(DEFAULT_TRANSLATIONS),
        help=f"Comma-separated translation codes to index (default: {','.join(DEFAULT_TRANSLATIONS)})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="Encoding batch size (default: 256)",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU even if CUDA is available",
    )
    args = parser.parse_args()

    db_path = os.path.abspath(args.db_path)
    output_dir = os.path.abspath(args.output_dir)
    translations = [t.strip().upper() for t in args.translations.split(",")]

    print(f"  Database:      {db_path}")
    print(f"  Output:        {output_dir}")
    print(f"  Translations:  {', '.join(translations)}")
    print(f"  Batch size:    {args.batch_size}")
    print(f"  Force CPU:     {args.cpu}")
    print()

    build_faiss_index(
        db_path, output_dir,
        translations=translations,
        batch_size=args.batch_size,
        force_cpu=args.cpu,
    )
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
