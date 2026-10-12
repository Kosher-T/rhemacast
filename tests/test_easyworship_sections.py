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
