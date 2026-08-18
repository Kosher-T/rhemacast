#!/usr/bin/env python3
"""
build_topical.py — Build FAISS + BM25 indexes for Bible topical/stories search.

Reads topical_data.json (topics with descriptions + verse references),
builds:
  - topical_faiss.index   (IndexFlatIP, 384-dim, semantic search on descriptions)
  - topical_bm25.pkl      (BM25 keyword search on topic names + descriptions)
  - topical_lookup.pkl    (index → topic + verses mapping)

Replaces ERV (ENGLISHERVBIBLE) in the fuzzy search pipeline with topical search.

Usage:
  python build_topical.py
  python build_topical.py --cpu
"""

import argparse
import json
import os
import pickle
import sys
import time

import numpy as np

# Add project root to sys.path so we can import core modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ─── Data Loading ─────────────────────────────────────────────────────────────

def load_topical_data(data_path: str) -> list[dict]:
    """Load topical data from JSON file."""
    if not os.path.exists(data_path):
        print(f"[ERROR] Topical data not found: {data_path}")
        sys.exit(1)

    with open(data_path, "r", encoding="utf-8") as f:
        topics = json.load(f)

    print(f"  Loaded {len(topics)} topics")

    # Validate structure
    for t in topics:
        assert "topic" in t, f"Missing 'topic' key: {t}"
        assert "description" in t, f"Missing 'description' key: {t}"
        assert "verses" in t, f"Missing 'verses' key: {t}"

    return topics


# ─── Index Building ───────────────────────────────────────────────────────────

def build_topical_indexes(data_path: str, output_dir: str,
                          batch_size: int = 64, force_cpu: bool = False):
    """Build FAISS + BM25 indexes for topical search."""
    import faiss
    from rank_bm25 import BM25Okapi

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[ERROR] sentence-transformers is not installed.")
        sys.exit(1)

    t0 = time.perf_counter()

    # ── Load data ────────────────────────────────────────────────────────
    topics = load_topical_data(data_path)

    # ── Detect CUDA ──────────────────────────────────────────────────────
    provider = "CPUExecutionProvider"
    if not force_cpu:
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if "CUDAExecutionProvider" in providers:
                provider = "CUDAExecutionProvider"
                print("  CUDA detected — using GPU for encoding")
            else:
                print("  CUDA not available — using CPU")
        except ImportError:
            print("  [WARNING] onnxruntime not found — using CPU")

    # ── Load embedding model ─────────────────────────────────────────────
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    model_path = os.path.join(root_dir, "models", "all-MiniLM-L6-v2")
    model_path = os.path.abspath(model_path)
    print(f"  Loading embedding model from {model_path}...")
    t_model = time.perf_counter()

    try:
        model = SentenceTransformer(
            model_path,
            backend="onnx",
            model_kwargs={"provider": provider, "file_name": "onnx/model.onnx"},
        )
    except Exception:
        print("  [WARNING] ONNX backend failed, trying default...")
        model = SentenceTransformer(model_path)

    print(f"  Model loaded in {time.perf_counter() - t_model:.2f}s")

    # ── Encode descriptions for FAISS ────────────────────────────────────
    descriptions = [t["description"] for t in topics]
    print(f"  Encoding {len(descriptions)} topic descriptions...")

    embeddings = model.encode(
        descriptions,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=False,
    )

    embeddings = embeddings.astype(np.float32)
    faiss.normalize_L2(embeddings)

    emb_dim = embeddings.shape[1]
    print(f"  Embedding dimension: {emb_dim}")

    # ── Build FAISS index ────────────────────────────────────────────────
    print("  Building FAISS IndexFlatIP...")
    t_faiss = time.perf_counter()
    index = faiss.IndexFlatIP(emb_dim)
    index.add(embeddings)
    print(f"  FAISS index built in {time.perf_counter() - t_faiss:.2f}s — {index.ntotal} vectors")

    # ── Build BM25 index ─────────────────────────────────────────────────
    print("  Building BM25 index on topic names + descriptions...")
    from core.text_utils import tokenize

    bm25_docs = []
    for t in topics:
        # Combine topic name + description for keyword search
        combined = f"{t['topic']} {t['description']}"
        tokens = tokenize(combined)
        bm25_docs.append(tokens)

    bm25 = BM25Okapi(bm25_docs)
    print(f"  BM25 index built ({len(bm25_docs)} documents)")

    # ── Create lookup ────────────────────────────────────────────────────
    # FAISS index → topic mapping
    faiss_lookup = [
        {
            "topic": t["topic"],
            "description": t["description"],
            "verses": t["verses"],
        }
        for t in topics
    ]

    # BM25 index → topic mapping (same structure)
    bm25_lookup = faiss_lookup

    # ── Save ─────────────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)

    faiss_path = os.path.join(output_dir, "topical_faiss.index")
    bm25_path = os.path.join(output_dir, "topical_bm25.pkl")
    lookup_path = os.path.join(output_dir, "topical_lookup.pkl")

    faiss.write_index(index, faiss_path)
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(lookup_path, "wb") as f:
        pickle.dump(faiss_lookup, f, protocol=pickle.HIGHEST_PROTOCOL)

    # ── Report ───────────────────────────────────────────────────────────
    total_elapsed = time.perf_counter() - t0
    faiss_mb = os.path.getsize(faiss_path) / (1024 * 1024)
    bm25_mb = os.path.getsize(bm25_path) / (1024 * 1024)
    lookup_mb = os.path.getsize(lookup_path) / (1024 * 1024)

    print(f"\n  ── Topical Index Build Complete ──")
    print(f"  Topics indexed:    {len(topics)}")
    print(f"  Embedding dim:     {emb_dim}")
    print(f"  FAISS index:       {faiss_mb:.3f} MB")
    print(f"  BM25 index:        {bm25_mb:.3f} MB")
    print(f"  Lookup:            {lookup_mb:.3f} MB")
    print(f"  Total build time:  {total_elapsed:.1f}s")

    # ── Smoke test ───────────────────────────────────────────────────────
    _smoke_test(model, index, faiss_lookup, bm25, bm25_lookup)


def _smoke_test(model, faiss_index, faiss_lookup, bm25, bm25_lookup):
    """Run smoke tests for topical search."""
    import faiss as _faiss
    from core.text_utils import tokenize

    print("\n  ── Smoke Test (Topical Search) ──")

    test_queries = [
        "the prodigal son",
        "creation of the world",
        "Moses and the burning bush",
        "David and Goliath",
        "the last supper",
    ]

    for query in test_queries:
        # FAISS (semantic)
        q_emb = model.encode([query]).astype(np.float32)
        _faiss.normalize_L2(q_emb)
        scores, indices = faiss_index.search(q_emb, 3)

        print(f"\n  Query: \"{query}\"")

        # BM25 (keyword)
        tokens = tokenize(query)
        bm25_scores = bm25.get_scores(tokens)
        bm25_top = np.argsort(bm25_scores)[::-1][:3]

        # Show FAISS results
        print("    FAISS (semantic):")
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
            if idx < 0 or idx >= len(faiss_lookup):
                continue
            t = faiss_lookup[idx]
            verse_str = "; ".join(
                f"{v['book']} {v['chapter']}:{v['verse']}" for v in t["verses"][:2]
            )
            print(f"      #{rank} [{score:.4f}] {t['topic']} → {verse_str}")

        # Show BM25 results
        print("    BM25 (keyword):")
        for rank, idx in enumerate(bm25_top[:3], 1):
            t = bm25_lookup[idx]
            verse_str = "; ".join(
                f"{v['book']} {v['chapter']}:{v['verse']}" for v in t["verses"][:2]
            )
            print(f"      #{rank} [{bm25_scores[idx]:.4f}] {t['topic']} → {verse_str}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build FAISS + BM25 indexes for topical search."
    )
    parser.add_argument(
        "--data-path",
        default=os.path.join(os.path.dirname(__file__), "topical_data.json"),
        help="Path to topical data JSON (default: data/bible/topical_data.json)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "indexes"),
        help="Output directory (default: data/indexes/)",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--cpu", action="store_true", help="Force CPU")
    args = parser.parse_args()

    data_path = os.path.abspath(args.data_path)
    output_dir = os.path.abspath(args.output_dir)

    print(f"  Data:   {data_path}")
    print(f"  Output: {output_dir}\n")

    build_topical_indexes(data_path, output_dir,
                          batch_size=args.batch_size,
                          force_cpu=args.cpu)


if __name__ == "__main__":
    main()
