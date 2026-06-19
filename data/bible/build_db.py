#!/usr/bin/env python3
"""
build_db.py — Load Bible JSON files into SQLite with version fingerprinting.

Creates/rebuilds the Bible SQLite database from JSON files produced by
bible_to_json.py. Implements version fingerprinting so the runtime can
detect stale indexes and trigger rebuilds.

Schema:
  verses(id INTEGER PRIMARY KEY, version TEXT, book TEXT, chapter INTEGER,
         verse_num INTEGER, text TEXT)
  
  source_fingerprints(version TEXT PRIMARY KEY, sha256 TEXT, filename TEXT,
                      verse_count INTEGER, built_at TEXT)

Usage:
  python build_db.py <json_dir> <db_path>
  python build_db.py data/bible/json data/bible/bible.db
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone


# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
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

-- Composite index for the most common lookup pattern: version + book + chapter
CREATE INDEX IF NOT EXISTS idx_verses_lookup
    ON verses(version, book, chapter, verse_num);

-- Index for version-only filtering (e.g. "get all KJV verses")
CREATE INDEX IF NOT EXISTS idx_verses_version
    ON verses(version);

-- Full-text search virtual table for fast text matching
-- (used by BM25 and keyword search at runtime)
CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    text,
    content='verses',
    content_rowid='id'
);
"""

REBUILD_FTS_SQL = """
INSERT INTO verses_fts(verses_fts) VALUES('rebuild');
"""


def file_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json_to_db(json_path: str, conn: sqlite3.Connection) -> tuple[str, int]:
    """Load a single Bible JSON file into the database.
    
    Returns (version, verse_count).
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    version = data["translation"]
    books = data["books"]

    # Delete existing rows for this version (idempotent rebuild)
    conn.execute("DELETE FROM verses WHERE version = ?", (version,))

    # Batch insert all verses
    rows = []
    for book_name, chapters in books.items():
        for chap_num, verses in chapters.items():
            for verse_num, text in verses.items():
                rows.append((version, book_name, int(chap_num), int(verse_num), text.strip()))

    conn.executemany(
        "INSERT INTO verses (version, book, chapter, verse_num, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )

    # Record fingerprint
    sha = file_sha256(json_path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO source_fingerprints
           (version, sha256, filename, verse_count, built_at)
           VALUES (?, ?, ?, ?, ?)""",
        (version, sha, os.path.basename(json_path), len(rows), now),
    )

    return version, len(rows)


def verify_fingerprints(json_dir: str, db_path: str) -> dict:
    """Check if the database is up-to-date with source JSON files.
    
    Returns a dict of {version: status} where status is one of:
      'current'  — DB matches source file
      'stale'    — DB hash doesn't match source file (needs rebuild)
      'missing'  — Source file exists but version not in DB
      'orphaned' — Version in DB but source file is gone
    """
    if not os.path.exists(db_path):
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get existing fingerprints
    db_versions = {}
    try:
        for row in conn.execute("SELECT * FROM source_fingerprints"):
            db_versions[row["version"]] = dict(row)
    except sqlite3.OperationalError:
        conn.close()
        return {}

    # Get current JSON files
    json_files = {}
    for f in os.listdir(json_dir):
        if f.endswith(".json"):
            path = os.path.join(json_dir, f)
            # Quick read to get version name
            with open(path, "r", encoding="utf-8") as fh:
                # Only read enough to get the translation field
                raw = fh.read(200)
                import re
                m = re.search(r'"translation"\s*:\s*"([^"]+)"', raw)
                if m:
                    ver = m.group(1)
                    json_files[ver] = path

    result = {}

    # Check each JSON file against DB
    for ver, path in json_files.items():
        if ver not in db_versions:
            result[ver] = "missing"
        else:
            current_hash = file_sha256(path)
            if current_hash == db_versions[ver]["sha256"]:
                result[ver] = "current"
            else:
                result[ver] = "stale"

    # Check for orphaned versions in DB
    for ver in db_versions:
        if ver not in json_files:
            result[ver] = "orphaned"

    conn.close()
    return result


def build_database(json_dir: str, db_path: str):
    """Build or rebuild the Bible SQLite database from JSON files."""
    t0 = time.perf_counter()

    json_files = sorted(
        os.path.join(json_dir, f)
        for f in os.listdir(json_dir)
        if f.endswith(".json")
    )

    if not json_files:
        print(f"[ERROR] No JSON files found in {json_dir}")
        sys.exit(1)

    # Check what needs rebuilding
    status = verify_fingerprints(json_dir, db_path)
    needs_rebuild = {
        v for v, s in status.items() if s in ("stale", "missing")
    }
    current = {v for v, s in status.items() if s == "current"}

    if current and not needs_rebuild:
        print(f"  Database is up-to-date. All {len(current)} versions current.")
        print(f"  Versions: {', '.join(sorted(current))}")
        return

    if needs_rebuild:
        print(f"  Versions needing rebuild: {', '.join(sorted(needs_rebuild))}")
    if current:
        print(f"  Versions already current: {', '.join(sorted(current))}")

    # Connect (or create) database
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache

    # Create schema
    conn.executescript(SCHEMA_SQL)

    total_rows = 0
    versions_loaded = []

    for json_path in json_files:
        # Quick version peek
        with open(json_path, "r", encoding="utf-8") as fh:
            raw = fh.read(200)
            import re
            m = re.search(r'"translation"\s*:\s*"([^"]+)"', raw)
            ver = m.group(1) if m else os.path.splitext(os.path.basename(json_path))[0].upper()

        # Skip if already current
        if ver in current:
            continue

        version, count = load_json_to_db(json_path, conn)
        total_rows += count
        versions_loaded.append((version, count))
        print(f"  [{version}] Loaded {count:,} verses from {os.path.basename(json_path)}")

    # Rebuild FTS index
    if versions_loaded:
        print("  Rebuilding FTS index...")
        conn.executescript(REBUILD_FTS_SQL)

    conn.commit()

    # Report final stats
    total_in_db = conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    conn.close()

    elapsed = time.perf_counter() - t0
    print(f"\n  Database: {db_path}")
    print(f"  Total rows: {total_in_db:,}")
    print(f"  Size: {db_size_mb:.2f} MB")
    print(f"  Time: {elapsed:.3f}s")

    # Print fingerprint summary
    print("\n  Fingerprints:")
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    for row in conn2.execute("SELECT * FROM source_fingerprints ORDER BY version"):
        print(f"    {row['version']:>5s}  {row['sha256'][:16]}…  {row['verse_count']:,} verses  ({row['built_at']})")
    conn2.close()


def main():
    if len(sys.argv) < 3:
        print("Usage: python build_db.py <json_dir> <db_path>")
        print("  json_dir: Directory containing Bible JSON files")
        print("  db_path:  Path to output SQLite database")
        sys.exit(1)

    json_dir = sys.argv[1]
    db_path = sys.argv[2]

    if not os.path.isdir(json_dir):
        print(f"[ERROR] JSON directory not found: {json_dir}")
        sys.exit(1)

    build_database(json_dir, db_path)


if __name__ == "__main__":
    main()
