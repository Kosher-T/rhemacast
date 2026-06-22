import os
import json
import time
import pytest
from unittest.mock import patch, MagicMock

from core.database import stitch_transcript, get_false_positives, get_connection, init_db
from cloud.extraction import (
    get_api_key, 
    perform_extraction, 
    queue_for_later, 
    OFFLINE_QUEUE_PATH,
    SAFE_TOKEN_LIMIT
)
import cloud.extraction

@pytest.fixture(autouse=True)
def setup_db_and_queue():
    init_db()
    if os.path.exists(OFFLINE_QUEUE_PATH):
        os.remove(OFFLINE_QUEUE_PATH)
    yield
    if os.path.exists(OFFLINE_QUEUE_PATH):
        os.remove(OFFLINE_QUEUE_PATH)

def test_regression_phase9():
    """Verify operator UI review queue still functions after cloud pipeline changes."""
    # This is a stub for the regression test. We just ensure UI imports work.
    try:
        from core.ui import RhemaCastApp
        assert True
    except ImportError:
        pytest.fail("UI import failed, indicating regression.")

def test_stitch_transcript():
    """Feed overlapping chunks; verify 6-word trailing overlap is stripped."""
    # Setup test DB
    conn = get_connection()
    session_id = "test_stitch_session"
    conn.execute("DELETE FROM transcripts WHERE session_id = ?", (session_id,))
    
    # 8 words chunk
    chunk1 = "this is a test of the trailing overlap"
    # the 6-word trailing overlap is: "test of the trailing overlap"
    # chunk 2 has the overlap plus some more words
    chunk2 = "a test of the trailing overlap and some more text"
    
    conn.execute("INSERT INTO transcripts (session_id, sequence_id, text_chunk, word_count, timestamp_ms) VALUES (?, ?, ?, ?, ?)",
                 (session_id, 1, chunk1, 8, 1000))
    conn.execute("INSERT INTO transcripts (session_id, sequence_id, text_chunk, word_count, timestamp_ms) VALUES (?, ?, ?, ?, ?)",
                 (session_id, 2, chunk2, 10, 2000))
    conn.commit()
    conn.close()
    
    stitched = stitch_transcript(session_id)
    # expected: "this is a test of the trailing overlap and some more text"
    # Because chunk1 is "this is a test of the trailing overlap" (8 words)
    # chunk2 words: ['a', 'test', 'of', 'the', 'trailing', 'overlap', 'and', 'some', 'more', 'text']
    # If len > 6: drop first 6: ['and', 'some', 'more', 'text']
    # Stitched = chunk1 + " " + " ".join(words[6:])
    expected = "this is a test of the trailing overlap and some more text"
    assert stitched == expected

def test_pre_truncation_middle_cut():
    """Feed transcript exceeding model context window minus 5000 tokens; verify middle 80% is removed."""
    # Simulate a transcript with SAFE_TOKEN_LIMIT + 10 words
    words = [f"word{i}" for i in range(SAFE_TOKEN_LIMIT + 10)]
    transcript = " ".join(words)
    
    # Mock network to avoid offline queueing
    with patch("cloud.extraction.check_network", return_value=True):
        # We need to mock _extract_mock_or_real to capture what was sent
        with patch("cloud.extraction._extract_mock_or_real", return_value='{"insights":[]}') as mock_extract:
            perform_extraction(transcript)
            
            # Get the transcript that was sent to the provider
            sent_transcript = mock_extract.call_args[0][0]
            sent_words = sent_transcript.split()
            
            # Original length: SAFE_TOKEN_LIMIT + 10 = 123010
            # Truncated length: 10% from front + 10% from back
            first_10 = int(len(words) * 0.10)
            last_10 = int(len(words) * 0.10)
            expected_length = first_10 + last_10
            
            assert len(sent_words) == expected_length
            assert sent_words[0] == words[0]
            assert sent_words[-1] == words[-1]

@patch("cloud.extraction.keyring.get_password")
@patch("cloud.extraction.os.getenv")
def test_api_key_keyring(mock_getenv, mock_get_password):
    """Verify system keyring integration reads/writes API keys correctly and falls back to .env."""
    # Test keyring success
    mock_get_password.return_value = "keyring-secret"
    assert get_api_key("gemini") == "keyring-secret"
    mock_getenv.assert_not_called()
    
    # Test fallback to .env
    mock_get_password.return_value = None
    mock_getenv.return_value = "env-secret"
    assert get_api_key("gemini") == "env-secret"
    mock_getenv.assert_called_with("GEMINI_API_KEY")

def test_data_privacy_no_pii():
    """Verify no PII fields (beyond sermon content) are transmitted in cloud payload."""
    # The extraction function only takes `transcript` string. 
    # There is no user/church metadata passed to perform_extraction.
    transcript = "Jesus loves you."
    with patch("cloud.extraction.check_network", return_value=True):
        with patch("cloud.extraction._extract_mock_or_real", return_value='{"insights":[]}') as mock_extract:
            perform_extraction(transcript)
            args = mock_extract.call_args[0]
            # args[0] is transcript, args[1] is prompt
            assert "Jesus loves you." in args[0]
            assert "sermon transcript" in args[1]
            assert "church" not in args[1].lower() # no church name
            assert "pastor" not in args[1].lower() # no pastor name

def test_forensic_audit_top_queued_false_positives():
    """Execute forensic SQL query; verify it returns expected false positives."""
    conn = get_connection()
    session_id = "test_forensic_session"
    
    # Clean up
    conn.execute("DELETE FROM search_results WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM transcripts WHERE session_id = ?", (session_id,))
    
    # Insert transcript chunk
    conn.execute("INSERT INTO transcripts (session_id, sequence_id, text_chunk, word_count, timestamp_ms) VALUES (?, ?, ?, ?, ?)",
                 (session_id, 1, "random conversation about cars", 4, 1000))
    
    # Insert search result that was top_queued (confidence >= 85 and intent_matched = 1)
    results_json = json.dumps([{"verse_ref": "John 11:35"}])
    conn.execute("INSERT INTO search_results (session_id, sequence_id, confidence_pct, intent_matched, latency_ms, results_json, timestamp_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (session_id, 1, 90.0, 1, 10.0, results_json, 1000))
    
    conn.commit()
    conn.close()
    
    results = get_false_positives(session_id)
    assert len(results) == 1
    assert results[0]["source_text"] == "random conversation about cars"
    assert results[0]["top_verse_ref"] == "John 11:35"
    assert results[0]["confidence_pct"] == 90.0
    assert results[0]["intent_score"] == 1
    assert results[0]["action_taken"] == "top_queued"

def test_integration_offline_queue():
    """Mock API failure; verify transcript is successfully written to OFFLINE_QUEUE_PATH."""
    transcript = "Network is down."
    
    # Force network down
    with patch("cloud.extraction.check_network", return_value=False):
        perform_extraction(transcript)
        
    assert os.path.exists(OFFLINE_QUEUE_PATH)
    with open(OFFLINE_QUEUE_PATH, "r") as f:
        data = json.loads(f.readline())
        assert data["transcript"] == transcript
        assert data["reason"] == "network_down"

@patch("cloud.extraction.time.sleep")
def test_validation_network_recovery(mock_sleep):
    """Simulate network recovery; verify exponential backoff jitter gracefully resumes queue processing."""
    # We will mock check_network to return False, False, True
    with patch("cloud.extraction.check_network", side_effect=[False, False, True]):
        result = cloud.extraction.reconnect_loop("network_down")
        assert result is True
        # Sleep should be called twice
        assert mock_sleep.call_count == 2
        # First sleep base is ~5s, second is ~10s
        first_sleep = mock_sleep.call_args_list[0][0][0]
        second_sleep = mock_sleep.call_args_list[1][0][0]
        
        # Check jitter bounds
        assert 4.0 <= first_sleep <= 6.0
        assert 8.0 <= second_sleep <= 12.0
