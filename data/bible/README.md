# Bible Data — Source Files & Licensing

## Overview

RhemaCast requires Bible text data in structured JSON format to build its searchable index. This directory contains the conversion tools and (after you run them) the generated JSON and SQLite database.

## Directory Structure

```
data/bible/
├── convert.sh          # Main pipeline script (XML/XMM/CSV/JSON → SQLite)
├── bible_to_json.py    # Python converter (XML/XMM → JSON)
├── build_db.py         # JSON → SQLite loader with fingerprinting
├── verify_db.py        # Runtime integrity checker
├── README.md           # This file
├── json/               # Generated JSON files (gitignored)
│   ├── kjv.json
│   ├── esv.json
│   └── ...
├── sources/            # Place your source XML/XMM/CSV files here
└── bible.db            # Generated SQLite database (gitignored)
```

## Supported Versions

| Version | Abbreviation | License | Source |
|---------|-------------|---------|--------|
| King James Version | KJV | **Public Domain** | [scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases) or OSIS XML |
| New King James Version | NKJV | © Thomas Nelson | User must supply |
| English Standard Version | ESV | © Crossway | User must supply |
| New International Version | NIV | © Biblica | User must supply |
| New Living Translation | NLT | © Tyndale House | User must supply |
| Amplified Bible | AMP | © The Lockman Foundation | User must supply |

## ⚠️ Licensing Notice

> **KJV is public domain and may be freely distributed.**
>
> **All other translations (NKJV, NIV, ESV, NLT, AMP) are copyrighted.**
> Users are solely responsible for compliance with copyright terms.
> You must obtain your own legally licensed copies of these texts.
> **Do NOT commit copyrighted Bible texts to version control.**
> **Do NOT distribute copyrighted Bible texts with this project.**

## Supported Input Formats

The converter accepts the following source file formats:

### 1. JSON (preferred — fastest)
Already in the target format. Place files directly in `json/`.
```json
{
  "translation": "ESV",
  "books": {
    "Genesis": {
      "1": { "1": "In the beginning...", "2": "..." }
    }
  }
}
```

### 2. OSIS XML
Standard Bible encoding format (e.g., KJV from Zefania project).
```xml
<osis>
  <osisText osisIDWork='kjv'>
    <div type='book' osisID='Gen'>
      <chapter osisID='Gen.1'>
        <verse osisID='Gen.1.1'>In the beginning...</verse>
```

### 3. Zefania XML (XMLBIBLE)
Common format for ESV, NLT, and others.
```xml
<XMLBIBLE biblename="ENGLISHESV">
  <BIBLEBOOK bnumber="1" bname="Genesis">
    <CHAPTER cnumber="1">
      <VERS vnumber="1">In the beginning...</VERS>
```

### 4. XMM XML
Compact format used by some distributions (NKJV, NIV).
```xml
<bible>
  <b n="Genesis">
    <c n="1">
      <v n="1">In the beginning...</v>
```

### 5. CSV
Simple tabular format.
```csv
version,book,chapter,verse,text
KJV,Genesis,1,1,"In the beginning God created the heaven and the earth."
```

## Quick Start

```bash
# 1. Place your source files in ~/Downloads/ (or any directory)

# 2. Run the full pipeline (convert + build DB):
./data/bible/convert.sh ~/Downloads/

# 3. Or convert from default ~/Downloads/ location:
./data/bible/convert.sh

# 4. Or rebuild the database only (if JSON files already exist):
./data/bible/convert.sh --db-only

# 5. Verify database integrity at any time:
python data/bible/verify_db.py
python data/bible/verify_db.py --rebuild  # auto-fix if stale
```

## Version Fingerprinting

Every source file is SHA-256 hashed when loaded into the database. At runtime, `verify_db.py` compares stored hashes against current JSON files to detect:

- **Stale** — Source file changed since last DB build
- **Missing** — New source file not yet in DB
- **Orphaned** — Version in DB but source file deleted
- **Current** — Everything matches

This ensures indexes built on top of the database (BM25, FAISS) stay synchronized with the underlying text data.
