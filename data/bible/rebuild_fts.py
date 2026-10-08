#!/usr/bin/env python3
"""Rebuild the FTS5 verse index for the operator's chosen translations.

The index is the whole ranking story for this lane: a Porter-stemmed FTS5
table scored by SQLite's own bm25. It deliberately does NOT mirror the
whole `verses` table — it holds only the translations the operator picked
in Settings, because a term's postings are scanned in full before the
`version` filter throws most of them away. Indexing all 18 translations
when six were chosen means every query scans three times the postings it
needs and discards two thirds of them.

That also means this is a REBUILD whenever the selection changes, not a
one-off: there is no incremental path, because adding a translation means
adding a whole translation.

    python data/bible/rebuild_fts.py [--db PATH] [--check] [--force]
"""
import argparse
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_DB = os.path.join(HERE, "bible.db")

# The selection lives with the app, so this script needs the project root
# importable before it can ask `core` what the operator chose.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Must stay in step with the DDL in build_db.py and bible_service.py.
# NOTE: no `content=` option — an external-content FTS5 table mirrors its
# whole source table and cannot be restricted to a subset of rows.
FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    text,
    tokenize='porter unicode61 remove_diacritics 2'
);
"""


def chosen_translations():
    """The operator's selection — the same source the query path reads, so
    index and search can never disagree about what is searchable."""
    try:
        from core.bible_service import fts_translations
        return list(fts_translations())
    except Exception as e:                      # pragma: no cover
        print(f"warning: falling back to defaults ({e})", file=sys.stderr)
        from core.constants import FTS_TRANSLATIONS
        return list(FTS_TRANSLATIONS)


def _table_exists(conn):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='verses_fts'").fetchone() \
        is not None


def tokenizer_of(conn):
    """The tokenize= clause of the live verses_fts table ('' if absent)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='verses_fts'").fetchone()
    if not row or not row[0]:
        return ""
    for part in row[0].split(","):
        if "tokenize" in part:
            return part.strip().strip("()").strip()
    return ""


def _placeholders(n):
    return ",".join("?" for _ in range(n))


def indexed_versions(conn):
    """Which translations actually have rows in the index."""
    if not _table_exists(conn):
        return set()
    rows = conn.execute(
        "SELECT DISTINCT v.version FROM verses_fts fts "
        "JOIN verses v ON v.id = fts.rowid").fetchall()
    return {r[0] for r in rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB, help="path to bible.db")
    ap.add_argument("--check", action="store_true",
                    help="report status and exit without rebuilding")
    ap.add_argument("--force", action="store_true",
                    help="rebuild even if the index already matches")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print(f"ERROR: no database at {args.db}", file=sys.stderr)
        return 1

    wanted = chosen_translations()
    conn = sqlite3.connect(args.db)
    try:
        installed = {r[0] for r in conn.execute(
            "SELECT DISTINCT version FROM verses")}
        missing = [t for t in wanted if t not in installed]
        if missing:
            print(f"ERROR: chosen translation(s) not installed: "
                  f"{', '.join(missing)}", file=sys.stderr)
            return 1
        expected = conn.execute(
            f"SELECT COUNT(*) FROM verses WHERE version IN "
            f"({_placeholders(len(wanted))})", tuple(wanted)).fetchone()[0]

        if args.check:
            have = indexed_versions(conn)
            ok = (bool(have) and have == set(wanted)
                  and "porter" in tokenizer_of(conn))
            print(f"chosen    : {', '.join(wanted)}")
            print(f"indexed   : {', '.join(sorted(have)) or '(nothing)'}")
            print(f"rows      : "
                  f"{conn.execute('SELECT COUNT(*) FROM verses_fts').fetchone()[0] if have else 0:,}"
                  f" (expected {expected:,})")
            print(f"tokenizer : {tokenizer_of(conn) or '(none)'}")
            print("status    : " + ("OK" if ok else "NEEDS REBUILD"))
            return 0 if ok else 1

        have = indexed_versions(conn)
        in_sync = (have == set(wanted)
                   and "porter" in tokenizer_of(conn)
                   and _table_exists(conn)
                   and conn.execute(
                       "SELECT COUNT(*) FROM verses_fts").fetchone()[0]
                   == expected)
        if in_sync and not args.force:
            print(f"already matches: {', '.join(wanted)}")
            return 0

        t0 = time.time()
        # A stale table can hold a different tokenizer or a different
        # translation set, and neither can be corrected in place — the
        # whole table goes.
        conn.execute("DROP TABLE IF EXISTS verses_fts")
        conn.executescript(FTS_DDL)
        conn.execute(
            f"INSERT INTO verses_fts(rowid, text) "
            f"SELECT id, text FROM verses WHERE version IN "
            f"({_placeholders(len(wanted))})", tuple(wanted))
        conn.commit()

        got = conn.execute("SELECT COUNT(*) FROM verses_fts").fetchone()[0]
        print(f"indexed {got:,} verses from {len(wanted)} translation(s): "
              f"{', '.join(wanted)}")
        print(f"tokenizer: {tokenizer_of(conn)}")
        print(f"built in {time.time() - t0:.1f}s")
        if got != expected:
            print(f"ERROR: indexed {got} but expected {expected}",
                  file=sys.stderr)
            return 1
        return 0
    except sqlite3.Error as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())