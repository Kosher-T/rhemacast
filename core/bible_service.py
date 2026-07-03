"""
core/bible_service.py

Data access layer for the Bible browser panel.
Queries bible.db (SQLite) for chapter/verse lookups and natural language search.
"""

import csv
import os
import pickle
import shutil
import sqlite3
import logging
import sys
import concurrent.futures
import numpy as np
from typing import List, Dict, Optional

from core.text_utils import tokenize

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_BIBLE_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "bible", "bible.db")

_INDEXES_DIR = os.path.join(_PROJECT_ROOT, "data", "indexes")

_JSON_DIR = os.path.join(_PROJECT_ROOT, "data", "bible", "json")

# Default translations (fallback if bible.db query fails)
_DEFAULT_TRANSLATIONS = ["AMP", "ESV", "KJV", "NIV", "NKJV", "NLT"]

# Lazy-loaded per-version BM25 caches: {version: (bm25_index, verse_lookup)}
_bm25_cache: Dict[str, tuple] = {}


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


def get_all_verses(version: str) -> List[Dict]:
    """
    Retrieve the entire bible for a given translation in canonical order.
    Returns a list of dicts with keys: book, chapter, verse, text.
    """
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT book, chapter, verse_num, text FROM verses "
            "WHERE version = ? "
            "ORDER BY id ASC",
            (version.upper(),)
        )
        results = [
            {"book": row["book"], "chapter": row["chapter"],
             "verse": row["verse_num"], "text": row["text"]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Failed to query all verses: {e}")
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


def get_verse_count(version: str, book: str, chapter: int) -> int:
    """Return the number of verses in a chapter."""
    try:
        conn = _get_connection()
        cursor = conn.execute(
            "SELECT MAX(verse_num) as max_v FROM verses "
            "WHERE version = ? AND book = ? AND chapter = ?",
            (version.upper(), book, chapter)
        )
        row = cursor.fetchone()
        conn.close()
        return row["max_v"] if row and row["max_v"] else 0
    except Exception as e:
        logger.error(f"Failed to query verse count: {e}")
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


# ─── BM25 + Hybrid Search ────────────────────────────────────────────────────


def _load_bm25_index(version: str):
    """Lazy-load a per-version BM25 index from disk. Returns (bm25, verse_lookup) or (None, None)."""
    version = version.upper()
    if version in _bm25_cache:
        return _bm25_cache[version]

    bm25_path = os.path.join(_INDEXES_DIR, f"bm25_{version}.pkl")
    lookup_path = os.path.join(_INDEXES_DIR, f"verse_lookup_{version}.pkl")

    if not os.path.exists(bm25_path) or not os.path.exists(lookup_path):
        logger.warning(f"Per-version BM25 index not found for {version} — run build_bm25.py")
        return None, None

    try:
        with open(bm25_path, "rb") as f:
            bm25 = pickle.load(f)
        with open(lookup_path, "rb") as f:
            verse_lookup = pickle.load(f)
        _bm25_cache[version] = (bm25, verse_lookup)
        logger.info(f"Loaded BM25 index for {version}: {len(verse_lookup):,} verses")
        return bm25, verse_lookup
    except Exception as e:
        logger.error(f"Failed to load BM25 index for {version}: {e}")
        return None, None


def bm25_search(query: str, version: str = "KJV", limit: int = 20) -> List[Dict]:
    """Search a per-version BM25 index with stemmed tokenization.

    Returns list[dict] with keys: book, chapter, verse, text.
    """
    bm25, verse_lookup = _load_bm25_index(version)
    if not bm25 or not verse_lookup:
        return []

    tokens = tokenize(query)
    if not tokens:
        return []

    scores = bm25.get_scores(tokens)
    top_indices = np.argsort(scores)[::-1][:limit]

    results = []
    for idx in top_indices:
        _ver, book, chapter, verse_num, text = verse_lookup[idx]
        if scores[idx] <= 0:
            break
        results.append({"book": book, "chapter": chapter, "verse": verse_num, "text": text})
    return results


def hybrid_search(query: str, version: str = "KJV", limit: int = 20) -> List[Dict]:
    """Run FTS5 and BM25 in parallel, fuse with RRF.

    Returns fused results sorted by confidence, limited to *limit*.
    """
    if not query.strip():
        return []

    word_count = len(query.split())

    # Run both searches in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fts_future = pool.submit(search_verses_text, query, version, limit)
        bm25_future = pool.submit(bm25_search, query, version, limit)
        fts_results = fts_future.result()
        bm25_results = bm25_future.result()

    # If BM25 returned nothing (index missing), fall back to FTS5 only
    if not bm25_results:
        return fts_results

    # Convert to 7-tuple format expected by rrf_fuse
    fts_tuples = [
        (i + 1, version, r["book"], r["chapter"], r["verse"], 0.0, r["text"])
        for i, r in enumerate(fts_results)
    ]
    bm25_tuples = [
        (i + 1, version, r["book"], r["chapter"], r["verse"], 0.0, r["text"])
        for i, r in enumerate(bm25_results)
    ]

    # Lazy import to avoid pulling in model_manager at module load time
    from core.search_engine import rrf_fuse
    fused = rrf_fuse(bm25_tuples, fts_tuples, word_count=word_count)

    # rrf_fuse returns dicts with confidence, book, chapter, verse_num, text, etc.
    # Trim to limit and return in the standard dict format
    results = []
    for r in fused[:limit]:
        results.append({
            "book": r["book"],
            "chapter": r["chapter"],
            "verse": r["verse_num"],
            "text": r["text"],
        })
    return results


# ─── Translation Import ──────────────────────────────────────────────────────


def refresh_available_translations() -> List[str]:
    """Re-query bible.db and update the module-level AVAILABLE_TRANSLATIONS."""
    global AVAILABLE_TRANSLATIONS
    AVAILABLE_TRANSLATIONS = get_available_translations()
    return AVAILABLE_TRANSLATIONS


def import_translation_file(filepath: str) -> str:
    """Import a Bible source file into the app.

    Steps:
      1. Convert to JSON (XML/XMM via bible_to_json, CSV inline, JSON copied)
      2. Load JSON into bible.db
      3. Rebuild FTS index

    Returns the translation abbreviation (e.g. "NKJV").
    Raises on any failure.
    """
    ext = os.path.splitext(filepath)[1].lower()
    os.makedirs(_JSON_DIR, exist_ok=True)

    if ext in (".xml", ".xmm"):
        json_path = _import_xml(filepath)
    elif ext == ".csv":
        json_path = _import_csv(filepath)
    elif ext == ".json":
        json_path = _import_json(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # Load into SQLite
    version = _load_into_db(json_path)

    # Rebuild BM25 cache for this version (invalidate so it reloads next search)
    _bm25_cache.pop(version, None)

    # Build BM25 index for just this version (fast, <1s)
    _build_bm25_for_version(version)

    logger.info(f"Imported translation '{version}' from {filepath}")
    return version


def _import_xml(filepath: str) -> str:
    """Convert XML/XMM to JSON via bible_to_json. Returns JSON path."""
    # Add data/bible to sys.path so we can import bible_to_json
    bible_dir = os.path.join(_PROJECT_ROOT, "data", "bible")
    if bible_dir not in sys.path:
        sys.path.insert(0, bible_dir)

    from bible_to_json import convert_file
    return convert_file(filepath, _JSON_DIR)


def _import_csv(filepath: str) -> str:
    """Convert CSV to JSON. Returns JSON path."""
    versions: dict = {}
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ver = row.get("version", os.path.splitext(os.path.basename(filepath))[0]).upper()
            book = row["book"]
            chap = str(row["chapter"])
            verse = str(row["verse"])
            text = row["text"].strip()

            if ver not in versions:
                versions[ver] = {"translation": ver, "books": {}}
            books = versions[ver]["books"]
            if book not in books:
                books[book] = {}
            if chap not in books[book]:
                books[book][chap] = {}
            books[book][chap][verse] = text

    import json
    out_paths = []
    for ver, data in versions.items():
        out_path = os.path.join(_JSON_DIR, f"{ver.lower()}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        out_paths.append(out_path)
        logger.info(f"CSV → JSON: [{ver}] {out_path}")

    if not out_paths:
        raise ValueError("CSV file contained no valid verse rows")
    return out_paths[0]


def _import_json(filepath: str) -> str:
    """Copy a JSON file into the json directory. Returns destination path."""
    import json as _json

    # Validate it's a Bible JSON
    with open(filepath, "r", encoding="utf-8") as f:
        data = _json.load(f)
    if "translation" not in data or "books" not in data:
        raise ValueError("Invalid Bible JSON: missing 'translation' or 'books' key")

    ver = data["translation"]
    dest = os.path.join(_JSON_DIR, f"{ver.lower()}.json")
    if os.path.abspath(filepath) != os.path.abspath(dest):
        shutil.copy2(filepath, dest)
        logger.info(f"Copied JSON: {filepath} → {dest}")
    return dest


def _load_into_db(json_path: str) -> str:
    """Load a single JSON file into bible.db. Returns version string."""
    import json

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    version = data["translation"]

    conn = sqlite3.connect(_BIBLE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")

    # Create schema if needed
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS verses (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            version    TEXT    NOT NULL,
            book       TEXT    NOT NULL,
            chapter    INTEGER NOT NULL,
            verse_num  INTEGER NOT NULL,
            text       TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_fingerprints (
            version     TEXT PRIMARY KEY,
            sha256      TEXT    NOT NULL,
            filename    TEXT    NOT NULL,
            verse_count INTEGER NOT NULL,
            built_at    TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_verses_lookup
            ON verses(version, book, chapter, verse_num);
        CREATE INDEX IF NOT EXISTS idx_verses_version
            ON verses(version);
        CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
            text,
            content='verses',
            content_rowid='id'
        );
    """)

    # Delete existing rows for this version (idempotent)
    conn.execute("DELETE FROM verses WHERE version = ?", (version,))

    # Batch insert all verses
    rows = []
    books = data["books"]
    for book_name, chapters in books.items():
        for chap_num, verses in chapters.items():
            for verse_num, text in verses.items():
                rows.append((version, book_name, int(chap_num), int(verse_num), text.strip()))

    conn.executemany(
        "INSERT INTO verses (version, book, chapter, verse_num, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )

    # Record fingerprint
    import hashlib
    from datetime import datetime, timezone
    sha = hashlib.sha256()
    with open(json_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO source_fingerprints
           (version, sha256, filename, verse_count, built_at)
           VALUES (?, ?, ?, ?, ?)""",
        (version, sha.hexdigest(), os.path.basename(json_path), len(rows), now),
    )

    # Rebuild FTS index
    conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()

    logger.info(f"Loaded [{version}] {len(rows):,} verses into {_BIBLE_DB_PATH}")
    return version


def _build_bm25_for_version(version: str):
    """Build BM25 index for a single translation version.

    Reads verses from bible.db, tokenizes, builds BM25Okapi, and writes
    data/indexes/bm25_{VERSION}.pkl + verse_lookup_{VERSION}.pkl.
    Fast (<1s) since it only processes one version.
    """
    import sqlite3
    import pickle
    import time
    from collections import defaultdict
    from rank_bm25 import BM25Okapi
    from core.text_utils import tokenize

    t0 = time.perf_counter()

    conn = sqlite3.connect(str(_BIBLE_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT version, book, chapter, verse_num, text FROM verses "
        "WHERE version = ? ORDER BY book, chapter, verse_num",
        (version,),
    ).fetchall()
    conn.close()

    if not rows:
        logger.warning(f"No verses found for version '{version}', skipping BM25 build")
        return

    verses = [dict(r) for r in rows]

    # Build verse lookup and tokenized corpus
    v_lookup = [
        (v["version"], v["book"], v["chapter"], v["verse_num"], v["text"])
        for v in verses
    ]
    v_tokenized = [tokenize(v["text"]) for v in verses]
    v_bm25 = BM25Okapi(v_tokenized)

    # Write pickle files
    output_dir = os.path.join(_PROJECT_ROOT, "data", "indexes")
    os.makedirs(output_dir, exist_ok=True)

    bm25_path = os.path.join(output_dir, f"bm25_{version}.pkl")
    lookup_path = os.path.join(output_dir, f"verse_lookup_{version}.pkl")

    with open(bm25_path, "wb") as f:
        pickle.dump(v_bm25, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(lookup_path, "wb") as f:
        pickle.dump(v_lookup, f, protocol=pickle.HIGHEST_PROTOCOL)

    elapsed = time.perf_counter() - t0
    bm25_mb = os.path.getsize(bm25_path) / (1024 * 1024)
    lookup_mb = os.path.getsize(lookup_path) / (1024 * 1024)
    logger.info(f"Built BM25 for [{version}]: {len(rows):,} verses, "
                f"{bm25_mb + lookup_mb:.2f} MB, {elapsed:.2f}s")


# ─── Translation Display Names ───────────────────────────────────────────────

_DISPLAY_NAMES_KEY = "bible.translation_display_names"

# Module-level cache: {canonical: display_name}
_display_names_cache: Dict[str, str] = {}
_display_names_loaded = False


def _load_display_names():
    """Load display names from settings into the cache."""
    global _display_names_cache, _display_names_loaded
    if _display_names_loaded:
        return
    from core.database import get_setting
    raw = get_setting(_DISPLAY_NAMES_KEY, "{}")
    try:
        import json as _json
        _display_names_cache = _json.loads(raw)
    except (ValueError, TypeError):
        _display_names_cache = {}
    _display_names_loaded = True


def get_display_name(canonical: str) -> str:
    """Return the display name for a translation, or canonical if no rename."""
    _load_display_names()
    return _display_names_cache.get(canonical, canonical)


def set_display_name(canonical: str, display: str):
    """Set a display name mapping. Updates settings + module cache."""
    global _display_names_cache
    _load_display_names()
    if display and display != canonical:
        _display_names_cache[canonical] = display
    else:
        _display_names_cache.pop(canonical, None)
    from core.database import set_setting
    import json as _json
    set_setting(_DISPLAY_NAMES_KEY, _json.dumps(_display_names_cache))


def get_all_display_names() -> Dict[str, str]:
    """Return the full canonical→display mapping."""
    _load_display_names()
    return dict(_display_names_cache)


# ─── Translation Order ───────────────────────────────────────────────────────

_ORDER_KEY = "bible.translation_order"

_order_cache: list[str] | None = None


def get_translation_order() -> List[str]:
    """Return the saved translation order, or empty list if none saved."""
    global _order_cache
    if _order_cache is not None:
        return list(_order_cache)
    from core.database import get_setting
    raw = get_setting(_ORDER_KEY, "[]")
    try:
        import json as _json
        _order_cache = _json.loads(raw)
    except (ValueError, TypeError):
        _order_cache = []
    return list(_order_cache)


def set_translation_order(order: List[str]):
    """Persist the translation order to settings."""
    global _order_cache
    _order_cache = list(order)
    from core.database import set_setting
    import json as _json
    set_setting(_ORDER_KEY, _json.dumps(order))
