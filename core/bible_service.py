"""
core/bible_service.py

Data access layer for the Bible browser panel.
Queries bible.db (SQLite) for chapter/verse lookups and natural language search.
"""

import os
import sqlite3
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

_BIBLE_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "bible", "bible.db"
)

# Default translations (fallback if bible.db query fails)
_DEFAULT_TRANSLATIONS = ["AMP", "ESV", "KJV", "NIV", "NKJV", "NLT"]


def _get_connection() -> sqlite3.Connection:
    """Returns a read-only connection to the Bible database."""
    conn = sqlite3.connect(f"file:{_BIBLE_DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_available_translations() -> List[str]:
    """Return the list of translations available in bible.db, dynamically."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT DISTINCT version FROM verses ORDER BY version ASC"
        )
        translations = [row["version"] for row in cursor.fetchall()]
        conn.close()
        return translations if translations else _DEFAULT_TRANSLATIONS
    except Exception as e:
        logger.error(f"Failed to query available translations: {e}")
        return _DEFAULT_TRANSLATIONS


# Backward-compatible: module-level constant populated lazily
AVAILABLE_TRANSLATIONS = get_available_translations()


def get_chapter(version: str, book: str, chapter: int) -> List[Dict]:
    """
    Retrieve all verses for a given book and chapter in the specified translation.
    Returns a list of dicts with keys: chapter, verse, text.
    """
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT chapter, verse_num, text FROM verses "
            "WHERE version = ? AND book = ? AND chapter = ? "
            "ORDER BY verse_num ASC",
            (version.upper(), book, chapter)
        )
        results = [
            {"chapter": row["chapter"], "verse": row["verse_num"], "text": row["text"]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Failed to query chapter: {e}")
        return []


def get_verse(version: str, book: str, chapter: int, verse: int) -> Optional[Dict]:
    """Retrieve a single verse."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT chapter, verse_num, text FROM verses "
            "WHERE version = ? AND book = ? AND chapter = ? AND verse_num = ?",
            (version.upper(), book, chapter, verse)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"chapter": row["chapter"], "verse": row["verse_num"], "text": row["text"]}
        return None
    except Exception as e:
        logger.error(f"Failed to query verse: {e}")
        return None


def get_books(version: str = "KJV") -> List[str]:
    """Return the distinct list of books for a translation, in canonical order."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT DISTINCT book FROM verses WHERE version = ? ORDER BY id ASC",
            (version.upper(),)
        )
        # Use a seen-set to preserve insertion order (canonical)
        seen = set()
        books = []
        for row in cursor.fetchall():
            b = row["book"]
            if b not in seen:
                seen.add(b)
                books.append(b)
        conn.close()
        return books
    except Exception as e:
        logger.error(f"Failed to query books: {e}")
        return []


def get_chapter_count(version: str, book: str) -> int:
    """Return the number of chapters in a book."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT MAX(chapter) as max_ch FROM verses WHERE version = ? AND book = ?",
            (version.upper(), book)
        )
        row = cursor.fetchone()
        conn.close()
        return row["max_ch"] if row and row["max_ch"] else 0
    except Exception as e:
        logger.error(f"Failed to query chapter count: {e}")
        return 0


def search_verses_text(query: str, version: str = "KJV", limit: int = 20) -> List[Dict]:
    """
    Simple FTS5 search on verse text within a specific translation.
    Falls back to LIKE query if FTS is not available.
    """
    if not query.strip():
        return []

    try:
        conn = _get_connection()
        
        # Try FTS5 first (verses_fts table exists in bible.db)
        try:
            cursor = conn.execute(
                "SELECT v.book, v.chapter, v.verse_num, v.text "
                "FROM verses_fts fts "
                "JOIN verses v ON v.rowid = fts.rowid "
                "WHERE fts.text MATCH ? AND v.version = ? "
                "ORDER BY rank "
                "LIMIT ?",
                (query, version.upper(), limit)
            )
            results = [
                {"chapter": row["chapter"], "verse": row["verse_num"],
                 "text": row["text"], "book": row["book"]}
                for row in cursor.fetchall()
            ]
            conn.close()
            return results
        except sqlite3.OperationalError:
            pass
        
        # Fallback: LIKE query
        cursor = conn.execute(
            "SELECT book, chapter, verse_num, text FROM verses "
            "WHERE version = ? AND text LIKE ? "
            "LIMIT ?",
            (version.upper(), f"%{query}%", limit)
        )
        results = [
            {"chapter": row["chapter"], "verse": row["verse_num"],
             "text": row["text"], "book": row["book"]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Failed to search verses: {e}")
        return []
