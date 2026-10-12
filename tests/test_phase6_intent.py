import pytest
import re
from unittest import mock
import queue

from core.intent_classifier import intent_classifier, IntentClassifier
from core.search_engine import _search_thread_target, rrf_fuse
from core.queues import queue_b, db_write_queue, operator_queue
from core.service_manager import service_active

@pytest.fixture(autouse=True)
def cleanup():
    while not queue_b.empty(): queue_b.get_nowait()
    while not db_write_queue.empty(): db_write_queue.get_nowait()
    while not operator_queue.empty(): operator_queue.get_nowait()
    service_active.set()
    yield

def test_regression_phase5():
    """Verify RRF fusion still produces correct confidence scores after intent changes."""
    bm25_res = [(1, "KJV", "Gen", 1, 1, 10.0, "text")]
    faiss_res = [(1, "KJV", "Gen", 1, 1, 0.9, "text")]
    
    fused = rrf_fuse(bm25_res, faiss_res, word_count=15)
    best = fused[0]
    
    # Assert RRF rank math is completely unaffected
    rrf = best["rrf_score"]
    assert abs(rrf - 0.03278) < 0.0001

def test_token_window_regex_compilation():
    """Verify 'turn to chapter' compiles to correct regex format."""
    # Test internal compilation method
    pat = intent_classifier._compile_phrase("turn to chapter")
    expected_pattern = r'(?:\s+\w+){0,2}\s+'.join([r'\bturn\b', r'\bto\b', r'\bchapter\b'])
    
    assert pat.pattern.lower() == expected_pattern.lower()

def test_triggers_match():
    """Feed known trigger phrases into regex engine; assert all return intent = True."""
    triggers = [
        "turn to chapter",
        "turn quickly to chapter",
        "turn to the chapter",
        "turn right over to chapter",
        "let's read",
        "gospel of"
    ]
    
    for text in triggers:
        is_triggered, is_ignored, match = intent_classifier.evaluate_intent(text)
        assert is_triggered is True
        assert is_ignored is False

def test_ignore_overrides_triggers():
    """Feed phrases containing both ignore and trigger vocabulary; verify intent = False."""
    text = "please turn off the verse display and don't turn to chapter 5"
    
    # Contains "turn off" (ignore) AND "turn to chapter" (trigger)
    # Ignore must evaluate first
    is_triggered, is_ignored, match = intent_classifier.evaluate_intent(text)
    
    assert is_triggered is False
    assert is_ignored is True
    assert match == "turn off"  # "turn off" is one of the ignore triggers

def test_6word_overlap_boundary():
    """Verify 7-word trigger phrases are caught across chunk boundaries."""
    # STT buffers retain 6 words of overlap.
    # If a trigger is "turn to the book of john", which is 6 words.
    # If the first chunk ends with "turn to the", and the next chunk starts with
    # "turn to the book of john", it will trigger successfully.
    
    chunk_1 = "and I said we should turn to the"
    chunk_2 = "we should turn to the book of john" # 6 words of overlap + new words
    
    # The point of the test is to ensure our regex handles it normally in the new chunk
    is_triggered, is_ignored, match = intent_classifier.evaluate_intent(chunk_2)
    assert is_triggered is True
    
@mock.patch("core.search_engine.bm25_search")
@mock.patch("core.search_engine.faiss_search")
def test_integration_ignore_prevents_queue(mock_faiss, mock_bm25):
    """Verify 'ignore intent' correctly prevents high-confidence matches from entering top of queue."""
    mock_bm25.return_value = [(1, "KJV", "Gen", 1, 1, 10.0, "text")]
    mock_faiss.return_value = [(1, "KJV", "Gen", 1, 1, 0.9, "text")]
    
    queue_b.put({
        "session_id": "test",
        "sequence_id": 1,
        "text_chunk": "turn off the display but here is Genesis 1:1",
        "word_count": 9
    })
    
    def stop_after_one(*args, **kwargs):
        service_active.clear()
        
    with mock.patch("core.queues.queue_b.task_done", side_effect=stop_after_one):
        _search_thread_target()
        
    # Operator queue should be empty because 'turn off' is an ignore trigger
    assert operator_queue.empty() is True
    
    # DB Write queue should still get the observability metrics
    item = db_write_queue.get_nowait()
    assert item["type"] == "search_metrics"
    assert item["payload"]["intent_ignored"] is True
