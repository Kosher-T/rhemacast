#!/usr/bin/env python3
"""
verify_db.py — Runtime Bible database integrity verification.

Checks that the loaded SQLite database matches the current source JSON files.
If mismatched, either warns or triggers an automatic rebuild.

Usage (standalone):
  python data/bible/verify_db.py                     # verify default paths
  python data/bible/verify_db.py --rebuild            # auto-rebuild if stale
  python data/bible/verify_db.py --json-dir DIR --db PATH  # custom paths

Usage (as module):
  from data.bible.verify_db import check_bible_db
  status = check_bible_db()  # returns 'ok', 'stale', or 'missing'
"""

import os
import sys

# Allow importing sibling modules when run as script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from build_db import verify_fingerprints, build_database


DEFAULT_JSON_DIR = os.path.join(SCRIPT_DIR, "json")
DEFAULT_DB_PATH = os.path.join(SCRIPT_DIR, "bible.db")


def check_bible_db(
    json_dir: str = DEFAULT_JSON_DIR,
    db_path: str = DEFAULT_DB_PATH,
    auto_rebuild: bool = False,
    quiet: bool = False,
) -> str:
    """Check Bible database integrity against source files.
    
    Returns:
      'ok'       — All versions current, database is valid
      'stale'    — One or more versions have changed source files
      'missing'  — Database doesn't exist or is missing versions
      'rebuilt'  — Database was stale but has been auto-rebuilt
    
    Args:
      json_dir:     Path to directory containing Bible JSON files
      db_path:      Path to SQLite database
      auto_rebuild: If True, automatically rebuild stale/missing databases
      quiet:        If True, suppress print output
    """
    def log(msg):
        if not quiet:
            print(msg)

    # Check if DB exists at all
    if not os.path.exists(db_path):
        log(f"[WARN] Bible database not found: {db_path}")
        if auto_rebuild:
            log("[INFO] Auto-rebuilding database...")
            build_database(json_dir, db_path)
            return "rebuilt"
        return "missing"

    # Check if JSON dir exists
    if not os.path.isdir(json_dir):
        log(f"[WARN] JSON source directory not found: {json_dir}")
        return "missing"

    # Verify fingerprints
    status = verify_fingerprints(json_dir, db_path)

    if not status:
        log("[WARN] No fingerprint data found in database.")
        if auto_rebuild:
            log("[INFO] Auto-rebuilding database...")
            build_database(json_dir, db_path)
            return "rebuilt"
        return "missing"

    stale = [v for v, s in status.items() if s == "stale"]
    missing = [v for v, s in status.items() if s == "missing"]
    orphaned = [v for v, s in status.items() if s == "orphaned"]
    current = [v for v, s in status.items() if s == "current"]

    if stale or missing:
        if stale:
            log(f"[WARN] Stale versions (source changed): {', '.join(stale)}")
        if missing:
            log(f"[WARN] Missing versions (not in DB): {', '.join(missing)}")
        if orphaned:
            log(f"[INFO] Orphaned versions (no source): {', '.join(orphaned)}")

        if auto_rebuild:
            log("[INFO] Auto-rebuilding database...")
            build_database(json_dir, db_path)
            return "rebuilt"
        return "stale"

    if orphaned:
        log(f"[INFO] Orphaned versions in DB (source files removed): {', '.join(orphaned)}")

    log(f"[OK] Bible database verified. {len(current)} versions current.")
    return "ok"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Verify Bible database integrity")
    parser.add_argument("--json-dir", default=DEFAULT_JSON_DIR,
                        help=f"Path to JSON source directory (default: {DEFAULT_JSON_DIR})")
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--rebuild", action="store_true",
                        help="Auto-rebuild if database is stale or missing")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress output (exit code only)")
    args = parser.parse_args()

    result = check_bible_db(
        json_dir=args.json_dir,
        db_path=args.db,
        auto_rebuild=args.rebuild,
        quiet=args.quiet,
    )

    # Exit codes: 0 = ok/rebuilt, 1 = stale, 2 = missing
    exit_codes = {"ok": 0, "rebuilt": 0, "stale": 1, "missing": 2}
    sys.exit(exit_codes.get(result, 1))


if __name__ == "__main__":
    main()
