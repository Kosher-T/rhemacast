"""
core/easyworship_import.py

EasyWorship v6 song database importer.

Source layout (Default/v6.1/Databases/Data/):
  Songs.db      — table `song`: rowid, song_uid, title, author, copyright,
                  administrator, reference_number, provider_id, ...
  SongWords.db  — table `word`: song_id (= Songs.rowid), words (RTF),
                  slide_uids (comma-separated UUIDs, one per slide)
  SongKeys.db   — EW's own keyword index (ignored — we build FTS5 ourselves)
  SongHistory.db— usage log + denormalized song copies (ignored)

Linkage: Songs.rowid == SongWords.song_id (1:1, verified zero orphans).

RTF lyrics format (machine-generated, consistent):
  - Content lines end with \\par and carry text after a font token
    (`\\fntnamaut TEXT\\par`)
  - A paragraph block WITHOUT \\fntnamaut but WITH \\li0/\\sb0 controls is an
    EMPTY line = slide boundary (single blank splits slides here, unlike our
    txt format's double-blank rule)
  - Blocks with neither are RTF header noise (fonttbl/colortbl/pnseclvl...)
  - Section headers are standalone lines like "Verse 1", "Chorus", "Bridge"
  - A section can span multiple slides: continuation slides after a blank
    inherit the current section (no repeated header)
"""

import csv
import os
import re
import sqlite3

from core.slide_service import create_deck_from_slides

_EW_SOURCE_PREFIX = "easyworship://song/"

# ── Collation ────────────────────────────────────────────────────────────────

def _utf8_ci(a: str, b: str) -> int:
    al, bl = a.lower(), b.lower()
    return (al > bl) - (al < bl)


def _open_ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    # Songs.db declares columns COLLATE UTF8_U_CI which python's sqlite
    # cannot resolve unless registered.
    conn.create_collation("UTF8_U_CI", _utf8_ci)
    return conn


# ── RTF parsing ──────────────────────────────────────────────────────────────

_SECTION_RE = re.compile(
    r"^(verse|chorus|bridge|tag|pre-?chorus|prechorus|ending|intro|outro|"
    r"v\s*\d*|c\s*\d*|b\s*\d*|t\s*\d*)"
    r"(\s+\d+)?$",
    re.IGNORECASE,
)


def is_section_header(line: str) -> bool:
    """True if a lyric line is an EasyWorship section marker ('Verse 1', 'Chorus', ...)."""
    return bool(_SECTION_RE.match(line.strip()))


def _rtf_unescape(text: str) -> str:
    """Decode \\'hh (cp1252) and \\uN? unicode escapes; unescape braces/backslash."""
    def hex_repl(m):
        try:
            return bytes.fromhex(m.group(1)).decode("cp1252")
        except ValueError:
            return m.group(0)

    def uni_repl(m):
        try:
            code = int(m.group(1))
            if code < 0:
                code += 0x10000
            return chr(code)
        except (ValueError, OverflowError):
            return m.group(0)

    text = re.sub(r"\\'([0-9a-fA-F]{2})", hex_repl, text)
    # \uN followed by optional fallback char represented as '?'
    text = re.sub(r"\\u(-?\d+)\s*\??", uni_repl, text)
    text = text.replace(r"\{", "{").replace(r"\}", "}").replace(r"\\", "\\")
    # NOTE: no strip() here — color-run segmentation preserves boundary whitespace
    return text.replace("{", "").replace("}", "")


# \colortbl: {\colortbl ;\red51\green51\blue153;} (also matches {\*\colortbl})
# Index 0 = default/auto; index N = Nth listed color.
_COLORTBL_RE = re.compile(r"\\(?:\*\\?)?colortbl([^{}]+)")
_COLOR_DEF_RE = re.compile(r"\\red(\d+)\\green(\d+)\\blue(\d+)")
_CF_SPLIT_RE = re.compile(r"\\cf(-?\d+)")
# Remaining RTF control words inside a color segment (\sdnotstroke, \shad0...)
_CTRL_WORD_RE = re.compile(r"\\(?:\*)?[a-zA-Z]+(?:-?\d+)?[ ]?")


def parse_color_palette(rtf: str) -> dict[int, str]:
    """Parse {\\colortbl} into {index: "#rrggbb"} (index 0 omitted — default)."""
    m = _COLORTBL_RE.search(rtf or "")
    if not m:
        return {}
    palette: dict[int, str] = {}
    idx = 0
    for part in m.group(1).split(";"):
        cm = _COLOR_DEF_RE.search(part)
        if cm:
            idx += 1
            r, g, b = int(cm.group(1)), int(cm.group(2)), int(cm.group(3))
            palette[idx] = f"#{r:02x}{g:02x}{b:02x}"
    return palette


def _color_runs_to_markup(tail: str, palette: dict[int, str]) -> str:
    """Convert \\cfN ... \\cfM runs in an RTF tail to [text: (#hex)] markup.

    Segments with default color (0/unknown index) are emitted unwrapped.
    """
    if "\\cf" not in tail:
        # No explicit runs — still strip stray control words + braces
        cleaned = _CTRL_WORD_RE.sub("", tail)
        return _rtf_unescape(cleaned)

    parts = _CF_SPLIT_RE.split(tail)
    # parts alternates: [pre, id1, seg1, id2, seg2, ...]
    out: list[str] = []
    color_idx = 0
    for i, part in enumerate(parts):
        if i % 2 == 1:
            try:
                color_idx = int(part)
            except ValueError:
                color_idx = 0
            continue
        cleaned = _rtf_unescape(_CTRL_WORD_RE.sub("", part))
        if not cleaned:
            continue
        hexcolor = palette.get(color_idx) if color_idx != 0 else None
        if hexcolor:
            m = re.match(r"^(\s*)(.*?)(\s*)$", cleaned, re.S)
            lead, core, trail = m.groups()
            if not core:
                out.append(cleaned)
                continue
            # Avoid doubling separators when previous segment already ends with space
            if out and out[-1].endswith((" ", "\n")):
                lead = ""
            out.append(f"{lead}[{core}: ({hexcolor})]{trail}")
        else:
            # Collapse doubling when previous colored run already emitted a trail space
            if out and cleaned.startswith(" ") and out[-1].endswith(" "):
                cleaned = cleaned.lstrip()
            out.append(cleaned)
    return "".join(out)


def _rtf_block_text(block: str, palette: dict[int, str] | None = None) -> str | None:
    """Extract display text from one RTF paragraph block.

    Returns None if the block carries no text token. Tries fntnamaut (old
    dialect) before sdfsauto (EW2 dialect); sequential find() avoids the
    earliest-match trap of a combined regex alternation. \\cf color runs are
    converted to [text: (#hex)] inline markup.
    """
    for token in ("\\fntnamaut", "\\sdfsauto"):
        idx = block.find(token)
        if idx != -1:
            tail = block[idx + len(token):]
            if palette is None:
                palette = {}
            return _color_runs_to_markup(tail, palette)
    return None


def rtf_to_slides(rtf: str) -> list[dict]:
    """Convert EasyWorship RTF lyrics to slides_json entries.

    Two dialects:
      Old: content lines carry \\fntnamaut; EMPTY \\li0/\\sb0 paragraph blocks
           are implicit slide boundaries; section headers detected by regex.
      EW2: text carries \\sdfsauto; explicit \\sdslidemarker blocks are slide
           boundaries; section labels are \\sdparawysiwghidden blocks (EW hides
           them on screen — non-header hidden lines are dropped, matching
           WYSIWYG behavior).

    A standalone section-header line sets the current section (not displayed);
    subsequent slides until the next header inherit it. Slides before any
    header get section=None.
    """
    if not rtf:
        return []
    ew2 = "\\sdslidemarker" in rtf or "\\sdfsauto" in rtf
    palette = parse_color_palette(rtf)

    slides: list[dict] = []
    current_section: str | None = None
    buf: list[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf).strip()
        if text:
            slides.append({"section": current_section, "text": text})
        buf = []

    for block in re.split(r"\\par", rtf):
        marker = ew2 and "\\sdslidemarker" in block
        hidden = ew2 and (
            "\\sdparawysiwghidden" in block or "sdewparatemplatestyle102" in block
        )
        text = _rtf_block_text(block, palette)

        if marker:
            flush()

        if text is None:
            # Old dialect: empty paragraph block = implicit boundary
            if not ew2 and not marker and ("\\li0" in block or "\\sb0" in block):
                flush()
            continue

        stripped = text.strip()
        if stripped == "":
            if not ew2 and not marker:
                flush()  # old-dialect blank boundary
            continue

        if hidden:
            # EW hides these lines on screen: section labels become sections,
            # anything else (e.g. pasted titles) is dropped like EW does.
            if is_section_header(stripped):
                flush()
                current_section = stripped.title()
            continue

        if not ew2 and is_section_header(stripped):
            flush()
            current_section = stripped.title()
            continue

        buf.append(stripped)

    flush()
    return slides


# ── Source readers ───────────────────────────────────────────────────────────

def read_songs_from_db(data_dir: str) -> list[dict]:
    """Read songs from EasyWorship Data dir (Songs.db + SongWords.db).

    Returns dicts: {ew_rowid, song_uid, title, author, copyright, administrator,
    reference_number, rtf}.
    """
    songs_db = os.path.join(data_dir, "Songs.db")
    words_db = os.path.join(data_dir, "SongWords.db")
    if not os.path.isfile(songs_db):
        raise FileNotFoundError(f"Songs.db not found in {data_dir}")

    conn = _open_ro(songs_db)
    if os.path.isfile(words_db):
        conn.execute(f"ATTACH DATABASE '{words_db}' AS sw")
        rows = conn.execute(
            """SELECT s.rowid, s.song_uid, s.title, s.author, s.copyright,
                      s.administrator, s.reference_number, w.words
               FROM song s
               LEFT JOIN sw.word w ON w.song_id = s.rowid
               ORDER BY s.rowid ASC"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT rowid, song_uid, title, author, copyright, administrator,
                      reference_number, NULL
               FROM song ORDER BY rowid ASC"""
        ).fetchall()
    conn.close()

    songs = []
    for rowid, uid, title, author, copyright_, admin, refnum, rtf in rows:
        songs.append({
            "ew_rowid": rowid,
            "song_uid": uid or None,
            "title": title or "",
            "author": author or None,
            "copyright": copyright_ or None,
            "administrator": admin or None,
            "reference_number": refnum or None,
            "rtf": rtf,
        })
    return songs


def read_songs_from_csv(songs_csv: str, words_csv: str) -> list[dict]:
    """Fallback reader for CSV exports of the `song` and `word` tables."""
    words_by_song_id: dict[int, str] = {}
    with open(words_csv, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                sid = int(row["song_id"])
            except (KeyError, TypeError, ValueError):
                continue
            words_by_song_id[sid] = row.get("words") or ""

    songs = []
    with open(songs_csv, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                rowid = int(row["rowid"])
            except (KeyError, TypeError, ValueError):
                continue
            songs.append({
                "ew_rowid": rowid,
                "title": row.get("title") or "",
                "author": row.get("author") or None,
                "copyright": row.get("copyright") or None,
                "administrator": row.get("administrator") or None,
                "reference_number": row.get("reference_number") or None,
                "rtf": words_by_song_id.get(rowid),
            })
    return songs


# ── Importer ────────────────────────────────────────────────────────────────

def import_easyworship(
    data_dir: str | None = None,
    songs_csv: str | None = None,
    words_csv: str | None = None,
    skip_empty: bool = True,
) -> dict:
    """Import EasyWorship songs into slide_decks.

    Either provide `data_dir` (Songs.db/SongWords.db) or both CSV paths.
    Decks are keyed by source_path `easyworship://song/<song_uid>` (stable
    across library versions), so re-import updates in place.

    Returns {"imported": n_new, "updated": n_updated, "skipped": n_skipped,
             "failed": [(title, error), ...]}.
    """
    if data_dir:
        songs = read_songs_from_db(data_dir)
    elif songs_csv and words_csv:
        songs = read_songs_from_csv(songs_csv, words_csv)
    else:
        raise ValueError("Provide either data_dir or both songs_csv and words_csv")

    imported = updated = skipped = 0
    failed: list[tuple[str, str]] = []

    for song in songs:
        title = song["title"].strip() or "(untitled)"
        try:
            if not song["rtf"]:
                if skip_empty:
                    skipped += 1
                    continue
                slides: list[dict] = []
            else:
                slides = rtf_to_slides(song["rtf"])
                if not slides and skip_empty:
                    skipped += 1
                    continue

            source_path = f"{_EW_SOURCE_PREFIX}{song['song_uid'] or song['ew_rowid']}"
            tags = "easyworship"
            if song["copyright"] and song["copyright"].lower() != "public domain":
                tags += ",copyrighted"

            deck = create_deck_from_slides(
                title=title,
                slides=slides,
                author=song["author"],
                ccli=song["reference_number"],
                tags=tags,
                source_path=source_path,
                raw_text=song["rtf"],
            )
            if deck["_was_created"]:
                imported += 1
            else:
                updated += 1
        except Exception as e:
            failed.append((title, str(e)))

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }
