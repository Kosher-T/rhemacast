#!/usr/bin/env python3
"""
build_keywords.py — Build the per-verse keyword index for FTS search.

Turns two public-domain-flavored resources into a numpy BM25 postings
compact in the exact `core/bible_service._load_postings` format, scored
at query time with the shared `_score_postings` (bit-identical BM25
arithmetic, own idf mass):

  1. Nave's Topical Bible subjects  → verse → topic/subtopic keyword tokens
  2. KJV interlinear Strong's tags  → verse → lemma gloss + transliteration
     tokens (every verse gains its Hebrew/Greek identity: "agape" matches
     even where the translation says "charity").

Usage:
  python data/bible/build_keywords.py [--fetch] [--source-dir DIR]
                                      [--db PATH] [--out-dir DIR]

Outputs (data/indexes/):
  keywords.pkl               — postings compact (numpy arrays + lookup)
  keywords_meta.json         — coverage stats, source SHAs, build time
  keywords_fingerprint.json  — input SHAs for rebuild-change detection

Sources are NOT committed (gitignored); use --fetch to download them.
See SOURCES.md for URLs, licenses, and attribution.
"""

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import pickle
import sqlite3
import sys
import time
import urllib.request
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
from core.text_utils import tokenize  # noqa: E402

# ─── Pinned sources (mirrored in SOURCES.md) ────────────────────────────────

SOURCES = {
    "naves.csv": (
        "https://raw.githubusercontent.com/BradyStephenson/bible-data"
        "/main/NavesTopicalDictionary.csv"),
    "interlinear.json.gz": (
        "https://raw.githubusercontent.com/kennethreitz/kjvstudy.org"
        "/main/kjvstudy_org/data/interlinear.json.gz"),
    "hebrew.json": (
        "https://raw.githubusercontent.com/kennethreitz/kjvstudy.org"
        "/main/kjvstudy_org/data/strongs/hebrew.json"),
    "greek.json": (
        "https://raw.githubusercontent.com/kennethreitz/kjvstudy.org"
        "/main/kjvstudy_org/data/strongs/greek.json"),
}

# BM25Okapi defaults (must match rank_bm25 or scores drift from the main lanes).
_K1, _B, _EPSILON = 1.5, 0.75, 0.25

# Nave's abbreviations → full book names. Only unambiguous abbreviations;
# prose lookalikes (GOD, LORD, PAUL, JOHN-as-person…) are excluded and any
# coordinate that fails KJV validation is dropped with a report.
ABBREV = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus",
    "NUM": "Numbers", "DEU": "Deuteronomy", "JOS": "Joshua",
    "JDG": "Judges", "RUT": "Ruth", "1SA": "1 Samuel",
    "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
    "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra",
    "NEH": "Nehemiah", "EST": "Esther", "JOB": "Job",
    "PSA": "Psalms", "PRO": "Proverbs", "ECC": "Ecclesiastes",
    "ISA": "Isaiah", "JER": "Jeremiah", "LAM": "Lamentations",
    "EZK": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea",
    "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah",
    "JON": "Jonah", "MIC": "Micah", "HAB": "Habakkuk",
    "ZEP": "Zephaniah", "HAG": "Haggai", "ZEC": "Zechariah",
    "MAL": "Malachi", "MAT": "Matthew", "MRK": "Mark",
    "LUK": "Luke", "JHN": "John", "ACT": "Acts",
    "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians",
    "GAL": "Galatians", "EPH": "Ephesians", "PHP": "Philippians",
    "COL": "Colossians", "1TH": "1 Thessalonians",
    "2TH": "2 Thessalonians", "1TI": "1 Timothy", "2TI": "2 Timothy",
    "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
    "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter",
    "1JN": "1 John", "1JHN": "1 John", "2JN": "2 John",
    "3JN": "3 John", "REV": "Revelation",
}

_REF_BOOK = r"(?:[1-3][A-Z]{2,4}|[A-Z]{2,4})"
import re as _re
# A book token plus its trailing number run ("EXO 6:16-20", "PSA 77").
_REFTOK = _re.compile(r"\b([1-3]?[A-Z]{2,4})\s+(\d[\d\s,:\-]*)")
_CHAPTER_ONLY = _re.compile(r"^(\d+)\s*$")
_CV = _re.compile(r"^(\d+)\s*:\s*(.+)$")
# Real-looking but ambiguous tokens: never treated as books (the KJV
# validator cannot tell person-John from Gospel-John).
_AMBIGUOUS = {"JOHN", "JUD", "SON"}


# ─── Fetch ──────────────────────────────────────────────────────────────────

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_sources(source_dir: str):
    os.makedirs(source_dir, exist_ok=True)
    for name, url in SOURCES.items():
        dest = os.path.join(source_dir, name)
        if os.path.exists(dest):
            print(f"  have {name}")
            continue
        print(f"  downloading {name}…")
        urllib.request.urlretrieve(url, dest)
        print(f"  saved {name} ({os.path.getsize(dest):,} bytes)")


# ─── KJV coordinates ────────────────────────────────────────────────────────

def load_kjv(db_path: str):
    """(book, chapter, verse) → text, plus chapter → verse lists."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT book, chapter, verse_num, text FROM verses "
        "WHERE version = 'KJV' ORDER BY rowid").fetchall()
    conn.close()
    texts, chapters = {}, {}
    for book, ch, vs, text in rows:
        key = (book, int(ch), int(vs))
        texts[key] = text or ""
        chapters.setdefault((book, int(ch)), []).append(int(vs))
    print(f"  KJV verses: {len(texts):,}")
    return texts, chapters


# ─── Nave's parsing ─────────────────────────────────────────────────────────

def _expand_spec(spec: str, chapter: int, book: str, chapters: dict,
                 valid: set, stats: Counter):
    """'16-20' / '2,3' / '23' → validated coordinate list."""
    out = []
    for part in spec.split(","):
        part = part.strip()
        m = _re.match(r"^(\d+)(?:\s*-\s*(\d+))?$", part)
        if not m:
            stats["bad_spec"] += 1
            continue
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        if hi - lo > 200:
            stats["range_capped"] += 1
            hi = lo + 200
        for v in range(lo, hi + 1):
            key = (book, chapter, v)
            if key in valid:
                out.append(key)
            else:
                stats["invalid_coord"] += 1
    return out


def parse_naves(path: str, valid: set, chapters: dict):
    """entry text → list of (label, coord); labels are subtopic phrases."""
    per_verse = {}
    stats = Counter()
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    stats["subjects"] = len(rows)
    for row in rows:
        subject = (row.get("subject") or "").strip()
        entry = row.get("entry") or ""
        for line in entry.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("-"):
                line = line[1:].strip()
            book, chapter = None, None
            label_parts, refs_found = [], False
            for piece in line.split(";"):
                piece = piece.strip()
                if not piece:
                    continue
                found = [(m.start(), m.group(1), m.group(2))
                         for m in _REFTOK.finditer(piece)]
                for s, tok, _ in found:
                    if tok in _AMBIGUOUS:
                        stats["ambiguous_book"] += 1
                known = [(s, b, r) for (s, b, r) in found if b in ABBREV]
                if not known:
                    # Chapter-only with a carried book ("…6:3-15,50-53; 24").
                    if book is not None and _CHAPTER_ONLY.match(piece):
                        ch = int(piece)
                        for v in chapters.get((book, ch), []):
                            key = (book, ch, v)
                            per_verse.setdefault(key, []).append(
                                (subject, line_label(label_parts, subject)))
                        refs_found = True
                    elif not refs_found:
                        label_parts.append(piece)
                    continue
                if not refs_found and not label_parts:
                    head = piece[:known[0][0]].strip(" -–—")
                    if head:
                        label_parts.append(head)
                for _s, b, r in known:
                    book = ABBREV[b]
                    for item in r.split(","):
                        item = item.strip()
                        if not item:
                            continue
                        cm = _CV.match(item)
                        if cm:
                            chapter = int(cm.group(1))
                            spec = cm.group(2)
                        else:
                            spec = item
                        if chapter is None:
                            stats["orphan_spec"] += 1
                            continue
                        for key in _expand_spec(spec, chapter, book,
                                                chapters, valid, stats):
                            per_verse.setdefault(key, []).append(
                                (subject, line_label(label_parts, subject)))
                    refs_found = True
    # Flatten to keyword counters per verse.
    keyword_docs = {}
    for key, pairs in per_verse.items():
        c = Counter()
        for subject, label in pairs:
            c.update(tokenize(subject))
            c.update(tokenize(label))
        keyword_docs[key] = c
    stats["verses_covered"] = len(keyword_docs)
    return keyword_docs, stats


def line_label(label_parts: list, subject: str) -> str:
    """Subtopic label text (the human-written phrase before references)."""
    return " ".join(label_parts) if label_parts else subject


# ─── Strong's keywords ──────────────────────────────────────────────────────

def strongs_keywords(source_dir: str, valid: set):
    with gzip.open(os.path.join(source_dir, "interlinear.json.gz"),
                   "rt", encoding="utf-8") as f:
        interlinear = json.load(f)
    lex = {}
    for name in ("hebrew.json", "greek.json"):
        with open(os.path.join(source_dir, name), encoding="utf-8") as f:
            lex.update(json.load(f))
    per_verse = {}
    stats = Counter(numbers_missing=0, verses_tagged=0, refs_dropped=0)
    for ref, words in interlinear.items():
        try:
            book, ch, vs = ref.split(":")
            key = (book, int(ch), int(vs))
        except ValueError:
            stats["refs_dropped"] += 1
            continue
        if key not in valid:
            stats["refs_dropped"] += 1
            continue
        c = Counter()
        for w in words:
            num = (w.get("strongs") or "").strip().upper()
            entry = lex.get(num)
            if not entry:
                if num:
                    stats["numbers_missing"] += 1
                continue
            gloss = entry.get("kjv_def") or entry.get("strongs_def") or ""
            translit = entry.get("translit") or entry.get("xlit") or ""
            c.update(tokenize(gloss))
            c.update(tokenize(translit))
        if c:
            per_verse[key] = c
            stats["verses_tagged"] += 1
    return per_verse, stats


# ─── Compact build (numpy arrays in _score_postings' layout) ───────────────

def build_compact(docs: dict, kjv_texts: dict):
    """{coord: Counter} → numpy postings compact + ordered coord list."""
    coords = sorted(docs.keys())
    # Document frequencies.
    df = Counter()
    doc_lens = []
    for key in coords:
        c = docs[key]
        doc_lens.append(sum(c.values()))
        df.update(c.keys())
    n = len(coords)
    # BM25Okapi idf with epsilon floor (exact rank_bm25 formula).
    idf, idf_sum, negatives = {}, 0.0, []
    for term, freq in df.items():
        v = math.log(n - freq + 0.5) - math.log(freq + 0.5)
        idf[term] = v
        idf_sum += v
        if v < 0:
            negatives.append(term)
    eps = _EPSILON * (idf_sum / len(idf)) if idf else 0.0
    for term in negatives:
        idf[term] = eps
    avgdl = sum(doc_lens) / n if n else 0.0
    post = {}
    for idx, key in enumerate(coords):
        for term, freq in docs[key].items():
            slot = post.get(term)
            if slot is None:
                slot = post[term] = [[], []]
            slot[0].append(idx)
            slot[1].append(freq if freq < 65535 else 65535)
    arrays = {term: (np.array(ix, dtype=np.int32),
                     np.array(fq, dtype=np.uint16))
              for term, (ix, fq) in post.items()}
    book_names = sorted({key[0] for key in coords})
    book_id_of = {name: i for i, name in enumerate(book_names)}
    lookup = [("KW", book, ch, vs, kjv_texts.get((book, ch, vs), ""))
              for (book, ch, vs) in coords]
    compact = {"postings": arrays, "idf": idf, "avgdl": float(avgdl),
               "doc_len": np.array(doc_lens, dtype=np.int32),
               "book_ids": np.array([book_id_of[k[0]] for k in coords],
                                    dtype=np.int32),
               "book_names": book_names, "k1": _K1, "b": _B,
               "corpus_size": n, "lookup": lookup,
               "folded": {}, "grams": {}}
    return compact, coords


# ─── Smoke test ─────────────────────────────────────────────────────────────

def _smoke(compact, coords):
    sys.path.insert(0, os.getcwd())
    from core.bible_service import _score_postings
    from core.text_utils import tokenize as tok
    by_coord = {tuple(l[1:4]): i for i, l in enumerate(compact["lookup"])}
    probes = {
        "prodigal son": ("Luke", 15, 11),
        "agape love": None,  # any G26 verse; just show top books
        "golden calf": ("Exodus", 32, 1),
        "lovingkindness mercy": None,
    }
    print("\n  ── Smoke test ──")
    for q, expect in probes.items():
        scores, _hits = _score_postings(compact, tok(q))
        top = np.argsort(scores)[::-1][:3]
        line = " │ ".join(
            f"{compact['lookup'][i][1]} {compact['lookup'][i][2]}:"
            f"{compact['lookup'][i][3]} ({scores[i]:.1f})" for i in top)
        mark = ""
        if expect is not None:
            mark = " ✓" if by_coord.get(expect) in set(top.tolist()) else \
                " ✗ (expected %s %d:%d)" % expect
        print(f'  "{q}" → {line}{mark}')


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Build the keyword index.")
    ap.add_argument("--fetch", action="store_true",
                    help="Download sources if missing")
    ap.add_argument("--source-dir",
                    default=os.path.join(os.path.dirname(__file__), "sources"))
    ap.add_argument("--db",
                    default=os.path.join(os.path.dirname(__file__), "bible.db"))
    ap.add_argument("--out-dir",
                    default=os.path.join(os.path.dirname(__file__),
                                         "..", "indexes"))
    args = ap.parse_args()
    t0 = time.perf_counter()

    if args.fetch:
        print("Fetching sources…")
        fetch_sources(args.source_dir)
    for name in SOURCES:
        if not os.path.exists(os.path.join(args.source_dir, name)):
            sys.exit(f"[ERROR] missing {name} — rerun with --fetch")
    source_shas = {name: _sha256(os.path.join(args.source_dir, name))
                   for name in SOURCES}

    kjv_texts, chapters = load_kjv(args.db)
    valid = set(kjv_texts)

    print("Parsing Nave's…")
    nave_docs, nave_stats = parse_naves(
        os.path.join(args.source_dir, "naves.csv"), valid, chapters)
    print(f"  subjects: {nave_stats['subjects']:,} │ "
          f"verses: {nave_stats['verses_covered']:,} │ "
          f"invalid coords dropped: {nave_stats['invalid_coord']:,} │ "
          f"orphans: {nave_stats['orphan_spec'] + nave_stats['orphan_chapter']:,}")

    print("Tagging Strong's…")
    strong_docs, strong_stats = strongs_keywords(args.source_dir, valid)
    print(f"  verses tagged: {strong_stats['verses_tagged']:,} │ "
          f"refs dropped: {strong_stats['refs_dropped']:,} │ "
          f"numbers missing from lexicon: {strong_stats['numbers_missing']:,}")

    merged = {}
    for key in set(nave_docs) | set(strong_docs):
        c = Counter()
        c.update(nave_docs.get(key, Counter()))
        c.update(strong_docs.get(key, Counter()))
        merged[key] = c
    n_nave = len(nave_docs)
    n_strong = len(strong_docs)
    n_both = len(set(nave_docs) & set(strong_docs))
    print(f"  merged verses: {len(merged):,} "
          f"(nave {n_nave:,} │ strong {n_strong:,} │ both {n_both:,})")

    print("Building postings compact…")
    compact, coords = build_compact(merged, kjv_texts)
    print(f"  terms: {len(compact['postings']):,} │ "
          f"docs: {compact['corpus_size']:,} │ "
          f"avgdl: {compact['avgdl']:.1f}")

    os.makedirs(args.out_dir, exist_ok=True)
    kw_path = os.path.join(args.out_dir, "keywords.pkl")
    with open(kw_path, "wb") as f:
        pickle.dump(compact, f, protocol=pickle.HIGHEST_PROTOCOL)
    meta = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                   time.gmtime()),
        "verses_indexed": len(coords),
        "verses_naves": n_nave,
        "verses_strongs": n_strong,
        "verses_both": n_both,
        "verses_neither": len(valid) - len(merged),
        "terms": len(compact["postings"]),
        "avg_keywords_per_verse": round(
            sum(sum(merged[k].values()) for k in merged) / len(merged), 1)
        if merged else 0,
        "nave_stats": dict(nave_stats),
        "strong_stats": dict(strong_stats),
        "source_shas": source_shas,
        "keywords_sha256": _sha256(kw_path),
    }
    with open(os.path.join(args.out_dir, "keywords_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(args.out_dir, "keywords_fingerprint.json"),
              "w") as f:
        json.dump({"built_at": meta["built_at"],
                   "source_shas": source_shas,
                   "verse_count": len(valid)}, f, indent=2)
    print(f"\n  done in {time.perf_counter() - t0:.1f}s → {kw_path}")
    _smoke(compact, coords)


if __name__ == "__main__":
    main()
