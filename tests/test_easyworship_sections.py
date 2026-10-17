"""EasyWorship makeshift section labels (pure RTF fixtures, no DB).

Hidden template-style blocks carry the labels most libraries actually use
(bare slide numbers, Vamp, mid-song Song N) — verified against 1219 real
songs: numeric labels precede lyric content 1568:6, and zero old-dialect
songs contain bare-number lyric lines.
"""

from core.easyworship_import import rtf_to_slides, is_section_header

def _hidden(text: str) -> str:
    return r"{\sdewparatemplatestyle102\plain\sdfsauto " + text + "}"


TXT = r"{\sdewparatemplatestyle101\plain\sdfsauto "


def _rtf(*blocks: str) -> str:
    return r"{\rtf1\ansi" + "".join(b + r"\par " for b in blocks) + "}"


def _text(text: str) -> str:
    return TXT + text + "}"


def test_hidden_numbers_become_sections():
    slides = rtf_to_slides(_rtf(
        _hidden("1"), _text("Line one"), _text("Line two"),
        _hidden("2"), _text("Line three"),
    ))
    assert [(s["section"], s["text"]) for s in slides] == [
        ("1", "Line one\nLine two"),
        ("2", "Line three"),
    ]


def test_hidden_title_echo_dropped_but_medley_kept():
    slides = rtf_to_slides(_rtf(
        _hidden("Song 1"), _text("First song line"),
        _hidden("Song 2"), _text("Second song line"),
    ))
    assert [(s["section"], s["text"]) for s in slides] == [
        (None, "First song line"),
        ("Song 2", "Second song line"),
    ]


def test_hidden_vamp_and_named_headers():
    assert is_section_header("VAMP")
    assert is_section_header("Vamp 1")
    slides = rtf_to_slides(_rtf(
        _hidden("VAMP"), _text("Repeat after me"),
    ))
    assert slides == [{"section": "Vamp", "text": "Repeat after me"}]


def test_hidden_noise_stays_dropped():
    slides = rtf_to_slides(_rtf(
        _hidden("TUESDAY PRAISE NIGHT"), _hidden("x8"), _text("Real lyric"),
    ))
    assert slides == [{"section": None, "text": "Real lyric"}]


def test_visible_numbers_stay_lyrics():
    # Old-dialect visible lines are never treated as labels.
    slides = rtf_to_slides(_rtf(_text("In the year 1999"), _text("42")))
    assert slides == [{"section": None, "text": "In the year 1999\n42"}]


# ── Skip-vs-overwrite (DB-backed) ─────────────────────────────────────

def _make_library(data_dir, words_by_uid):
    """Fabricate Songs.db + SongWords.db inside data_dir. Returns it."""
    import sqlite3
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(data_dir / "Songs.db"))
    conn.execute(
        "CREATE TABLE song (song_uid TEXT, title TEXT, author TEXT,"
        " copyright TEXT, administrator TEXT, reference_number TEXT)")
    for i, (uid, _words) in enumerate(words_by_uid, start=1):
        conn.execute(
            "INSERT INTO song (rowid, song_uid, title) VALUES (?, ?, ?)",
            (i, uid, f"Song {uid}"))
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(data_dir / "SongWords.db"))
    conn.execute("CREATE TABLE word (song_id INTEGER, words TEXT)")
    for i, (_uid, words) in enumerate(words_by_uid, start=1):
        conn.execute("INSERT INTO word (song_id, words) VALUES (?, ?)",
                     (i, words))
    conn.commit()
    conn.close()
    return str(data_dir)


def _use_tmp_db(tmp_path):
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()


def test_skip_existing_leaves_deck_untouched(tmp_path):
    from core.easyworship_import import import_easyworship
    from core.slide_service import get_deck
    rtf = _rtf(_text("Line one"))
    data_dir = _make_library(tmp_path / "ewdata", [("uid-1", rtf), ("uid-2", rtf)])
    _use_tmp_db(tmp_path)
    first = import_easyworship(data_dir=data_dir)
    assert (first["imported"], first["updated"]) == (2, 0)
    before = get_deck(1)
    second = import_easyworship(data_dir=data_dir, on_existing="skip")
    assert second["imported"] == 0
    assert second["updated"] == 0
    assert second["skipped_existing"] == 2
    assert get_deck(1)["slides_json"] == before["slides_json"]


def test_overwrite_updates_existing(tmp_path):
    from core.easyworship_import import (
        import_easyworship, count_existing_easyworship,
    )
    from core.slide_service import get_deck
    data_dir = _make_library(tmp_path / "ewdata", [("uid-1", _rtf(_text("Old")))])
    _use_tmp_db(tmp_path)
    import_easyworship(data_dir=data_dir)
    assert count_existing_easyworship(data_dir) == (1, 1)
    data_dir2 = _make_library(tmp_path / "v2", [("uid-1", _rtf(_text("New")))])
    third = import_easyworship(data_dir=data_dir2)
    assert third["updated"] == 1
    assert "New" in get_deck(1)["slides_json"]


def test_invalid_on_existing_rejected(tmp_path):
    from core.easyworship_import import import_easyworship
    import pytest
    _use_tmp_db(tmp_path)
    with pytest.raises(ValueError):
        import_easyworship(data_dir=str(tmp_path), on_existing="merge")


# ── Section label normalizer ────────────────────────────────────────────

def test_normalize_bracketed_and_repeat_labels():
    from core.easyworship_import import normalize_section_label as norm
    assert norm("[Verse]") == "Verse"
    assert norm("[CHORUS]") == "Chorus"
    assert norm("[Verse 1]") == "Verse 1"
    assert norm("[Verse 2][2X]") == "Verse 2"
    assert norm("[CHANT][2X]") == "Chant"
    assert norm("[VERSE 1] [REPEAT]") == "Verse 1"
    assert norm("[Chorus] (Repeat)") == "Chorus"
    assert norm("VERSE (REPEAT)") == "Verse"
    assert norm("Chorus (repeat)") == "Chorus"
    assert norm("Vamp (repeat 12x)") == "Vamp"
    assert norm("Pre-chorus (repeat)") == "Pre-Chorus"
    assert norm("Bridge (repeat)") == "Bridge"
    assert norm("Verse [Repeat]") == "Verse"


def test_normalize_new_words_and_dashes():
    from core.easyworship_import import normalize_section_label as norm
    assert norm("Refrain") == "Refrain"
    assert norm("Interlude") == "Interlude"
    assert norm("Chant") == "Chant"
    assert norm("Rap") == "Rap"
    assert norm("OUT") == "Outro"
    assert norm("Vamp 1") == "Vamp 1"
    assert norm("Vamp 3") == "Vamp 3"
    assert norm("Pre \u2013 Chorus") == "Pre-Chorus"
    assert norm("PRE-CHORUS") == "Pre-Chorus"
    assert norm("[PRE-VERSE]") == "Pre-Verse"
    assert norm("VERSE (SOLO 1)") == "Verse (Solo 1)"
    assert norm("Bridge 1") == "Bridge 1"
    assert norm("1") == "1"
    assert norm("12") == "12"


def test_normalize_drops_noise():
    from core.easyworship_import import normalize_section_label as norm
    assert norm("x8") is None
    assert norm("x2") is None
    assert norm("[2X]") is None
    assert norm("2X") is None
    assert norm("Keyterms: tamuno") is None
    assert norm("[...]") is None
    assert norm("[Dunno what this is]") is None
    assert norm("(Just in case they sing it)") is None
    assert norm("[Or]") is None
    assert norm("Song 2") is None  # medley joints stay contextual
    assert norm("1999") is None  # years are never sections
    assert norm("TUESDAY PRAISE NIGHT") is None
    assert norm("") is None


def test_hidden_bracketed_labels_become_sections():
    slides = rtf_to_slides(_rtf(
        _hidden("[CHORUS]"), _text("Sing along"),
        _hidden("Vamp (repeat 12x)"), _text("Oh yeah"),
        _hidden("Keyterms: foo"), _text("More lines"),
    ))
    assert [(s["section"], s["text"]) for s in slides] == [
        ("Chorus", "Sing along"),
        ("Vamp", "Oh yeah\nMore lines"),
    ]


# ── Token-less (size-overridden) blocks ─────────────────────────────────

def _sized(text: str, size: int = 39) -> str:
    return (r"{\pard\qc\sdewparatemplatestyle101\plain\fs%d"
            r"{\*\sdfsreal %d}{\*\sdfsdef 42}%s}" % (size + 39, size, text))


def test_sized_translation_blocks_survive():
    # Madu Nile Na-asi Ebube shape: translation in smaller type carries
    # explicit size runs instead of the \sdfsauto token.
    slides = rtf_to_slides(_rtf(
        _hidden("1"),
        _text("Ebube Jehovah, mara mma"),
        _sized("(Glorious Jehovah, you are beautiful)"),
    ))
    assert [(s["section"], s["text"]) for s in slides] == [
        ("1", "Ebube Jehovah, mara mma\n(Glorious Jehovah, you are beautiful)"),
    ]


def test_sized_verse_lines_survive():
    slides = rtf_to_slides(_rtf(
        _text("First line"),
        _sized("Second line, smaller type"),
    ))
    assert [s["text"] for s in slides] == [
        "First line\nSecond line, smaller type",
    ]


def test_fallback_ignores_header_noise():
    from core.easyworship_import import _rtf_fallback_text
    assert _rtf_fallback_text(r"{\fonttbl{\f0 Tahoma;}}") is None
    assert _rtf_fallback_text(r"{\colortbl ;}") is None
    assert _rtf_fallback_text(r"{\rtf1\ansi\deff0}") is None
    assert _rtf_fallback_text(
        r"{\pard\qc{\*\sdfsreal 42}{\*\sdfsdef 42}}") is None


# ── Verification ────────────────────────────────────────────────────────

def test_verify_flags_dropped_translation():
    from core.easyworship_import import verify_song_import
    rtf = _rtf(
        _hidden("1"),
        _text("Line one"),
        _text("(Translation one)"),
        _text("Line two"),
        _text("(Translation two)"),
    )
    slides = rtf_to_slides(rtf)
    assert verify_song_import(rtf, slides)["translation_gaps"] == []
    broken = [dict(s) for s in slides]
    broken[-1]["text"] = ("Line one\n(Translation one)\nLine two"
                          )  # last translation lost, as Madu was
    assert verify_song_import(rtf, broken)["translation_gaps"] == [2]
    assert verify_song_import(rtf, broken)["has_translations"] is True


def test_verify_clean_song_is_quiet():
    from core.easyworship_import import verify_song_import
    rtf = _rtf(_text("Line one"), _text("Line two"))
    slides = rtf_to_slides(rtf)
    out = verify_song_import(rtf, slides)
    assert out == {"dropped": [], "translation_gaps": [],
                   "has_translations": False}


# ── Label recognition: structural, not a fixed string list ─────────────────
# Every hidden block in EW2 shares one template style (102, list level -1) —
# measured across all 1219 songs, labels and annotations included. So the
# rich text identifies "hidden annotation", and the TEXT identifies the
# label. These pin the text-side rules.

def _label(text: str):
    from core.easyworship_import import normalize_section_label
    return normalize_section_label(text)


def test_ellipsis_placeholder_is_a_section_not_a_drop():
    """'[...]' is EW's unnamed-section placeholder and sits in the label
    block exactly like [CHORUS] does."""
    from core.easyworship_import import is_placeholder_label
    for text in ("[...]", "(...)", "…", "[...][REPEAT]", "[ ... ]"):
        assert is_placeholder_label(text), text
        # normalize() names it positionally in the parser, so it returns
        # None here rather than inventing a name per call.
        assert _label(text) is None, text


def test_placeholder_starts_a_section_instead_of_inheriting_the_previous():
    from core.easyworship_import import rtf_to_slides
    slides = rtf_to_slides(_rtf(
        _hidden("[VERSE 3]"), _text("Verse three line"),
        _hidden("[...]"), _text("Bridge line one"), _text("Bridge line two"),
        _hidden("[...]"), _text("Tag line"),
    ))
    assert [(s["section"], s["text"]) for s in slides] == [
        ("Verse 3", "Verse three line"),
        ("Section", "Bridge line one\nBridge line two"),
        ("Section 2", "Tag line"),
    ]


def test_color_hints_inside_labels_do_not_hide_the_section():
    """EW writes '[Verse 2: (#333399)]' — the color hint used to defeat
    every label pattern, so the section silently vanished."""
    assert _label("[Verse 2: (#333399)]") == "Verse 2"
    assert _label("[Chorus: (#333399)]") == "Chorus"
    assert _label("[1: (#333399)]") == "1"
    assert _label("[Refrain:: (#333399)]") == "Refrain"


def test_rtf_metadata_leak_does_not_break_labels():
    """A second run in the block leaked '\\*48.5999…' into the text."""
    from core.easyworship_import import rtf_to_slides
    block = (r"{\pard\sdparawysiwghidden\sdlistlevel-1\sdewparatemplatestyle102"
             r"\plain\sdewtemplatestyle101\fs98"
             r"{\*\sdfsreal 48.5999984741211}{\*\sdfsdef 48.5999984741211}"
             r"\sdfsauto VERSE" + TXT + r"{\*\sdfsreal 48.5999984741211}"
             r"{\*\sdfsdef 48.5999984741211}\sdfsauto}")
    slides = rtf_to_slides(block + r"\par " + _text("a line") + r"\par ")
    assert slides == [{"section": "Verse", "text": "a line"}]


def test_label_word_variants_collapse():
    assert _label("Refrain:") == "Refrain"           # trailing colon
    assert _label("VERSE 1:") == "Verse 1"
    assert _label("Chants") == "Chant"               # plural
    assert _label("Vamps") == "Vamp"
    assert _label("[POST – CHORUS]") == "Post-Chorus"
    assert _label("Bridge/Vamp") == "Bridge / Vamp"  # compound marker
    assert _label("Bridge & Vamp") == "Bridge / Vamp"
    assert _label("[Bridge] (repeat twice)") == "Bridge"
    assert _label("[Verse][Repeat ad infinitum]") == "Verse"
    assert _label("c") == "C" and _label("b2") == "B 2"


def test_annotations_still_dropped():
    """Dynamic recognition must not promote EW's other annotations —
    titles, credits and notes live in the same hidden block."""
    for text in ("Keyterms: tamuno", "keywords: ami nyetoro",
                 "Search terms: Ihe nemerem", "DO NOT USE | SEPARATOR",
                 "Victor's Crown by Darlene Zschech", "[Dunno what this is]",
                 "(Just in case they sing it)", "I will sing of the mercies",
                 "CALL TO WORSHIP", "x8", "All x3", "[BACK TO CHORUS]"):
        assert _label(text) is None, text


def test_label_audit_reports_kept_and_dropped_with_evidence():
    """The audit is how the next report arrives with proof instead of a
    guess: every hidden block, its verdict, and an example song."""
    import sqlite3
    from core.easyworship_import import (audit_section_labels, format_label_audit,
                                         read_songs_from_db)
    import tempfile, os
    words = ("{\\rtf1\\ansi\\sdeasyworship2"
             + _hidden("[...]") + r"\par " + _text("a lyric line") + r"\par "
             + _hidden("[CHORUS]") + r"\par " + _text("chorus line") + r"\par "
             + _hidden("Keyterms: amen") + r"\par }")
    with tempfile.TemporaryDirectory() as d:
        songs = os.path.join(d, "Songs.db")
        words_db = os.path.join(d, "SongWords.db")
        conn = sqlite3.connect(songs)
        conn.execute("CREATE TABLE song (rowid INTEGER PRIMARY KEY, song_uid TEXT,"
                     " title TEXT, author TEXT, copyright TEXT, administrator TEXT,"
                     " reference_number TEXT)")
        conn.execute("INSERT INTO song VALUES (1, 'uid-1', 'Probe Song', '', '', '', '')")
        conn.commit(); conn.close()
        conn = sqlite3.connect(words_db)
        conn.execute("CREATE TABLE word (rowid INTEGER PRIMARY KEY, song_id INTEGER,"
                     " words TEXT)")
        conn.execute("INSERT INTO word VALUES (1, 1, ?)", (words,))
        conn.commit(); conn.close()

        audit = audit_section_labels(d)
        assert audit["songs"] == 1
        assert "Section" in audit["kept"]            # the placeholder
        assert "Chorus" in audit["kept"]             # the named label
        assert "Keyterms: amen" in audit["dropped"]  # the annotation
        assert audit["dropped"]["Keyterms: amen"]["songs"] == ["Probe Song"]
        report = format_label_audit(audit)
        assert "Probe Song" in report and "Keyterms" in report
        assert read_songs_from_db(d)[0]["title"] == "Probe Song"


def test_verifier_does_not_flag_labels_or_markup_lyrics_as_lost():
    """The verifier must measure LOST LYRICS, not noise.

    Two false-positive classes it used to report: old-dialect section
    headers (they become the section name, never slide text) and hymn
    lyrics EW writes as literal markup ("[…: (#333399)]"), which the deck
    keeps as markup and renders bare.
    """
    from core.easyworship_import import rtf_to_slides, verify_song_import
    OLD_TXT = r"{\plain\f1\fntnamaut "
    rtf = (r"{\rtf1\ansi"
           + OLD_TXT + r"Chorus 1}" + r"\par "
           + OLD_TXT + r"[Oh! precious is the flow;: (#333399)]}" + r"\par "
           + OLD_TXT + r"real lyric line}" + r"\par "
           + r"{\sdewparatemplatestyle101\plain\sdfsauto trailing line}"
           + r"\par }")
    slides = rtf_to_slides(rtf)
    assert slides, "fixture should parse"
    result = verify_song_import(rtf, slides)
    assert result["dropped"] == [], result["dropped"]


def test_invisible_and_spaced_variants_still_recognize():
    """The audit found both of these in real songs: a label arrived as
    U+200ECHORUS (invisible LRM) and as "PRE CHORUS" with a space."""
    assert _label("‎CHORUS") == "Chorus"
    assert _label("﻿VAMP") == "Vamp"
    assert _label("PRE CHORUS") == "Pre-Chorus"
    assert _label("Post Verse") == "Post-Verse"
