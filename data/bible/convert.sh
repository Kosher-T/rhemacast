#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# convert.sh — Bible source file conversion pipeline
#
# Converts Bible source files (.xml, .xmm, .json, .csv) into the unified
# JSON format used by RhemaCast, then loads them into the SQLite database
# with version fingerprinting.
#
# Supported input formats:
#   - OSIS XML      (.xml)   — e.g. KJV from Zefania/OSIS projects
#   - Zefania XML   (.xml)   — e.g. ESV, NLT (XMLBIBLE root element)
#   - XMM XML       (.xmm)   — e.g. NKJV, NIV (bible > b > c > v)
#   - Amplified XML (.xml)   — bible > testament > book > chapter > verse
#   - JSON          (.json)  — Already in target format (copied directly)
#   - CSV           (.csv)   — Columns: version,book,chapter,verse,text
#
# Usage:
#   ./data/bible/convert.sh                        # Convert all from ~/Downloads
#   ./data/bible/convert.sh /path/to/sources/      # Convert all from a directory
#   ./data/bible/convert.sh /path/to/file.xml      # Convert a single file
#   ./data/bible/convert.sh --db-only              # Skip conversion, rebuild DB only
#
# LICENSING NOTE:
#   KJV is public domain. All other translations (NKJV, NIV, ESV, NLT, AMP)
#   are copyrighted. Users must supply their own legally obtained source files.
#   Do NOT distribute copyrighted Bible texts with this project.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"
JSON_DIR="$SCRIPT_DIR/json"
DB_PATH="$SCRIPT_DIR/bible.db"

# ─── Color output ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ─── Verify Python venv ─────────────────────────────────────────────────────
if [ ! -f "$VENV_PYTHON" ]; then
    err "Python venv not found at $VENV_PYTHON"
    err "Run: python3 -m venv venv && venv/bin/pip install lxml"
    exit 1
fi

# ─── Parse arguments ────────────────────────────────────────────────────────
DB_ONLY=false
SOURCE_PATH=""

for arg in "$@"; do
    case "$arg" in
        --db-only)
            DB_ONLY=true
            ;;
        --help|-h)
            head -28 "${BASH_SOURCE[0]}" | tail -25
            exit 0
            ;;
        *)
            SOURCE_PATH="$arg"
            ;;
    esac
done

# ─── Step 1: Convert XML/XMM/CSV → JSON ─────────────────────────────────────
if [ "$DB_ONLY" = false ]; then
    info "Step 1: Converting source files to JSON..."
    echo ""

    # Handle CSV files if present (convert to JSON inline)
    if [ -n "$SOURCE_PATH" ] && [ -d "$SOURCE_PATH" ]; then
        for csv_file in "$SOURCE_PATH"/*.csv; do
            [ -f "$csv_file" ] || continue
            info "Converting CSV: $csv_file"
            "$VENV_PYTHON" -c "
import csv, json, os, sys

csv_path = sys.argv[1]
out_dir = sys.argv[2]

# Read CSV: version,book,chapter,verse,text
versions = {}
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        ver = row.get('version', os.path.splitext(os.path.basename(csv_path))[0]).upper()
        book = row['book']
        chap = str(row['chapter'])
        verse = str(row['verse'])
        text = row['text'].strip()
        
        if ver not in versions:
            versions[ver] = {'translation': ver, 'books': {}}
        books = versions[ver]['books']
        if book not in books:
            books[book] = {}
        if chap not in books[book]:
            books[book][chap] = {}
        books[book][chap][verse] = text

for ver, data in versions.items():
    out_path = os.path.join(out_dir, f'{ver.lower()}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    total_v = sum(len(v) for c in data['books'].values() for v in c.values())
    print(f'  [{ver}] {total_v} verses → {out_path}')
" "$csv_file" "$JSON_DIR"
        done
    fi

    # Handle JSON files if present (copy directly if not already in json/)
    if [ -n "$SOURCE_PATH" ] && [ -d "$SOURCE_PATH" ]; then
        for json_file in "$SOURCE_PATH"/*.json; do
            [ -f "$json_file" ] || continue
            dest="$JSON_DIR/$(basename "$json_file")"
            if [ "$(realpath "$json_file")" != "$(realpath "$dest" 2>/dev/null || echo "")" ]; then
                info "Copying JSON: $json_file → $dest"
                cp "$json_file" "$dest"
            fi
        done
    fi

    # Handle XML/XMM files via the Python converter
    if [ -n "$SOURCE_PATH" ]; then
        "$VENV_PYTHON" "$SCRIPT_DIR/bible_to_json.py" "$SOURCE_PATH"
    else
        "$VENV_PYTHON" "$SCRIPT_DIR/bible_to_json.py"
    fi

    echo ""
    ok "JSON conversion complete."
else
    info "Skipping conversion (--db-only)."
fi

# ─── Step 2: Build SQLite database with fingerprinting ───────────────────────
echo ""
info "Step 2: Building SQLite database with version fingerprinting..."
"$VENV_PYTHON" "$SCRIPT_DIR/build_db.py" "$JSON_DIR" "$DB_PATH"

echo ""
ok "Pipeline complete."
info "Database: $DB_PATH"
info "JSON files: $JSON_DIR/"
