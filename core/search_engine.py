"""
core/search_engine.py

Phase 5 - Hybrid Search Engine
Runs Thread 3 for BM25 + FAISS search, RRF fusion, and early exit filtering.
"""

import time
import queue
import logging
import numpy as np

from core.queues import queue_b, db_write_queue, push_to_operator
from core.service_manager import manager, service_active
from core.model_manager import model_manager
from core.intent_classifier import intent_classifier
from core.text_utils import normalize_text, tokenize, STOP_WORDS
from core.bible_service import get_display_name

logger = logging.getLogger(__name__)

# Config
require_trigger_for_fast_lane = False
CONFIDENCE_THRESHOLD = 85.0

def set_confidence_threshold(value: float):
    """Allow external modules (e.g. Settings UI) to reconfigure the threshold at runtime."""
    global CONFIDENCE_THRESHOLD
    CONFIDENCE_THRESHOLD = max(0.0, min(100.0, value))
    logger.info(f"Confidence threshold updated to {CONFIDENCE_THRESHOLD}%")

LRU_CACHE = {}
CACHE_TTL = 15.0

def check_lru_cache(verse_ref: str) -> bool:
    """Returns True if the verse was recently pushed to the operator queue."""
    now = time.time()
    if verse_ref in LRU_CACHE and (now - LRU_CACHE[verse_ref]) < CACHE_TTL:
        return True
    
    LRU_CACHE[verse_ref] = now
    
    # Prune expired
    expired = [k for k, v in LRU_CACHE.items() if (now - v) >= CACHE_TTL]
    for k in expired:
        del LRU_CACHE[k]
        
    return False

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

def fuzzy_bm25_search(query: str, top_k: int = 5):
    """BM25 over the fuzzy-lane index (same translations as FAISS)."""
    bm25 = model_manager.fuzzy_bm25_index
    verse_lookup = model_manager.fuzzy_verse_lookup
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
    # FAISS has its own verse lookup (6 translations only)
    verse_lookup = model_manager.faiss_verse_lookup
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

def topical_search(query: str, top_k: int = 3):
    """Search topical/stories index for matches.
    
    Returns list of (rank, "TOPIC", topic_name, 0, verse_num, score, description) tuples
    where verse_num is actually the topic index for later lookup.
    The actual verse references are in the topical lookup.
    """
    import faiss as _faiss
    topical_faiss = model_manager.topical_faiss_index
    topical_bm25 = model_manager.topical_bm25_index
    topical_lookup = model_manager.topical_lookup
    model = model_manager.embedding_model
    
    if not topical_faiss or not topical_bm25 or not topical_lookup or not model:
        return []
    
    # Semantic search on FAISS
    q_emb = model.encode([query]).astype(np.float32)
    _faiss.normalize_L2(q_emb)
    faiss_scores, faiss_indices = topical_faiss.search(q_emb, top_k)
    
    # BM25 keyword search
    tokens = tokenize(query)
    bm25_scores = topical_bm25.get_scores(tokens)
    bm25_top_indices = np.argsort(bm25_scores)[::-1][:top_k]
    
    # Combine results using simple score fusion
    candidates = {}
    
    for rank, (idx, score) in enumerate(zip(faiss_indices[0], faiss_scores[0]), 1):
        if idx < 0 or idx >= len(topical_lookup):
            continue
        topic = topical_lookup[idx]
        key = topic["topic"]
        if key not in candidates:
            candidates[key] = {
                "topic": topic["topic"],
                "description": topic["description"],
                "verses": topic["verses"],
                "faiss_rank": rank,
                "faiss_score": float(score),
                "bm25_rank": None,
                "bm25_score": 0.0,
            }
        else:
            candidates[key]["faiss_rank"] = rank
            candidates[key]["faiss_score"] = float(score)
    
    for rank, idx in enumerate(bm25_top_indices, 1):
        topic = topical_lookup[idx]
        key = topic["topic"]
        if key not in candidates:
            candidates[key] = {
                "topic": topic["topic"],
                "description": topic["description"],
                "verses": topic["verses"],
                "faiss_rank": None,
                "faiss_score": 0.0,
                "bm25_rank": rank,
                "bm25_score": float(bm25_scores[idx]),
            }
        else:
            candidates[key]["bm25_rank"] = rank
            candidates[key]["bm25_score"] = float(bm25_scores[idx])
    
    # RRF fusion for topical results
    fused = []
    k = 60
    for key, c in candidates.items():
        rrf = 0.0
        if c["bm25_rank"] is not None:
            rrf += 1.0 / (k + c["bm25_rank"])
        if c["faiss_rank"] is not None:
            rrf += 1.0 / (k + c["faiss_rank"])
        
        fused.append({
            "confidence": rrf * 100,  # Scale to match verse confidence
            "rrf_score": rrf,
            "topic": c["topic"],
            "description": c["description"],
            "verses": c["verses"],
            "bm25_rank": c["bm25_rank"],
            "faiss_rank": c["faiss_rank"],
        })
    
    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused[:top_k]

def rrf_fuse(bm25_results, faiss_results, word_count: int, k: int = 60, dedupe_by_ref: bool = True):
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

    # Deduplicate by reference (book, chapter, verse) — keep highest confidence version
    if dedupe_by_ref:
        seen_refs = set()
        deduped = []
        for r in fused:
            ref_key = (r["book"], r["chapter"], r["verse_num"])
            if ref_key not in seen_refs:
                seen_refs.add(ref_key)
                deduped.append(r)
        fused = deduped
        
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
            
            # Phase 6: Intent Classification
            is_triggered, is_ignored, matched_phrase = intent_classifier.evaluate_intent(text_chunk)
            
            # Phase 1.5 - 8-word BM25 early exit check (Fast Lane)
            if require_trigger_for_fast_lane and word_count < 8 and not is_triggered:
                queue_b.task_done()
                continue
                
            t0 = time.perf_counter()
            
            # Lane A - BM25 lexical search
            t_bm25_start = time.perf_counter()
            bm25_res = bm25_search(text_chunk)
            t_bm25_end = time.perf_counter()
            
            # Lane B - FAISS semantic search
            t_faiss_start = time.perf_counter()
            faiss_res = faiss_search(text_chunk)
            t_faiss_end = time.perf_counter()
            
            # Lane C - Topical/stories search (replaces ERV translation)
            t_topical_start = time.perf_counter()
            topical_res = topical_search(text_chunk)
            t_topical_end = time.perf_counter()
            
            # Phase 3 RRF Fusion (verse search)
            fused = rrf_fuse(bm25_res, faiss_res, word_count)
            
            total_latency = (time.perf_counter() - t0) * 1000
            
            if fused:
                best = fused[0]
                best["intent_state"] = is_triggered
                best["intent_ignored"] = is_ignored
                
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
                    "topical_latency_ms": (t_topical_end - t_topical_start) * 1000,
                    "total_search_latency_ms": total_latency,
                    "intent_state": is_triggered,
                    "intent_ignored": is_ignored,
                    "matched_trigger": matched_phrase,
                    "best_match": best,
                    "topical_matches": topical_res[:3] if topical_res else []
                }
                
                db_write_queue.put({"type": "search_metrics", "payload": observability})
                
                # If high confidence and not ignored, push to operator queue
                if best["confidence"] >= CONFIDENCE_THRESHOLD and not is_ignored:
                    ref = f"[{get_display_name(best['version'])}] {best['book']} {best['chapter']}:{best['verse_num']}"
                    
                    if not check_lru_cache(ref):
                        # Display Decision Matrix
                        if best["confidence"] >= 85 and is_triggered:
                            priority = "high"
                        else:
                            priority = "normal"
                            
                        push_to_operator(best, best["confidence"], priority=priority)
                        
                        # Phase 7: Push Stage 3 payload to DB Write Queue
                        db_write_queue.put({
                            "type": "display_event",
                            "payload": {
                                "action": "operator_queue_push",
                                "ref": ref,
                                "priority": priority,
                                "confidence": best["confidence"],
                                "timestamp_ms": int(time.time() * 1000)
                            }
                        })
            
            # If no verse match but topical results exist, push top topical match
            if not fused and topical_res:
                best_topical = topical_res[0]
                # Create a synthetic result with the first verse from the topic
                if best_topical["verses"]:
                    v = best_topical["verses"][0]
                    push_result = {
                        "topic": best_topical["topic"],
                        "description": best_topical["description"],
                        "book": v["book"],
                        "chapter": v["chapter"],
                        "verse_num": v["verse"],
                        "text": best_topical["description"],
                        "confidence": best_topical["confidence"],
                        "is_topical": True,
                        "all_verses": best_topical["verses"],
                    }
                    push_to_operator(push_result, best_topical["confidence"], priority="normal")
            
            queue_b.task_done()
            
        except queue.Empty:
            manager.heartbeat("T3")
            continue
        except Exception as e:
            logger.error(f"Search pipeline error: {e}")

def register_search_thread():
    """Register Thread 3 with the ServiceManager."""
    manager.register_thread("T3", _search_thread_target, max_restarts=3, critical=True)
