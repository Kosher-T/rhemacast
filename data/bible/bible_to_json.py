#!/usr/bin/env python3
"""
bible_to_json.py — Universal Bible XML/XMM → JSON converter.

Supports 4 XML format variants found in the wild:
  1. XMLBIBLE  (ESV, NLT)         — BIBLEBOOK[bname] > CHAPTER[cnumber] > VERS[vnumber]
  2. bible/b   (NKJV .xmm, NIV)  — b[n] > c[n] > v[n]
  3. OSIS      (KJV)              — div[osisID] > chapter[osisID] > verse[osisID]
  4. Amplified (AMP)              — testament > book[number] > chapter[number] > verse[number]

Output JSON schema (flat nested dicts for O(1) lookups):
{
  "translation": "ESV",
  "books": {
    "Genesis": {
      "1": { "1": "In the beginning...", "2": "..." }
    }
  }
}

Usage:
  python data/bible/bible_to_json.py                # process all .xml/.xmm in ~/Downloads
  python data/bible/bible_to_json.py /path/to/file.xml   # process a single file
  python data/bible/bible_to_json.py /path/to/dir/       # process all in a specific directory
"""

import json
import os
import sys
import glob
import time
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    import xml.etree.ElementTree as etree
    print("[WARN] lxml not found, falling back to stdlib xml.etree (slower).")


# ─── Canonical book ordering (1-66) for number-only formats like Amplified ────
BOOK_NAMES_BY_NUMBER = {
    1: "Genesis", 2: "Exodus", 3: "Leviticus", 4: "Numbers", 5: "Deuteronomy",
    6: "Joshua", 7: "Judges", 8: "Ruth", 9: "1 Samuel", 10: "2 Samuel",
    11: "1 Kings", 12: "2 Kings", 13: "1 Chronicles", 14: "2 Chronicles",
    15: "Ezra", 16: "Nehemiah", 17: "Esther", 18: "Job", 19: "Psalms",
    20: "Proverbs", 21: "Ecclesiastes", 22: "Song of Solomon", 23: "Isaiah",
    24: "Jeremiah", 25: "Lamentations", 26: "Ezekiel", 27: "Daniel",
    28: "Hosea", 29: "Joel", 30: "Amos", 31: "Obadiah", 32: "Jonah",
    33: "Micah", 34: "Nahum", 35: "Habakkuk", 36: "Zephaniah", 37: "Haggai",
    38: "Zechariah", 39: "Malachi",
    40: "Matthew", 41: "Mark", 42: "Luke", 43: "John", 44: "Acts",
    45: "Romans", 46: "1 Corinthians", 47: "2 Corinthians", 48: "Galatians",
    49: "Ephesians", 50: "Philippians", 51: "Colossians",
    52: "1 Thessalonians", 53: "2 Thessalonians",
    54: "1 Timothy", 55: "2 Timothy", 56: "Titus", 57: "Philemon",
    58: "Hebrews", 59: "James", 60: "1 Peter", 61: "2 Peter",
    62: "1 John", 63: "2 John", 64: "3 John", 65: "Jude", 66: "Revelation",
}

# ─── OSIS abbreviation → full name mapping ───────────────────────────────────
OSIS_TO_NAME = {
    "Gen": "Genesis", "Exod": "Exodus", "Lev": "Leviticus", "Num": "Numbers",
    "Deut": "Deuteronomy", "Josh": "Joshua", "Judg": "Judges", "Ruth": "Ruth",
    "1Sam": "1 Samuel", "2Sam": "2 Samuel", "1Kgs": "1 Kings", "2Kgs": "2 Kings",
    "1Chr": "1 Chronicles", "2Chr": "2 Chronicles", "Ezra": "Ezra",
    "Neh": "Nehemiah", "Esth": "Esther", "Job": "Job", "Ps": "Psalms",
    "Prov": "Proverbs", "Eccl": "Ecclesiastes", "Song": "Song of Solomon",
    "Isa": "Isaiah", "Jer": "Jeremiah", "Lam": "Lamentations",
    "Ezek": "Ezekiel", "Dan": "Daniel", "Hos": "Hosea", "Joel": "Joel",
    "Amos": "Amos", "Obad": "Obadiah", "Jonah": "Jonah", "Mic": "Micah",
    "Nah": "Nahum", "Hab": "Habakkuk", "Zeph": "Zephaniah", "Hag": "Haggai",
    "Zech": "Zechariah", "Mal": "Malachi",
    "Matt": "Matthew", "Mark": "Mark", "Luke": "Luke", "John": "John",
    "Acts": "Acts", "Rom": "Romans", "1Cor": "1 Corinthians",
    "2Cor": "2 Corinthians", "Gal": "Galatians", "Eph": "Ephesians",
    "Phil": "Philippians", "Col": "Colossians", "1Thess": "1 Thessalonians",
    "2Thess": "2 Thessalonians", "1Tim": "1 Timothy", "2Tim": "2 Timothy",
    "Titus": "Titus", "Phlm": "Philemon", "Heb": "Hebrews", "Jas": "James",
    "1Pet": "1 Peter", "2Pet": "2 Peter", "1John": "1 John",
    "2John": "2 John", "3John": "3 John", "Jude": "Jude", "Rev": "Revelation",
}


# ─── Translation name extraction from filename ───────────────────────────────
FILENAME_TO_TRANSLATION = {
    "Bible_English_ESV": "ESV",
    "Bible_English_NLT": "NLT",
    "kjv": "KJV",
    "EnglishAmplifiedBible": "AMP",
    "NewKingJamesVersion": "NKJV",
    "NewInternationalVersion": "NIV",
}


def detect_translation(filepath: str) -> str:
    """Extract a short translation name from the filename."""
    stem = Path(filepath).stem
    return FILENAME_TO_TRANSLATION.get(stem, stem.upper())


def strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from a tag: '{http://...}verse' → 'verse'."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def get_text(element) -> str:
    """Get all text content from an element, including tail text of children."""
    # itertext() yields all text fragments inside the element
    return "".join(element.itertext()).strip()


# ─── Format-specific parsers ─────────────────────────────────────────────────

def parse_xmlbible(root) -> dict:
    """Parse XMLBIBLE format (ESV, NLT): BIBLEBOOK > CHAPTER > VERS."""
    books = {}
    for book_el in root.iter("BIBLEBOOK"):
        book_name = book_el.get("bname", f"Book_{book_el.get('bnumber', '?')}")
        chapters = {}
        for chap_el in book_el.iter("CHAPTER"):
            chap_num = chap_el.get("cnumber")
            verses = {}
            for verse_el in chap_el.iter("VERS"):
                v_num = verse_el.get("vnumber")
                verses[v_num] = get_text(verse_el)
            if verses:
                chapters[chap_num] = verses
        if chapters:
            books[book_name] = chapters
    return books


def parse_bcv(root) -> dict:
    """Parse bible > b > c > v format (NKJV .xmm, NIV)."""
    books = {}
    for book_el in root.iter("b"):
        book_name = book_el.get("n", "Unknown")
        chapters = {}
        for chap_el in book_el.iter("c"):
            chap_num = chap_el.get("n")
            verses = {}
            for verse_el in chap_el.iter("v"):
                v_num = verse_el.get("n")
                verses[v_num] = get_text(verse_el)
            if verses:
                chapters[chap_num] = verses
        if chapters:
            books[book_name] = chapters
    return books


def parse_osis(root) -> dict:
    """Parse OSIS format (KJV): div[type=book] > chapter > verse.
    
    osisID patterns:
      - book div: osisID='Gen'
      - chapter:  osisID='Gen.1'
      - verse:    osisID='Gen.1.1'
    """
    ns = {"osis": "http://www.bibletechnologies.net/2003/OSIS/namespace"}
    books = {}

    # Find all book-level divs
    for div in root.findall(".//osis:div[@type='book']", ns):
        osis_id = div.get("osisID", "")
        book_name = OSIS_TO_NAME.get(osis_id, osis_id)
        chapters = {}

        for chap_el in div.findall("osis:chapter", ns):
            chap_osis = chap_el.get("osisID", "")  # e.g. 'Gen.1'
            chap_num = chap_osis.split(".")[-1] if "." in chap_osis else chap_osis
            verses = {}

            for verse_el in chap_el.findall("osis:verse", ns):
                verse_osis = verse_el.get("osisID", "")  # e.g. 'Gen.1.1'
                v_num = verse_osis.split(".")[-1] if "." in verse_osis else verse_osis
                verses[v_num] = get_text(verse_el)

            if verses:
                chapters[chap_num] = verses

        if chapters:
            books[book_name] = chapters

    return books


def parse_amplified(root) -> dict:
    """Parse Amplified format: bible > testament > book[number] > chapter[number] > verse[number]."""
    books = {}
    for book_el in root.iter("book"):
        book_num = int(book_el.get("number", 0))
        book_name = BOOK_NAMES_BY_NUMBER.get(book_num, f"Book_{book_num}")
        chapters = {}
        for chap_el in book_el.iter("chapter"):
            chap_num = chap_el.get("number")
            verses = {}
            for verse_el in chap_el.iter("verse"):
                v_num = verse_el.get("number")
                verses[v_num] = get_text(verse_el)
            if verses:
                chapters[chap_num] = verses
        if chapters:
            books[book_name] = chapters
    return books


# ─── Auto-detect & dispatch ──────────────────────────────────────────────────

def detect_and_parse(filepath: str) -> dict:
    """Auto-detect XML format and parse to unified dict."""
    t0 = time.perf_counter()

    # Parse the XML tree
    tree = etree.parse(filepath)
    root = tree.getroot()
    root_tag = strip_ns(root.tag).lower()

    # Detect format from root element
    if root_tag == "xmlbible":
        fmt = "XMLBIBLE"
        books = parse_xmlbible(root)
    elif root_tag == "osis":
        fmt = "OSIS"
        books = parse_osis(root)
    elif root_tag == "bible":
        # Disambiguate: Amplified has <testament> children, bcv has <b> children
        has_testament = root.find("testament") is not None or root.find(".//testament") is not None
        has_b_tags = root.find("b") is not None or root.find(".//b") is not None

        if has_testament:
            fmt = "Amplified"
            books = parse_amplified(root)
        elif has_b_tags:
            fmt = "bible/b/c/v"
            books = parse_bcv(root)
        else:
            # Fallback: might be Amplified-style with direct <book> children
            fmt = "Amplified (fallback)"
            books = parse_amplified(root)
    else:
        raise ValueError(f"Unknown root element: <{root.tag}>. Cannot auto-detect format.")

    elapsed = time.perf_counter() - t0
    translation = detect_translation(filepath)

    # Count stats
    total_books = len(books)
    total_chapters = sum(len(c) for c in books.values())
    total_verses = sum(len(v) for c in books.values() for v in c.values())

    print(f"  [{translation}] Parsed {filepath}")
    print(f"    Format:   {fmt}")
    print(f"    Books:    {total_books}")
    print(f"    Chapters: {total_chapters}")
    print(f"    Verses:   {total_verses}")
    print(f"    Time:     {elapsed:.3f}s")

    return {
        "translation": translation,
        "books": books,
    }


def convert_file(filepath: str, output_dir: str) -> str:
    """Convert a single Bible XML/XMM file to JSON. Returns output path."""
    result = detect_and_parse(filepath)
    translation = result["translation"]
    out_name = f"{translation.lower()}.json"
    out_path = os.path.join(output_dir, out_name)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"    Output:   {out_path} ({size_mb:.2f} MB)")
    return out_path


def main():
    # Determine input source
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = os.path.expanduser("~/Downloads")

    # Determine output directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "json")
    os.makedirs(output_dir, exist_ok=True)

    # Collect files to process
    if os.path.isfile(target):
        files = [target]
    elif os.path.isdir(target):
        files = sorted(
            glob.glob(os.path.join(target, "*.xml"))
            + glob.glob(os.path.join(target, "*.xmm"))
        )
    else:
        print(f"[ERROR] '{target}' is neither a file nor a directory.")
        sys.exit(1)

    if not files:
        print(f"[ERROR] No .xml or .xmm files found in '{target}'.")
        sys.exit(1)

    print(f"Found {len(files)} Bible file(s) to convert.")
    print(f"Output directory: {output_dir}\n")

    t_total = time.perf_counter()
    outputs = []
    for filepath in files:
        try:
            out = convert_file(filepath, output_dir)
            outputs.append(out)
        except Exception as e:
            print(f"  [ERROR] Failed to convert {filepath}: {e}")
        print()

    elapsed_total = time.perf_counter() - t_total
    print(f"Done. Converted {len(outputs)}/{len(files)} files in {elapsed_total:.3f}s total.")
    print(f"JSON files written to: {output_dir}/")


if __name__ == "__main__":
    main()
