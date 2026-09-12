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
