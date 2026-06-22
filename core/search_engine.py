"""
core/search_engine.py

Phase 5 - Hybrid Search Engine
Runs Thread 3 for BM25 + FAISS search, RRF fusion, and early exit filtering.
"""

import time
import queue
import logging
import re
import numpy as np

from core.queues import queue_b, db_write_queue, push_to_operator
from core.service_manager import manager, service_active
from core.model_manager import model_manager

logger = logging.getLogger(__name__)

# Config
require_trigger_for_fast_lane = False
CONFIDENCE_THRESHOLD = 50.0  # arbitrary default

# ─── Normalization ────────────────────────────────────────────────────────────

STOP_WORDS = frozenset({"the", "is", "a", "and", "to", "of", "in", "that"})
_PUNCTUATION_TO_SPACE = re.compile(r"[\-\u2010\u2011\u2012\u2013\u2014\u2015/:]")
_STRIP_NON_ALNUM = re.compile(r"[^a-z0-9\s]")

def normalize_text(text: str) -> str:
    """Normalize a verse text for BM25 tokenization."""
    text = text.replace("'", "").replace("\u2019", "").replace("\u2018", "")
    text = _PUNCTUATION_TO_SPACE.sub(" ", text)
    text = text.lower()
    text = _STRIP_NON_ALNUM.sub("", text)
    return " ".join(text.split())

def tokenize(text: str) -> list[str]:
    """Tokenize normalized text into words, stripping stop-words."""
    normalized = normalize_text(text)
    return [w for w in normalized.split() if w not in STOP_WORDS]

# ─── Search Lanes ────────────────────────────────────────────────────────────

def bm25_search(query: str, top_k: int = 5):
    bm25 = model_manager.bm25_index
    verse_lookup = model_manager.verse_lookup
    if not bm25 or not verse_lookup:
        return []
    
    tokens = tokenize(query)
    if not tokens:
        return []
    
    scores = bm25.get_scores(tokens)
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for rank, idx in enumerate(top_indices, 1):
        version, book, chapter, verse_num, text = verse_lookup[idx]
        results.append((rank, version, book, chapter, verse_num, float(scores[idx]), text))
    return results

def faiss_search(query: str, top_k: int = 5):
    import faiss as _faiss
    index = model_manager.faiss_index
    model = model_manager.embedding_model
    verse_lookup = model_manager.verse_lookup
    if not index or not model or not verse_lookup:
        return []
    
    q_emb = model.encode([query]).astype(np.float32)
    _faiss.normalize_L2(q_emb)
    scores, indices = index.search(q_emb, top_k)
    
    results = []
    for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
        if idx < 0 or idx >= len(verse_lookup):
            continue
        version, book, chapter, verse_num, text = verse_lookup[idx]
        results.append((rank, version, book, chapter, verse_num, float(score), text))
    return results

def rrf_fuse(bm25_results, faiss_results, word_count: int, k: int = 60):
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
            
    fused = []
    RRF_max_full = 0.0327
    RRF_min = 0.0153
    
    scale_factor = min(1.0, word_count / 15.0)
    if word_count < 8:
        scale_factor = 0.4 + (word_count - 1) * 0.1
    RRF_max = RRF_max_full * scale_factor
    
    for key, c in candidates.items():
        rrf = 0.0
        if c["bm25_rank"] is not None:
            rrf += 1.0 / (k + c["bm25_rank"])
        if c["faiss_rank"] is not None:
            rrf += 1.0 / (k + c["faiss_rank"])
            
        confidence = (rrf - RRF_min) / (RRF_max - RRF_min) * 100 if RRF_max > RRF_min else 0.0
        confidence = max(0, min(100, confidence))
        
        fused.append({
            "confidence": confidence,
            "rrf_score": rrf,
            "version": c["version"],
            "book": c["book"],
            "chapter": c["chapter"],
            "verse_num": c["verse_num"],
            "text": c["text"],
            "bm25_rank": c["bm25_rank"],
            "faiss_rank": c["faiss_rank"]
        })
        
    fused.sort(key=lambda x: x["confidence"], reverse=True)
    return fused

# ─── Thread Target ───────────────────────────────────────────────────────────

def _search_thread_target():
    logger.info("Starting Search Pipeline (Thread 3)")
    
    while service_active.is_set():
        try:
            payload = queue_b.get(timeout=0.5)
            manager.heartbeat("T3")
            
            text_chunk = payload.get("text_chunk", "")
            word_count = payload.get("word_count", 0)
            
            # Phase 1.5 - 8-word BM25 early exit check (Fast Lane)
            if require_trigger_for_fast_lane and word_count < 8:
                queue_b.task_done()
                continue
                
            t0 = time.perf_counter()
            
            # Lane A
            t_bm25_start = time.perf_counter()
            bm25_res = bm25_search(text_chunk)
            t_bm25_end = time.perf_counter()
            
            # Lane B
            t_faiss_start = time.perf_counter()
            faiss_res = faiss_search(text_chunk)
            t_faiss_end = time.perf_counter()
            
            # Phase 3 RRF Fusion
            fused = rrf_fuse(bm25_res, faiss_res, word_count)
            
            total_latency = (time.perf_counter() - t0) * 1000
            
            if fused:
                best = fused[0]
                
                # Push Stage 2 payload to DB Write Queue (search observability)
                observability = {
                    "session_id": payload.get("session_id"),
                    "sequence_id": payload.get("sequence_id"),
                    "query": text_chunk,
                    "normalized_query": normalize_text(text_chunk),
                    "query_tokens": tokenize(text_chunk),
                    "word_count": word_count,
                    "bm25_latency_ms": (t_bm25_end - t_bm25_start) * 1000,
                    "faiss_latency_ms": (t_faiss_end - t_faiss_start) * 1000,
                    "total_search_latency_ms": total_latency,
                    "best_match": best
                }
                
                db_write_queue.put({"type": "search_metrics", "payload": observability})
                
                # If high confidence, push to operator queue
                if best["confidence"] >= CONFIDENCE_THRESHOLD:
                    push_to_operator(best, best["confidence"])
            
            queue_b.task_done()
            
        except queue.Empty:
            manager.heartbeat("T3")
            continue
        except Exception as e:
            logger.error(f"Search pipeline error: {e}")

def register_search_thread():
    """Register Thread 3 with the ServiceManager."""
    manager.register_thread("T3", _search_thread_target, max_restarts=3, critical=True)
