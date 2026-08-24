"""
core/slide_service.py

CRUD + FTS for slide_decks (songs / freeform slides).

Storage: data/slides/*.txt  (convention, not enforced)
DB: app.db  slide_decks + slides_fts (porter stemming)
Parser: core.slide_parser
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from core.database import DB_PATH, get_connection, init_db
from core.slide_parser import parse_slide_txt

_SLIDES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "slides")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slides_to_fts_text(slides: list[dict]) -> str:
    """Concatenate slide texts for FTS indexing."""
    return " \n ".join(s.get("text", "") for s in slides)


def _fts_sync_deck(conn: sqlite3.Connection, deck_id: int, title: str, slides: list[dict], tags: str | None):
    """Upsert FTS row for deck_id. Caller must commit. Works for content='' FTS."""
    slide_text = _slides_to_fts_text(slides)
    # For content='' FTS, delete via rowid, then insert. Both forms work; prefer explicit DELETE.
    try:
        conn.execute("DELETE FROM slides_fts WHERE rowid = ?", (deck_id,))
    except Exception:
        try:
            conn.execute(
                "INSERT INTO slides_fts(slides_fts, rowid, title, slide_text, tags) VALUES('delete', ?, ?, ?, ?)",
                (deck_id, title, "", tags or ""),
            )
        except Exception:
            pass
    conn.execute(
        "INSERT INTO slides_fts(rowid, title, slide_text, tags) VALUES (?, ?, ?, ?)",
        (deck_id, title, slide_text, tags or ""),
    )


def _fts_delete_deck(conn: sqlite3.Connection, deck_id: int, title: str = "", tags: str | None = ""):
    try:
        conn.execute("DELETE FROM slides_fts WHERE rowid = ?", (deck_id,))
    except Exception:
        try:
            conn.execute(
                "INSERT INTO slides_fts(slides_fts, rowid, title, slide_text, tags) VALUES('delete', ?, ?, ?, ?)",
                (deck_id, title, "", tags or ""),
            )
        except Exception:
            pass


# ── CRUD ────────────────────────────────────────────────────────────────────

def create_deck(
    raw_text: str,
    source_path: str | None = None,
    author: str | None = None,
    year: int | None = None,
    ccli: str | None = None,
    tags: str | None = None,
) -> dict:
    """
    Parse raw_text, insert deck, sync FTS. Returns deck dict.
    Raises ValueError if no title could be parsed (title may be "" — we allow it, but caller can validate).
    """
    init_db()
    parsed = parse_slide_txt(raw_text)
    title = parsed["title"]
    slides = parsed["slides"]
    slides_json = json.dumps(slides, ensure_ascii=False)
    now = _now_iso()

    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO slide_decks
           (title, author, year, ccli, tags, source_path, raw_text, slides_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, author, year, ccli, tags, source_path, raw_text, slides_json, now, now),
    )
    deck_id = cur.lastrowid
    # FTS sync — delete is no-op on insert, but keep symmetric
    try:
        conn.execute(
            "INSERT INTO slides_fts(rowid, title, slide_text, tags) VALUES (?, ?, ?, ?)",
            (deck_id, title, _slides_to_fts_text(slides), tags or ""),
        )
    except Exception:
        # fallback to sync helper
        _fts_sync_deck(conn, deck_id, title, slides, tags)

    conn.commit()
    conn.close()
    return get_deck(deck_id)


def get_deck(deck_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM slide_decks WHERE id = ?", (deck_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_deck(row)


def list_decks(order_by: str = "updated_at DESC") -> list[dict]:
    # whitelist order_by to avoid injection
    allowed = {"updated_at DESC", "updated_at ASC", "created_at DESC", "created_at ASC", "title ASC", "title DESC"}
    if order_by not in allowed:
        order_by = "updated_at DESC"
    conn = get_connection()
    rows = conn.execute(f"SELECT * FROM slide_decks ORDER BY {order_by}").fetchall()
    conn.close()
    return [_row_to_deck(r) for r in rows]


def update_deck(
    deck_id: int,
    raw_text: str | None = None,
    author: str | None = None,
    year: int | None = None,
    ccli: str | None = None,
    tags: str | None = None,
    source_path: str | None = None,
) -> Optional[dict]:
    """
    Update deck. If raw_text provided, re-parse title/slides. Other fields update if not None.
    Pass tags="" to clear. Returns updated deck or None if not found.
    """
    init_db()
    conn = get_connection()
    row = conn.execute("SELECT * FROM slide_decks WHERE id = ?", (deck_id,)).fetchone()
    if not row:
        conn.close()
        return None

    cur_title = row["title"]
    cur_slides_json = row["slides_json"]
    cur_raw = row["raw_text"]
    cur_author = row["author"]
    cur_year = row["year"]
    cur_ccli = row["ccli"]
    cur_tags = row["tags"]
    cur_source = row["source_path"]

    # Determine new values
    new_raw = cur_raw
    new_title = cur_title
    new_slides_json = cur_slides_json
    new_slides = json.loads(cur_slides_json) if cur_slides_json else []

    if raw_text is not None:
        parsed = parse_slide_txt(raw_text)
        new_raw = raw_text
        new_title = parsed["title"]
        new_slides = parsed["slides"]
        new_slides_json = json.dumps(new_slides, ensure_ascii=False)

    # Use sentinel to allow clearing: if caller passed the param (not default None for update),
    # we can't distinguish "not passed" vs "clear". So we use a trick: inspect call via
    # explicit None means clear for tags/author/ccli/year/source_path — but that also means
    # we can't skip update. Instead caller should fetch and pass through values they want kept.
    # Simpler: only update non-None values for optional fields; to clear, caller uses "".
    # For year, None means no change; to clear year pass -1 or handle externally.
    new_author = author if author is not None else cur_author
    new_year = year if year is not None else cur_year
    new_ccli = ccli if ccli is not None else cur_ccli
    new_tags = tags if tags is not None else cur_tags
    new_source = source_path if source_path is not None else cur_source

    now = _now_iso()
    conn.execute(
        """UPDATE slide_decks
           SET title=?, author=?, year=?, ccli=?, tags=?, source_path=?, raw_text=?, slides_json=?, updated_at=?
           WHERE id=?""",
        (new_title, new_author, new_year, new_ccli, new_tags, new_source, new_raw, new_slides_json, now, deck_id),
    )
    # FTS sync
    _fts_sync_deck(conn, deck_id, new_title, new_slides, new_tags)
    conn.commit()
    conn.close()
    return get_deck(deck_id)


def delete_deck(deck_id: int) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT title, tags FROM slide_decks WHERE id = ?", (deck_id,)).fetchone()
    if not row:
        conn.close()
        return False
    _fts_delete_deck(conn, deck_id, row["title"], row["tags"])
    conn.execute("DELETE FROM slide_decks WHERE id = ?", (deck_id,))
    conn.commit()
    conn.close()
    return True


def _row_to_deck(row: sqlite3.Row) -> dict:
    try:
        slides = json.loads(row["slides_json"]) if row["slides_json"] else []
    except Exception:
        slides = []
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "year": row["year"],
        "ccli": row["ccli"],
        "tags": row["tags"],
        "source_path": row["source_path"],
        "raw_text": row["raw_text"],
        "slides": slides,
        "slides_json": row["slides_json"],
        "slide_count": len(slides),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ── Import / Reparse ────────────────────────────────────────────────────────

def import_txt(path: str, tags: str | None = None) -> dict:
    """
    Read txt file at path, parse, and create deck with source_path=path.
    If a deck already exists with same source_path, it is updated (re-import).
    Returns deck dict.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()

    init_db()
    conn = get_connection()
    row = conn.execute("SELECT id FROM slide_decks WHERE source_path = ?", (os.path.abspath(path),)).fetchone()
    conn.close()

    abs_path = os.path.abspath(path)
    if row:
        return update_deck(row["id"], raw_text=raw, tags=tags, source_path=abs_path)
    else:
        return create_deck(raw, source_path=abs_path, tags=tags)


def import_all_txts(directory: str | None = None) -> list[dict]:
    """Import every .txt in directory (default data/slides). Returns list of decks."""
    directory = directory or _SLIDES_DIR
    if not os.path.isdir(directory):
        return []
    decks = []
    for fname in sorted(os.listdir(directory)):
        if fname.lower().endswith(".txt"):
            path = os.path.join(directory, fname)
            try:
                decks.append(import_txt(path))
            except Exception:
                continue
    return decks


def reparse_all() -> int:
    """Re-parse raw_text for every deck (after parser change). Returns count updated."""
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT id, raw_text FROM slide_decks").fetchall()
    # Collect to avoid cursor invalidation during update
    items = [(r["id"], r["raw_text"]) for r in rows]
    conn.close()

    count = 0
    for deck_id, raw in items:
        parsed = parse_slide_txt(raw)
        slides = parsed["slides"]
        title = parsed["title"]
        slides_json = json.dumps(slides, ensure_ascii=False)
        now = _now_iso()
        conn2 = get_connection()
        conn2.execute(
            "UPDATE slide_decks SET title=?, slides_json=?, updated_at=? WHERE id=?",
            (title, slides_json, now, deck_id),
        )
        # FTS sync — need tags
        row2 = conn2.execute("SELECT tags FROM slide_decks WHERE id=?", (deck_id,)).fetchone()
        tags = row2["tags"] if row2 else None
        _fts_sync_deck(conn2, deck_id, title, slides, tags)
        conn2.commit()
        conn2.close()
        count += 1
    return count


# ── Search ──────────────────────────────────────────────────────────────────

def search_decks(query: str, limit: int = 20) -> list[dict]:
    """
    FTS5 search over title/slide_text/tags with porter stemming.
    Ranking: FTS rank (title implicitly boosted via separate column) + fallback ordering.
    Returns decks ordered by relevance; each deck includes 'rank' if available.

    Relevance intent: title match > slide_text match > tags match.
    Achieved by querying with column filter when query hits title, else default FTS rank
    already favors rarer terms. For explicit boost we use bm25() weighting if available.
    """
    if not query or not query.strip():
        return []

    init_db()
    conn = get_connection()

    # Use FTS5 query as-is (porter handles stemming). Escape double quotes.
    q = query.strip().replace('"', '""')

    # Try bm25-weighted ranking with column weights: title 3.0, slide_text 1.0, tags 0.5
    # FTS5 bm25(table, weight, weight, ...) — available in SQLite >=3.38
    try:
        # Weight order matches CREATE VIRTUAL TABLE column order: title, slide_text, tags
        rows = conn.execute(
            """
            SELECT d.*, rank
            FROM slide_decks d
            JOIN (
                SELECT rowid, rank
                FROM slides_fts
                WHERE slides_fts MATCH ?
                ORDER BY bm25(slides_fts, 3.0, 1.0, 0.5)
                LIMIT ?
            ) f ON f.rowid = d.id
            ORDER BY f.rank
            """,
            (q, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # Fallback: plain rank
        try:
            rows = conn.execute(
                """
                SELECT d.*, f.rank as rank
                FROM slide_decks d
                JOIN (
                    SELECT rowid, rank
                    FROM slides_fts
                    WHERE slides_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                ) f ON f.rowid = d.id
                """,
                (q, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS table missing or query syntax error — return empty
            conn.close()
            return []

    conn.close()
    results = []
    for r in rows:
        d = _row_to_deck(r)
        # sqlite returns rank negative for bm25; keep as is for sorting but expose
        try:
            d["rank"] = r["rank"]
        except Exception:
            pass
        results.append(d)
    return results
