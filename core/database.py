"""
core/database.py

Database initialization and session management.
"""

import sqlite3
import os
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'app.db')
CURRENT_SCHEMA_VERSION = 5

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
                kind TEXT DEFAULT 'verse',
                deck_id INTEGER,
                timestamp_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS operator_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                lane TEXT,
                query TEXT,
                result_count INTEGER,
                top_refs_json TEXT,
                chosen_ref TEXT,
                timestamp_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS verse_popularity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                book TEXT NOT NULL,
                chapter TEXT NOT NULL,
                verse TEXT NOT NULL,
                points REAL NOT NULL DEFAULT 0,
                picks INTEGER NOT NULL DEFAULT 0,
                updated_ms INTEGER NOT NULL
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
                tokenize='porter unicode61 remove_diacritics 2',
                contentless_delete=1
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS slides_fts_prefix USING fts5(
                title, slide_text, tags,
                content='', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2',
                contentless_delete=1
            );
        """)
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
    elif user_version < CURRENT_SCHEMA_VERSION:
        _run_migrations(conn, user_version, CURRENT_SCHEMA_VERSION)
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")

    # Defensive fix: FTS must be content='' WITH contentless_delete=1.
    # Legacy states: content='slide_decks' (broken rebuild) or plain
    # content='' (no DELETE by rowid — sync fallback was lossy).
    _ensure_slide_fts(conn)

    # Popularity store for operator-learned verse ranking (idempotent).
    _ensure_verse_popularity(conn)

    conn.commit()
    conn.close()


def _ensure_verse_popularity(conn: sqlite3.Connection):
    """Create the verse_popularity table on older databases."""
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verse_popularity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                book TEXT NOT NULL,
                chapter TEXT NOT NULL,
                verse TEXT NOT NULL,
                points REAL NOT NULL DEFAULT 0,
                picks INTEGER NOT NULL DEFAULT 0,
                updated_ms INTEGER NOT NULL
            );
        """)
    except Exception:
        pass


def _ensure_slide_fts(conn: sqlite3.Connection):
    """Recreate slide FTS indexes when their definition is outdated.

    Handles legacy states:
      - content='slide_decks' (external-content, breaks without real columns)
      - plain content='' without contentless_delete=1 (no DELETE by rowid)
      - any tokenizer without remove_diacritics (no vernacular folding)
      - missing slides_fts_prefix (no prefix-stable search)
    Reindexes from slide_decks after recreation.
    """
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='slides_fts'").fetchone()
        if not row or not row[0]:
            return
        sql = row[0]
        prefix_missing = not conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='slides_fts_prefix'"
        ).fetchone()
        legacy = (
            "content='slide_decks'" in sql or 'content="slide_decks"' in sql
            or "content=slide_decks" in sql
            or "contentless_delete" not in sql
            or "remove_diacritics" not in sql
            or prefix_missing
        )
        if not legacy:
            return
        # Preserve decks
        decks = conn.execute("SELECT id, title, tags, slides_json FROM slide_decks").fetchall()
        conn.executescript("""
            DROP TABLE IF EXISTS slides_fts;
            DROP TABLE IF EXISTS slides_fts_data;
            DROP TABLE IF EXISTS slides_fts_idx;
            DROP TABLE IF EXISTS slides_fts_docsize;
            DROP TABLE IF EXISTS slides_fts_config;
            DROP TABLE IF EXISTS slides_fts_prefix;
            DROP TABLE IF EXISTS slides_fts_prefix_data;
            DROP TABLE IF EXISTS slides_fts_prefix_idx;
            DROP TABLE IF EXISTS slides_fts_prefix_docsize;
            DROP TABLE IF EXISTS slides_fts_prefix_config;
            CREATE VIRTUAL TABLE slides_fts USING fts5(
                title, slide_text, tags,
                content='', content_rowid='id',
                tokenize='porter unicode61 remove_diacritics 2',
                contentless_delete=1
            );
            CREATE VIRTUAL TABLE slides_fts_prefix USING fts5(
                title, slide_text, tags,
                content='', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2',
                contentless_delete=1
            );
        """)
        # Re-index existing decks (both tables)
        import json as _json
        from core.slide_parser import strip_inline_markup as _strip
        for d in decks:
            try:
                slides = _json.loads(d["slides_json"]) if d["slides_json"] else []
            except Exception:
                slides = []
            slide_text = " \n ".join(_strip(s.get("text", "")) for s in slides)
            tags = d["tags"] or ""
            conn.execute(
                "INSERT INTO slides_fts(rowid, title, slide_text, tags) VALUES (?, ?, ?, ?)",
                (d["id"], d["title"], slide_text, tags),
            )
            conn.execute(
                "INSERT INTO slides_fts_prefix(rowid, title, slide_text, tags) VALUES (?, ?, ?, ?)",
                (d["id"], d["title"], slide_text, tags),
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
                tokenize='porter unicode61 remove_diacritics 2'
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
    if from_version < 4 <= to_version:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(display_events)").fetchall()]
        if "kind" not in cols:
            conn.execute("ALTER TABLE display_events ADD COLUMN kind TEXT DEFAULT 'verse'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operator_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                lane TEXT,
                query TEXT,
                result_count INTEGER,
                top_refs_json TEXT,
                chosen_ref TEXT,
                timestamp_ms INTEGER
            );
        """)
    if from_version < 5 <= to_version:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(display_events)").fetchall()]
        if "deck_id" not in cols:
            conn.execute("ALTER TABLE display_events ADD COLUMN deck_id INTEGER")


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


# ── Operator history (History tab) ──────────────────────────────────────────
# Rule: anything pushed to the live screen gets documented here, grouped per
# session, plus every operator search (query + top hits + chosen result).
# Writes are direct (operator-paced, low volume) so the History tab always
# reads fresh rows without waiting on the T4 streaming queue.

import json as _json


def current_operator_session() -> str:
    """Session id for history rows: the live transcription session, else 'global'."""
    try:
        from core.service_manager import service_active
        from core import stt_inference
        running = getattr(stt_inference, "_stt_running", None)
        if service_active.is_set() and running is not None and running.is_set():
            sid = getattr(stt_inference, "session_id", None) or "global"
            try:
                conn = get_connection()
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (session_id, start_time, audio_source)"
                    " VALUES (?, ?, ?)",
                    (sid, int(time.time() * 1000), "wireless"),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return sid
    except Exception:
        pass
    return "global"


def log_display_event(session_id: str, action: str, kind: str, ref: str,
                      text: str, translation: str, theme: str,
                      deck_id: int | None = None) -> None:
    """Document one live-screen push (display or clear). Never raises."""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO display_events (session_id, action, ref, text, translation, theme, kind, deck_id, timestamp_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, action, ref or "", text or "",
             translation or "", theme or "", kind, deck_id, int(time.time() * 1000)),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def log_live_payload(payload: dict, kind: str | None = None,
                     ref: str | None = None) -> None:
    """Document a broadcast live payload (display or clear). Never raises."""
    if not isinstance(payload, dict):
        return
    action = payload.get("action", "display")
    if action not in ("display", "clear"):
        return
    log_display_event(
        current_operator_session(), action,
        kind or payload.get("content") or "verse",
        ref or payload.get("reference") or payload.get("ref") or "",
        payload.get("text") or "",
        payload.get("translation") or "",
        payload.get("theme") or "",
        payload.get("deck_id"),
    )


def log_search_event(session_id: str, lane: str, query: str,
                     result_count: int, top_refs: list) -> int | None:
    """Document an operator search. Keystroke runs coalesce: when the newest
    row for this session+lane has a query that is a prefix of (or equal to)
    the new one within 60s, it is UPDATED instead of inserting a new row.
    Returns the row id (for mark_search_chosen) or None. Never raises."""
    try:
        now = int(time.time() * 1000)
        conn = get_connection()
        row = conn.execute(
            "SELECT id, query, timestamp_ms FROM operator_searches"
            " WHERE session_id = ? AND lane = ? ORDER BY id DESC LIMIT 1",
            (session_id, lane),
        ).fetchone()
        if row and (query == row["query"] or query.startswith(row["query"] or "")) \
                and now - (row["timestamp_ms"] or 0) < 60000:
            conn.execute(
                "UPDATE operator_searches SET query=?, result_count=?,"
                " top_refs_json=?, timestamp_ms=? WHERE id=?",
                (query, result_count, _json.dumps(top_refs or []), now, row["id"]),
            )
            conn.commit()
            conn.close()
            return row["id"]
        cur = conn.execute(
            "INSERT INTO operator_searches (session_id, lane, query, result_count,"
            " top_refs_json, chosen_ref, timestamp_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, lane, query, result_count,
             _json.dumps(top_refs or []), None, now),
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return row_id
    except Exception:
        return None


def mark_search_chosen(row_id: int | None, chosen_ref: str) -> None:
    """Record which result the operator picked. Never raises."""
    if not row_id:
        return
    try:
        conn = get_connection()
        conn.execute("UPDATE operator_searches SET chosen_ref=? WHERE id=?",
                     (chosen_ref, row_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def log_verse_pick(prompt: str, book: str, chapter, verse,
                   points: float) -> None:
    """Accumulate popularity for a picked verse under a prompt.

    Same (prompt, verse) accumulates points/picks (multiple prompts per
    verse are kept — never collapsed); oldest rows past the cap are
    pruned. Private by design: debug-logged only, never console.
    Never raises.
    """
    from core.constants import POPULARITY_MAX_PROMPTS
    if not (prompt or "").strip() or not book:
        return
    try:
        now = int(time.time() * 1000)
        prompt = prompt.strip()
        book, chapter, verse = str(book), str(chapter), str(verse)
        conn = get_connection()
        row = conn.execute(
            "SELECT id, points, picks FROM verse_popularity"
            " WHERE prompt = ? AND book = ? AND chapter = ? AND verse = ?",
            (prompt, book, chapter, verse),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE verse_popularity SET points = points + ?,"
                " picks = picks + 1, updated_ms = ? WHERE id = ?",
                (float(points), now, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO verse_popularity"
                " (prompt, book, chapter, verse, points, picks, updated_ms)"
                " VALUES (?, ?, ?, ?, ?, 1, ?)",
                (prompt, book, chapter, verse, float(points), now),
            )
        conn.execute(
            "DELETE FROM verse_popularity WHERE id NOT IN ("
            "SELECT id FROM verse_popularity"
            " ORDER BY updated_ms DESC, id DESC LIMIT ?)",
            (POPULARITY_MAX_PROMPTS,),
        )
        conn.commit()
        conn.close()
        logger.debug("Popularity pick: %r -> %s %s:%s (+%s)",
                     prompt, book, chapter, verse, points)
    except Exception:
        pass


def read_verse_popularity() -> list:
    """All (prompt, verse, points) rows for prompt matching. Never raises."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT prompt, book, chapter, verse, points, picks"
            " FROM verse_popularity"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_history_sessions() -> list:
    """Session groups newest-first: real sessions plus any extra session ids
    found on operator rows (including 'global'). Groups without items are
    skipped so empty transcription sessions don't clutter the view."""
    try:
        conn = get_connection()
        seen: dict[str, dict] = {}
        for row in conn.execute(
                "SELECT session_id, start_time FROM sessions").fetchall():
            sid = row["session_id"]
            if sid not in seen:
                seen[sid] = {"session_id": sid, "start_time": row["start_time"]}
        for table in ("display_events", "operator_searches"):
            for row in conn.execute(
                    f"SELECT DISTINCT session_id FROM {table}").fetchall():
                sid = row["session_id"] or "global"
                if sid not in seen:
                    seen[sid] = {"session_id": sid, "start_time": None}
        groups = []
        for sid, meta in seen.items():
            if sid == "global":
                de_scope = "session_id='global' OR session_id IS NULL"
                se_scope = "session_id='global'"
            else:
                safe = sid.replace("'", "''")
                de_scope = f"session_id='{safe}'"
                se_scope = de_scope
            pushes = conn.execute(
                f"SELECT COUNT(*) c FROM display_events WHERE {de_scope}").fetchone()["c"]
            searches = conn.execute(
                f"SELECT COUNT(*) c FROM operator_searches WHERE {se_scope}").fetchone()["c"]
            bounds = conn.execute(
                "SELECT MIN(timestamp_ms) mn, MAX(timestamp_ms) mx FROM ("
                f" SELECT timestamp_ms FROM display_events WHERE {de_scope}"
                f" UNION ALL SELECT timestamp_ms FROM operator_searches WHERE {se_scope})").fetchone()
            start = meta["start_time"] or bounds["mn"]
            groups.append({"session_id": sid, "start_time": start,
                           "end_time": bounds["mx"], "pushes": pushes, "searches": searches})
        conn.close()
        groups.sort(key=lambda g: (g["end_time"] or 0, g["start_time"] or 0), reverse=True)
        return [g for g in groups if (g["pushes"] or 0) + (g["searches"] or 0) > 0]
    except Exception:
        return []


def get_session_items(session_id: str, limit: int = 500) -> list:
    """Chronological live pushes + searches for one session (oldest first)."""
    try:
        conn = get_connection()
        if session_id == "global":
            de_filter = "session_id='global' OR session_id IS NULL"
            se_filter = "session_id='global'"
        else:
            de_filter = "session_id='" + session_id.replace("'", "''") + "'"
            se_filter = de_filter
        rows = conn.execute(
            "SELECT 'display' AS kind2, timestamp_ms, action, ref, text, translation, theme, kind, deck_id,"
            " NULL AS lane, NULL AS query, NULL AS result_count, NULL AS top_refs, NULL AS chosen"
            f" FROM display_events WHERE {de_filter} "
            "UNION ALL SELECT 'search', timestamp_ms, NULL, NULL, NULL, NULL, NULL, NULL, NULL,"
            " lane, query, result_count, top_refs_json, chosen_ref"
            f" FROM operator_searches WHERE {se_filter} "
            "ORDER BY timestamp_ms ASC LIMIT ?",
            (limit,)).fetchall()
        conn.close()
        items = []
        for r in rows:
            if r["kind2"] == "display":
                items.append({"type": "display", "action": r["action"], "kind": r["kind"] or "verse",
                              "ref": r["ref"] or "", "text": r["text"] or "",
                              "translation": r["translation"] or "", "theme": r["theme"] or "",
                              "deck_id": r["deck_id"], "timestamp_ms": r["timestamp_ms"]})
            else:
                try:
                    top = _json.loads(r["top_refs"] or "[]")
                except Exception:
                    top = []
                items.append({"type": "search", "lane": r["lane"], "query": r["query"] or "",
                              "result_count": r["result_count"] or 0, "top_refs": top,
                              "chosen": r["chosen"], "timestamp_ms": r["timestamp_ms"]})
        return items
    except Exception:
        return []
