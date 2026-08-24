"""
core/database.py

Database initialization and session management.
"""

import sqlite3
import os
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'app.db')
CURRENT_SCHEMA_VERSION = 2

def get_connection():
    """Returns a new SQLite connection with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    """Initialize tables and apply schema migrations."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    
    cursor = conn.execute("PRAGMA user_version")
    user_version = cursor.fetchone()[0]
    
    if user_version == 0:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                sequence_id INTEGER,
                text_chunk TEXT,
                word_count INTEGER,
                timestamp_ms INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                sequence_id INTEGER,
                confidence_pct REAL,
                intent_matched BOOLEAN,
                latency_ms REAL,
                results_json TEXT,
                timestamp_ms INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS display_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                action TEXT,
                ref TEXT,
                text TEXT,
                translation TEXT,
                theme TEXT,
                timestamp_ms INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time INTEGER,
                audio_source TEXT CHECK(audio_source = 'wireless')
            );
            
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS slide_decks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                author      TEXT,
                year        INTEGER,
                ccli        TEXT,
                tags        TEXT,
                source_path TEXT,
                raw_text    TEXT    NOT NULL,
                slides_json TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS slides_fts USING fts5(
                title, slide_text, tags,
                content='', content_rowid='id',
                tokenize='porter unicode61'
            );
        """)
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
    elif user_version < CURRENT_SCHEMA_VERSION:
        _run_migrations(conn, user_version, CURRENT_SCHEMA_VERSION)
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")

    # Defensive fix: FTS must be content='' (slide_text is derived, not a column in slide_decks).
    # Older builds used content='slide_decks' which breaks rebuild and triggers.
    _ensure_slide_fts(conn)

    conn.commit()
    conn.close()


def _ensure_slide_fts(conn: sqlite3.Connection):
    """Recreate slides_fts with content='' if it was created with content='slide_decks'."""
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='slides_fts'").fetchone()
        if not row or not row[0]:
            return
        sql = row[0]
        if "content='slide_decks'" in sql or 'content="slide_decks"' in sql or "content=slide_decks" in sql:
            # Preserve decks
            decks = conn.execute("SELECT id, title, tags, slides_json FROM slide_decks").fetchall()
            conn.executescript("""
                DROP TABLE IF EXISTS slides_fts;
                DROP TABLE IF EXISTS slides_fts_data;
                DROP TABLE IF EXISTS slides_fts_idx;
                DROP TABLE IF EXISTS slides_fts_docsize;
                DROP TABLE IF EXISTS slides_fts_config;
                CREATE VIRTUAL TABLE slides_fts USING fts5(
                    title, slide_text, tags,
                    content='', content_rowid='id',
                    tokenize='porter unicode61'
                );
            """)
            # Re-index existing decks
            import json as _json
            for d in decks:
                try:
                    slides = _json.loads(d["slides_json"]) if d["slides_json"] else []
                except Exception:
                    slides = []
                slide_text = " \n ".join(s.get("text", "") for s in slides)
                conn.execute(
                    "INSERT INTO slides_fts(rowid, title, slide_text, tags) VALUES (?, ?, ?, ?)",
                    (d["id"], d["title"], slide_text, d["tags"] or ""),
                )
            # Also drop legacy triggers if any
            conn.executescript("""
                DROP TRIGGER IF EXISTS slide_decks_ai;
                DROP TRIGGER IF EXISTS slide_decks_ad;
                DROP TRIGGER IF EXISTS slide_decks_au;
            """)
    except Exception:
        pass


def _run_migrations(conn: sqlite3.Connection, from_version: int, to_version: int):
    """Apply incremental schema migrations."""
    if from_version < 2 <= to_version:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS slide_decks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                author      TEXT,
                year        INTEGER,
                ccli        TEXT,
                tags        TEXT,
                source_path TEXT,
                raw_text    TEXT    NOT NULL,
                slides_json TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS slides_fts USING fts5(
                title, slide_text, tags,
                content='', content_rowid='id',
                tokenize='porter unicode61'
            );
        """)
        # FTS is maintained explicitly by slide_service._fts_sync_deck (slide_text derived
        # from slides_json, not trigger-friendly). No triggers — service owns sync.
        # Defensive: drop legacy triggers if this migration was previously run with them.
        conn.executescript("""
            DROP TRIGGER IF EXISTS slide_decks_ai;
            DROP TRIGGER IF EXISTS slide_decks_ad;
            DROP TRIGGER IF EXISTS slide_decks_au;
        """)
        # Ensure any FTS created with old content='' mismatch is fixed (also handled by _ensure_slide_fts)
        _ensure_slide_fts(conn)


def create_session() -> str:
    """Creates a new session and returns the session_id."""
    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M")
    conn = get_connection()
    conn.execute(
        "INSERT INTO sessions (session_id, start_time, audio_source) VALUES (?, ?, ?)",
        (session_id, int(time.time() * 1000), "wireless")
    )
    conn.commit()
    conn.close()
    return session_id

def get_open_sessions() -> list:
    """Returns a list of all existing session IDs to check for interruption."""
    conn = get_connection()
    cursor = conn.execute("SELECT session_id FROM sessions ORDER BY start_time DESC")
    sessions = [row["session_id"] for row in cursor.fetchall()]
    conn.close()
    return sessions

def get_max_sequence_id(session_id: str) -> int:
    """Returns the highest sequence_id for a given session to resume counting."""
    conn = get_connection()
    cursor = conn.execute("SELECT MAX(sequence_id) as max_seq FROM transcripts WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return row["max_seq"] if row and row["max_seq"] is not None else 0

def stitch_transcript(session_id: str) -> str:
    """Reconstructs the full transcript for a session, deduplicating the 6-word trailing overlap."""
    conn = get_connection()
    cursor = conn.execute("SELECT text_chunk FROM transcripts WHERE session_id = ? ORDER BY sequence_id ASC", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    result = ""
    for i, row in enumerate(rows):
        chunk = row["text_chunk"]
        words = chunk.split()
        if i == 0:
            result += chunk
        else:
            if len(words) > 6:
                result += " " + " ".join(words[6:])
            else:
                result += " " + chunk
    return result.strip()

def get_false_positives(session_id: str) -> list:
    """
    Forensic audit trail query to find false positives:
    Top-queued verses with low actual relevance.
    """
    query = '''
        SELECT t.text_chunk as source_text, 
               json_extract(sr.results_json, '$[0].verse_ref') as top_verse_ref, 
               sr.confidence_pct, 
               sr.intent_matched as intent_score,
               CASE WHEN sr.confidence_pct >= 85 AND sr.intent_matched = 1 THEN 'top_queued'
                    WHEN sr.confidence_pct >= 40 THEN 'operator_queue'
                    ELSE 'discard' END as action_taken
        FROM search_results sr
        JOIN transcripts t ON sr.session_id = t.session_id AND sr.sequence_id = t.sequence_id
        WHERE sr.session_id = ? 
          AND (CASE WHEN sr.confidence_pct >= 85 AND sr.intent_matched = 1 THEN 'top_queued'
                    WHEN sr.confidence_pct >= 40 THEN 'operator_queue'
                    ELSE 'discard' END) = 'top_queued'
        ORDER BY sr.confidence_pct ASC;
    '''
    conn = get_connection()
    cursor = conn.execute(query, (session_id,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ── Settings Persistence ──

def get_setting(key: str, default: str = None) -> str | None:
    """Retrieve a setting value by key. Returns default if not found."""
    try:
        conn = get_connection()
        cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception:
        return default


def set_setting(key: str, value: str) -> bool:
    """Insert or update a setting value. Returns True on success."""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def delete_setting(key: str) -> bool:
    """Delete a setting by key. Returns True on success."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False
