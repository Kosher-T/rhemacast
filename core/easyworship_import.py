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
  - Size-overridden runs (translations in smaller type, custom slides)
    carry explicit \\fsN + \\sdfsreal instead of the auto token — the
    token search misses them, so _rtf_fallback_text recovers them by
    stripping size/style metadata groups (fonttbl/colortbl blocks stay
    excluded as header noise)
  - A paragraph block WITHOUT \\fntnamaut but WITH \\li0/\\sb0 controls is an
    EMPTY line = slide boundary (single blank splits slides here, unlike our
    txt format's double-blank rule)
  - Blocks with neither are RTF header noise (fonttbl/colortbl/pnseclvl...)
  - Section headers are standalone lines like "Verse 1", "Chorus", "Bridge",
    "Vamp" (named set deliberately small — visible lyric lines never match it)
  - EW2 hidden template-style blocks carry makeshift labels most libraries
    actually use: bare slide numbers ("1", "2"), "Vamp", mid-song "Song N"
    medley joints, plus bracketed ([CHORUS], [Verse 2][2X]), repeat
    qualifiers (Chorus (repeat), Vamp (repeat 12x)), dash variants
    (Pre – Chorus), and further words (Refrain, Interlude, Chant, Rap,
    OUT->Outro, Vamp 1-3) — all collapsed by normalize_section_label.
    Repeat-only counts (x8, [2X]), Keyterms:, [...], director notes, and a
    leading "Song 1" title echo stay dropped. A bare "1999" in
    visible lyrics is untouched (hidden-gated, verified zero occurrences
    across 225 old-dialect songs).
  - A section can span multiple slides: continuation slides after a blank
    inherit the current section (no repeated header)

Translated songs pair every line (vernacular + parenthesized English); a
song either has translations throughout or none at all — see
verify_song_import, which flags dropped content and unpaired lines.
"""

import csv
import os
import re
import sqlite3

from core.slide_service import create_deck_from_slides
from core.database import get_connection, init_db

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
    r"^(verse|chorus|bridge|tag|vamp|pre-?chorus|prechorus|ending|intro|outro|"
    r"v\s*\d*|c\s*\d*|b\s*\d*|t\s*\d*)"
    r"(\s+\d+)?$",
    re.IGNORECASE,
)

# Makeshift labels live ONLY in hidden (template-style) blocks — EW hides
# them on screen and most libraries number slides ("1", "2") or mark vamps
# and medley joints ("Song 2") there instead of named headers. Visible lyric
# lines never match this (a visible "1999" stays a lyric); the old-dialect
# visible path below keeps using is_section_header unchanged.
_HIDDEN_SONGN_RE = re.compile(r"^song \d+$", re.IGNORECASE)


def is_section_header(line: str) -> bool:
    """True if a lyric line is an EasyWorship section marker ('Verse 1', 'Chorus', ...)."""
    return bool(_SECTION_RE.match(line.strip()))


# Canonical section base words. Hidden labels arrive in every casing and
# wrapping imaginable ([CHORUS], Chorus (repeat), Pre – Chorus); the map
# below is what they all collapse to. Deliberately closed: EW puts real
# ANNOTATIONS (titles, credits, Keyterms:, schedule notes) in the very same
# hidden blocks, and promoting those to sections is worse than dropping an
# odd label. Unknown annotations stay dropped and are REPORTED by
# audit_section_labels() so the operator can send evidence, not guesses.
_SECTION_WORDS = {
    "verse": "Verse", "chorus": "Chorus", "bridge": "Bridge",
    "tag": "Tag", "vamp": "Vamp", "pre-chorus": "Pre-Chorus",
    "prechorus": "Pre-Chorus", "ending": "Ending", "intro": "Intro",
    "outro": "Outro", "out": "Outro", "interlude": "Interlude",
    "refrain": "Refrain", "chant": "Chant", "rap": "Rap",
    "pre-verse": "Pre-Verse", "preverse": "Pre-Verse",
    "post-chorus": "Post-Chorus", "postchorus": "Post-Chorus",
    "post-verse": "Post-Verse", "postverse": "Post-Verse",
    "hook": "Hook", "response": "Response", "coda": "Coda",
    "break": "Break", "instrumental": "Instrumental",
    "instrumental break": "Instrumental",
}
_SECTION_SINGLE = {"v": "V", "c": "C", "b": "B", "t": "T"}
# A whole label that is only a repeat count (x8, 2X, [2X]) — not a section.
_REPEAT_ONLY_RE = re.compile(r"^(?:x\d+|\d+x)$", re.IGNORECASE)
# Repeat qualifiers to strip: (repeat), (repeat 12x), [Repeat], [2X],
# (repeat twice), (repeat 3 times), [Repeat ad infinitum].
_REPEAT_QUAL_RE = re.compile(
    r"\s*[\(\[]\s*(?:repeat(?:\s+ad\s+infinitum|\s+twice|\s+\d+\s*times?|"
    r"\s+\d+\s*x?|\s*x\d+)?|\d+\s*x|x\d+)\s*[\)\]]",
    re.IGNORECASE)
_DASH_RE = re.compile(r"[–—]")
# EW writes a color hint INSIDE label text: "[Verse 2: (#333399)]". Left
# in place it defeated every label pattern and the section vanished.
_COLOR_HINT_RE = re.compile(r"\(\s*#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\s*\)")
# Leftover RTF metadata tokens ("\*48.5999…") — see _rtf_block_text.
_RTF_METADATA_RE = re.compile(r"\\\*\d*\.?\d+")
# An ellipsis placeholder: EW's stand-in for a section the publisher left
# unnamed ("[...]", "(...)", "…"). It sits in the label block exactly like
# [CHORUS] does, so it IS a section boundary — dropping it left everything
# after it wearing the previous section's name (a whole bridge + the final
# chorus came back labeled "Verse 3").
_PLACEHOLDER_RE = re.compile(
    r"^[\s\[\(]*(?:\.{2,}|\u2026+)[\s\]\)]*$")
# Annotations that share the label block but are never sections.
_ANNOTATION_PREFIX_RE = re.compile(
    r"(?i)^(key\s?terms?|keywords?|search\s+terms?|notes?|for\s+|by\s+|"
    r"do\s+not\s+use|copyright|ccli|version\s+\d+|arr\.|arranger|"
    r"repeat\s+(?:the\s+)?(?:verse|chorus)|just\s+in\s+case)")


def is_placeholder_label(text: str) -> bool:
    """True for EW's unnamed-section placeholder ('[...]').

    Cleans first, so it still fires on '[...][REPEAT]' and friends — the
    repeat qualifier rides along on the same block.
    """
    t = _REPEAT_QUAL_RE.sub(" ", _clean_label_text(text)).strip()
    return bool(_PLACEHOLDER_RE.match(t))


# Invisible formatting characters that ride along invisibly: LRM/RLM (a
# "CHORUS" label arrived as U+200ECHORUS), BOM, soft hyphen, zero-width.
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff\u00ad]")
# Section words written with a space instead of a hyphen ("PRE CHORUS").
_SPACE_JOIN_RE = re.compile(r"(?i)\b(pre|post)\s+(chorus|verse|vamp|bridge)\b")


def _clean_label_text(text: str) -> str:
    """Normalize the raw hidden-block text into something matchable."""
    t = _INVISIBLE_RE.sub("", text or "")
    t = _SPACE_JOIN_RE.sub(r"\1-\2", t)
    t = _RTF_METADATA_RE.sub("", _COLOR_HINT_RE.sub("", t))
    t = _DASH_RE.sub("-", t)
    t = re.sub(r"\s*-\s*", "-", t)
    # Compound labels are written inconsistently: "Bridge/Vamp",
    # "Bridge / Vamp", "Bridge & Vamp" all mean the same marker.
    t = re.sub(r"\s*([/+&])\s*", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Trailing colons are decoration ("Refrain:", "VERSE 1:").
    t = t.strip(" :,–—-")
    return t


def _canonical_word(word: str) -> str | None:
    """Map one label word to its canonical section name.

    Handles the morphology EW actually produces: plurals ("Chants"),
    "pre-/post-" affixes, and single letters.
    """
    w = word.lower().strip("-,: ")
    if not w:
        return None
    if w in _SECTION_WORDS:
        return _SECTION_WORDS[w]
    if w in _SECTION_SINGLE:
        return _SECTION_SINGLE[w]
    # Plurals: "Chants" -> "Chant", "Vamps" -> "Vamp".
    if w.endswith("s") and w[:-1] in _SECTION_WORDS:
        return _SECTION_WORDS[w[:-1]]
    return None


def normalize_section_label(text: str) -> str | None:
    """Hidden label -> canonical section name, or None to drop it.

    Handles bracket wrapping ([Verse 1], [CHANT][2X]), EW color hints
    ([Verse 2: (#333399)]), trailing colons (Refrain:), repeat qualifiers
    (Chorus (repeat), Vamp (repeat 12x), Bridge (repeat twice)), dash
    variants (Pre – Chorus), plurals (Chants), affixes (Post-Chorus), solo
    qualifiers (Verse (Solo 1)), and bare 1-3 digit numbers (slide
    numbers). Ellipsis placeholders return None here — rtf_to_slides names
    them per song (is_placeholder_label), since the name is positional.

    Anything else — Keyterms:, song titles, credits, director notes — is
    None, matching EW hiding them on screen.
    """
    t = _clean_label_text(text)
    if not t:
        return None
    if _REPEAT_ONLY_RE.match(t):
        return None
    # A trailing repeat count glued to the word: "Chorus x2", "Verse 1 x2".
    # Not a separate marker — the section, sung twice.
    t = re.sub(r"\s+x\d+\s*$", "", t, flags=re.IGNORECASE).strip()
    # Strip repeat qualifiers wherever they ride along.
    t = _REPEAT_QUAL_RE.sub(" ", t).strip()
    if not t or _REPEAT_ONLY_RE.match(t) or _PLACEHOLDER_RE.match(t):
        return None
    # Unwrap ONE balanced outer bracket pair: [Verse 1], [CHANT].
    if len(t) >= 2 and t[0] == "[" and t[-1] == "]" \
            and t.count("[") == 1 and t.count("]") == 1:
        # Re-clean inside: '[Verse 2: (#333399)]' cleaned to '[Verse 2:]',
        # so the colon only surfaces once the brackets are off.
        t = _clean_label_text(t[1:-1])
        if not t:
            return None
    # Bare slide numbers.
    if re.fullmatch(r"\d{1,3}", t):
        return t
    if _ANNOTATION_PREFIX_RE.match(t):
        return None
    m = re.match(r"^([A-Za-z]+(?:[-/+&][A-Za-z]+)*)\s*(\d*)\s*(\([^()]*\))?$", t)
    if not m:
        return None
    word, num, qual = m.group(1).lower(), m.group(2), m.group(3)
    # Compound labels EW writes as one word: "Bridge/Vamp", "Chorus+Vamp".
    if re.search(r"[/+&]", word):
        parts = [p for p in re.split(r"[/+&]", word) if p]
        names = [_canonical_word(p) for p in parts]
        if parts and all(names):
            out = " / ".join(names)
            return out + (f" {num}" if num else "")
        return None
    base = _canonical_word(word)
    if base is None:
        return None
    out = base + (f" {num}" if num else "")
    if qual:
        inner = qual[1:-1].strip()
        if not inner or re.match(
                r"(?i)^(repeat.*|ad\s+infinitum|\d+\s*x|x\d+)$", inner):
            return out
        out += f" ({inner.title()})"
    return out


def _rtf_unescape(text: str) -> str:
    """Full RTF-tail cleanup pipeline. ORDER MATTERS:

    1. Protect literal backslashes (\\\\) so later steps can't eat them.
    2. Decode \\'hh (cp1252) escapes.
    3. Decode \\uN? unicode escapes (consuming the single-char fallback).
    4. Strip remaining control words (\\f1, \\shad0, ...).
    5. Unescape \\{ / \\}, drop leftover braces, restore backslashes.
    6. Normalize exotic spacing (nbsp, thin/medium/em space) to ASCII space.

    Steps 2–3 MUST precede step 4: the control-word pattern would otherwise
    eat the \\uNNN token and orphan its '?' fallback in the lyrics.
    """
    text = text.replace("\\\\", "\x00")
    text = re.sub(r"\\'([0-9a-fA-F]{2})", _hex_repl, text)
    # \uN followed by optional fallback char represented as '?'
    text = re.sub(r"\\u(-?\d+)\s*\??", _uni_repl, text)
    text = _CTRL_WORD_RE.sub("", text)
    text = text.replace(r"\{", "{").replace(r"\}", "}")
    text = text.replace("{", "").replace("}", "")
    text = _SPACE_CHARS_RE.sub(" ", text)
    # NOTE: no strip() here — color-run segmentation preserves boundary whitespace
    return text.replace("\x00", "\\")


def _hex_repl(m):
    try:
        return bytes.fromhex(m.group(1)).decode("cp1252")
    except ValueError:
        return m.group(0)


def _uni_repl(m):
    try:
        code = int(m.group(1))
        if code < 0:
            code += 0x10000
        return chr(code)
    except (ValueError, OverflowError):
        return m.group(0)


# \colortbl: {\colortbl ;\red51\green51\blue153;} (also matches {\*\colortbl})
# Index 0 = default/auto; index N = Nth listed color.
_COLORTBL_RE = re.compile(r"\\(?:\*\\?)?colortbl([^{}]+)")
_COLOR_DEF_RE = re.compile(r"\\red(\d+)\\green(\d+)\\blue(\d+)")
_CF_SPLIT_RE = re.compile(r"\\cf(-?\d+)")
# Remaining RTF control words inside a color segment (\sdnotstroke, \shad0...)
# NOTE: must NOT run before \'hh / \uN decoding (it would eat the \uNNN part
# and leave the fallback '?' behind). _rtf_unescape() applies this last.
_CTRL_WORD_RE = re.compile(r"\\(?:\*)?[a-zA-Z]+(?:-?\d+)?[ ]?")
# Exotic spacing variants (nbsp, thin/medium/em spaces) → plain ASCII space
# so lyrics render and tokenize identically everywhere.
_SPACE_CHARS_RE = re.compile("[\u00a0\u2000-\u200b\u202f\u205f\u3000]")


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
        return _rtf_unescape(tail)

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
        cleaned = _rtf_unescape(part)
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


# Size/style metadata groups ({\*\sdfsreal 39}, {\*\sdfsdef 42},
# {\*\sdasfactor 0}): never lyrics, stripped before fallback extraction.
_METADATA_GROUP_RE = re.compile(r"\{\\\*\\s(?:dfs(?:real|def)|das\w+)[^}]*\}")


def _rtf_fallback_text(block: str, palette: dict[int, str] | None = None,
                       ) -> str | None:
    """Extract display text from a paragraph block with NO style token.

    Size-overridden runs (translations in smaller type, custom slides)
    carry explicit \\fsN + \\sdfsreal instead of \\sdfsauto/\\fntnamaut,
    so the token search misses them — and with them whole translations.
    Anything that survives metadata stripping here was displayed by EW.
    Returns None for header noise (fonttbl/colortbl/stylesheet) and
    non-paragraph blocks.
    """
    if ("fonttbl" in block or "colortbl" in block or "stylesheet" in block):
        return None
    if "\\pard" not in block and not block.startswith("d\\"):
        return None
    t = _METADATA_GROUP_RE.sub("", block)
    # "\par"-split remnant: the delimiter's "\par" is consumed, leaving "d\".
    t = re.sub(r"^d(?=\\)", "", t)
    if palette is None:
        palette = {}
    if "\\cf" in t:
        text = _color_runs_to_markup(t, palette)
    else:
        text = _rtf_unescape(t)
    text = text.strip()
    return text or None


def _rtf_block_text(block: str, palette: dict[int, str] | None = None) -> str | None:
    """Extract display text from one RTF paragraph block.

    Returns None if the block carries no text token. Tries fntnamaut (old
    dialect) before sdfsauto (EW2 dialect); sequential find() avoids the
    earliest-match trap of a combined regex alternation. \\cf color runs are
    converted to [text: (#hex)] inline markup. Token-less content blocks
    fall back to metadata-stripped extraction (size-overridden translations
    and custom slides carry explicit runs instead of the auto token).

    The style-token path strips size/style metadata groups FIRST, exactly
    like the fallback path. A paragraph can hold more than one run — EW
    writes a second `\\sdfsauto` after the first run's text — and those
    trailing groups used to survive into the text as literal
    "\\*48.5999…", which then made the whole label unrecognizable
    ("VERSE\\*48.6…") and silently dropped the section.
    """
    for token in ("\\fntnamaut", "\\sdfsauto"):
        idx = block.find(token)
        if idx != -1:
            tail = _METADATA_GROUP_RE.sub("", block[idx + len(token):])
            if palette is None:
                palette = {}
            return _color_runs_to_markup(tail, palette)
    return _rtf_fallback_text(block, palette)


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
    placeholder_count = 0

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
            # EW hides these lines on screen: named headers (Verse/Chorus/…,
            # Vamp, Refrain, Interlude, Chant, Rap, OUT->Outro, Vamp 1-3)
            # become sections, as do bare slide numbers ("1", "2") and
            # mid-song "Song N" medley joints. Repeat qualifiers
            # ((REPEAT), [2X], x8), Keyterms:, director notes and a
            # leading "Song 1" title echo stay dropped like EW does.
            if _HIDDEN_SONGN_RE.match(stripped) and (slides or buf):
                flush()
                current_section = stripped.title()
                continue
            # "[...]" — EW's unnamed-section placeholder. It sits in the
            # label block like [CHORUS] does, so it starts a section; the
            # name is positional ("Section", "Section 2", …) because the
            # source has nothing to call it. Dropping it instead left every
            # following slide wearing the PREVIOUS section's name.
            if is_placeholder_label(stripped):
                flush()
                placeholder_count += 1
                current_section = ("Section" if placeholder_count == 1
                                   else f"Section {placeholder_count}")
                continue
            section = normalize_section_label(stripped)
            if section is not None:
                flush()
                current_section = section
            continue

        if not ew2 and is_section_header(stripped):
            flush()
            current_section = stripped.title()
            continue

        buf.append(stripped)

    flush()
    return slides


# ── Verification ─────────────────────────────────────────────────────────────

def verify_song_import(rtf: str, slides: list[dict]) -> dict:
    """Check one song's import for dropped content and translation gaps.

    dropped: visible RTF content lines missing from the slides (the
      size-overridden-run bug class — translations in smaller type with
      no style token). Hidden labels/noise are out of scope here; label
      handling is pinned by unit tests on normalize_section_label.
    translation_gaps: song-wide line numbers where a lyric line has no
      following parenthesized line, in a song that HAS translations.
      Translated songs pair every line (a song either has translations
      throughout or none at all), so a gap means a dropped translation —
      or a rare ad-lib pattern worth a human glance.
    has_translations: whether any slide line is parenthesized.
    """
    from core.slide_parser import strip_inline_markup
    palette = parse_color_palette(rtf or "")
    visible: list[str] = []
    for block in re.split(r"\\par", rtf or ""):
        if "\\sdslidemarker" in block:
            continue
        if "\\sdparawysiwghidden" in block \
                or "sdewparatemplatestyle102" in block:
            continue
        text = _rtf_block_text(block, palette)
        if text and text.strip():
            # Old-dialect section headers become the section NAME, not
            # slide text — counting them as missing lyrics reported every
            # labelled song as broken. Hymn lyrics EW writes as literal
            # markup ("[Oh! precious is the flow,: (#333399)]") are kept
            # as markup in the deck, so both sides compare rendered.
            if is_section_header(text):
                continue
            rendered = strip_inline_markup(text).strip()
            if rendered:
                visible.append(rendered)
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    flat = norm("\n".join(
        strip_inline_markup(s.get("text", "")) for s in slides))
    dropped = [v for v in visible if norm(v) not in flat]
    lines = [ln.strip() for s in slides
             for ln in s.get("text", "").split("\n")]
    lines = [ln for ln in lines if ln]
    paren = [ln.startswith("(") and ln.endswith(")") for ln in lines]
    has_translations = any(paren)
    gaps: list[int] = []
    if has_translations:
        for i, ln in enumerate(lines):
            if paren[i]:
                continue
            if not (i + 1 < len(lines) and paren[i + 1]):
                gaps.append(i)
    return {"dropped": dropped, "translation_gaps": gaps,
            "has_translations": has_translations}


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


# ── Label audit ───────────────────────────────────────────────────────────

def audit_section_labels(data_dir: str, *, limit: int = 40) -> dict:
    """Inventory every hidden annotation in an EasyWorship data dir.

    Labels and non-labels share ONE hidden block style in EW2 (template
    style 102, list level -1) — measured across the database, not assumed —
    so the label decision comes from the text. This walks every song and
    reports each hidden annotation with the verdict and reason:

      {"section": name}      became a section
      {"number": "3"}        slide-number label
      {"medley": "Song 2"}   mid-song medley joint
      {"placeholder": …}     unnamed-section placeholder
      None                   dropped (annotation, repeat count, unknown)

    Unknown dropped text is the actionable part: it is how a mislabeled
    song gets reported with evidence instead of a guess. Read-only.
    """
    songs = read_songs_from_db(data_dir)
    kept: dict = {}
    dropped: dict = {}

    for song in songs:
        rtf = song.get("rtf") or ""
        if not rtf:
            continue
        palette = parse_color_palette(rtf)
        title = song.get("title") or "(untitled)"
        # Mirrors rtf_to_slides so the audit reports the names the importer
        # will actually use (placeholders are numbered per song).
        placeholders = 0
        for block in re.split(r"\\par", rtf):
            if "\\sdparawysiwghidden" not in block \
                    and "sdewparatemplatestyle102" not in block:
                continue
            text = (_rtf_block_text(block, palette) or "").strip()
            if not text:
                continue
            if re.fullmatch(r"\d{1,3}", text):
                bucket, key, value = kept, "number", text
            elif _HIDDEN_SONGN_RE.match(text):
                bucket, key, value = kept, "medley", text.title()
            elif is_placeholder_label(text):
                placeholders += 1
                bucket, key = kept, "placeholder"
                value = ("Section" if placeholders == 1
                         else f"Section {placeholders}")
            else:
                section = normalize_section_label(text)
                if section is not None:
                    bucket, key, value = kept, "section", section
                else:
                    bucket, key, value = dropped, text, None
            stats = bucket.setdefault(key if value is None else value,
                                      {"count": 0, "songs": []})
            stats["count"] += 1
            if len(stats["songs"]) < limit:
                stats["songs"].append(title)

    return {
        "songs": len(songs),
        "kept": kept,
        "dropped": dropped,
        "dropped_total": sum(v["count"] for v in dropped.values()),
    }


def format_label_audit(audit: dict) -> str:
    """Human-readable report for audit_section_labels()."""
    lines = [f"EasyWorship label audit — {audit['songs']} songs", ""]
    lines.append(f"KEPT as labels ({sum(v['count'] for v in audit['kept'].values())}):")
    for key, stats in sorted(audit["kept"].items(),
                             key=lambda kv: -kv[1]["count"]):
        lines.append(f"  {stats['count']:5d}  {key}")
    lines.append("")
    lines.append(f"DROPPED as annotations ({audit['dropped_total']} blocks, "
                 f"{len(audit['dropped'])} distinct):")
    for text, stats in sorted(audit["dropped"].items(),
                              key=lambda kv: -kv[1]["count"]):
        first = stats["songs"][0] if stats["songs"] else ""
        lines.append(f"  {stats['count']:5d}  {text!r}  e.g. {first}")
    return "\n".join(lines)


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

def _song_source_path(song: dict) -> str:
    """Stable deck key for a song (mirrors the import loop)."""
    return f"{_EW_SOURCE_PREFIX}{song.get('song_uid') or song['ew_rowid']}"


def _existing_source_paths() -> set:
    """Source paths already in slide_decks (one round trip)."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT source_path FROM slide_decks WHERE source_path LIKE ?",
            (_EW_SOURCE_PREFIX + "%",),
        ).fetchall()
    finally:
        conn.close()
    return {r["source_path"] for r in rows if r["source_path"]}


def count_existing_easyworship(data_dir: str) -> tuple:
    """How many songs in `data_dir` are already in slide_decks.

    Returns (existing_count, total_count). Read-only: for the import
    dialog, so the operator decides skip-vs-overwrite informed.
    """
    songs = read_songs_from_db(data_dir)
    existing = _existing_source_paths()
    n = sum(1 for s in songs if _song_source_path(s) in existing)
    return n, len(songs)

def import_easyworship(
    data_dir: str | None = None,
    songs_csv: str | None = None,
    words_csv: str | None = None,
    skip_empty: bool = True,
    on_existing: str = "overwrite",
) -> dict:
    """Import EasyWorship songs into slide_decks.

    Either provide `data_dir` (Songs.db/SongWords.db) or both CSV paths.
    Decks are keyed by source_path `easyworship://song/<song_uid>` (stable
    across library versions).

    `on_existing`: "overwrite" (default, current behavior — re-import
    updates in place) or "skip" (songs already in the library are left
    untouched and counted as `skipped_existing`).

    Returns {"imported": n_new, "updated": n_updated, "skipped": n_skipped,
             "skipped_existing": n, "failed": [(title, error), ...]}.
    """
    if on_existing not in ("overwrite", "skip"):
        raise ValueError("on_existing must be 'overwrite' or 'skip'")
    if data_dir:
        songs = read_songs_from_db(data_dir)
    elif songs_csv and words_csv:
        songs = read_songs_from_csv(songs_csv, words_csv)
    else:
        raise ValueError("Provide either data_dir or both songs_csv and words_csv")

    imported = updated = skipped = skipped_existing = 0
    failed: list[tuple[str, str]] = []
    known = _existing_source_paths() if on_existing == "skip" else set()

    for song in songs:
        title = song["title"].strip() or "(untitled)"
        try:
            if on_existing == "skip" \
                    and _song_source_path(song) in known:
                skipped_existing += 1
                continue
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
        "skipped_existing": skipped_existing,
        "failed": failed,
    }


def _main(argv: list[str] | None = None) -> int:
    """CLI: `python -m core.easyworship_import --audit <EasyWorship Data dir>`.

    Read-only report of every hidden annotation and the section it became.
    Exists so a mislabeled song can be reported with evidence (the exact
    raw label + the song it came from) instead of a guess.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--audit", metavar="DATA_DIR",
                        help="print the section-label audit for this "
                             "EasyWorship Data dir and exit")
    args = parser.parse_args(argv)
    if args.audit:
        print(format_label_audit(audit_section_labels(args.audit)))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
