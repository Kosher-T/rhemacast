"""Card-invariant stress + rerender timings: every structural op must
leave the card list exactly mirroring the slide model, and every op
reports its rerender duration (op ms / settle ms). Lower is better —
the bounds below are regression guards, the printed table is the
instrument panel (run with -s to see it).
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
import pytest

import core.database as db
from core.slide_parser import slide_owns_marker

# Regression bounds (generous headless caps — the table carries truth).
SMALL_OP_MS = 500
LARGE_OP_MS = 1000
SETTLE_MS = 1500

_OPEN = []


@pytest.fixture(autouse=True)
def _close():
    yield
    while _OPEN:
        w = _OPEN.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    _qt().processEvents()


_app = None


def _qt():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


def _designer(tmp_path, raw):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    deck = create_deck(raw)
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    _qt().processEvents()
    _qt().processEvents()
    _OPEN.append(w)
    return w


def _check_invariants(w, label):
    """Every card mirrors its slide; editor hosted exactly once."""
    assert len(w._cards) == len(w._slides), \
        f"{label}: {len(w._cards)} cards vs {len(w._slides)} slides"
    hosted = 0
    for i, card in enumerate(w._cards):
        slide = w._slides[i]
        expect_chip = slide.get("section") or "" \
            if slide_owns_marker(w._slides, i) else ""
        assert card._chip.toPlainText() == expect_chip, \
            f"{label}: card {i} chip={card._chip.toPlainText()!r} want {expect_chip!r}"
        assert card._index == i, f"{label}: card {i} thinks {card._index}"
        if i == w._active:
            assert card._editor_hosted, f"{label}: active card not hosting"
            assert w._edit.document() is w._doc_for(i), \
                f"{label}: editor doc is not slide {i} doc"
            hosted += 1
        else:
            assert not card._editor_hosted, \
                f"{label}: inactive card {i} claims editor"
            box_text = card._display_box.toPlainText()
            for word in slide.get("text", "").split():
                assert word in box_text, \
                    f"{label}: card {i} box missing {word!r} (box={box_text!r})"
        assert card._display_box.height() > 0 or i == w._active, \
            f"{label}: card {i} box has zero height"
    assert hosted == 1, f"{label}: editor hosted {hosted}x"
    assert w._edit.isVisible(), f"{label}: live editor not visible"


def _timed(records, deck_size: int, op: str, fn, settle: bool = True):
    """Run fn(), record (deck_size, op, op_ms, settle_ms)."""
    import time
    t0 = time.monotonic()
    fn()
    t1 = time.monotonic()
    if settle:
        _qt().processEvents()
    t2 = time.monotonic()
    records.append((deck_size, op, (t1 - t0) * 1000.0, (t2 - t1) * 1000.0))


def _report(records):
    lines = ["\nrerender timings (op ms / settle ms):"]
    worst_op = worst_settle = 0.0
    for size, op, op_ms, settle_ms in records:
        lines.append(f"  [{size:>3} slides] {op:<28} "
                     f"op={op_ms:7.1f}  settle={settle_ms:7.1f}")
        worst_op = max(worst_op, op_ms)
        worst_settle = max(worst_settle, settle_ms)
    lines.append(f"  worst op={worst_op:.1f}ms worst settle={worst_settle:.1f}ms")
    print("\n".join(lines))
    return worst_op, worst_settle


def test_stress_section_and_structure(tmp_path):
    w = _designer(tmp_path, "# T\n\n\n*1\naaa\n\n\nbbb\n\n\n*2\nccc\n")
    w._confirm = lambda *a: True  # headless: no modal dialogs
    recs = []
    n = lambda: len(w._slides)
    _check_invariants(w, "load")

    # Empty chip -> text (the reported slow/wrong case).
    w._activate(1)
    _qt().processEvents()
    w._cards[1].set_section("1")
    _timed(recs, n(), "section commit empty->text",
           lambda: w._on_section_changed(1, "1"))
    _check_invariants(w, "empty chip gets text")

    # Text chip -> cleared.
    w._cards[2].set_section("")
    _timed(recs, n(), "section commit text->cleared",
           lambda: w._on_section_changed(2, ""))
    _check_invariants(w, "header cleared")

    # Rapid renames incl. identical-to-above.
    for name in ["X", "X", "Y", ""]:
        w._cards[0].set_section(name)
        _timed(recs, n(), f"rename to {name!r}",
               lambda: w._on_section_changed(0, name))
    _check_invariants(w, "rapid renames")

    # Structural ops.
    _timed(recs, n(), "add slide", lambda: w._add_slide(1))
    _check_invariants(w, "add")
    _timed(recs, n(), "delete head", lambda: w._delete_slide(0))
    _check_invariants(w, "delete head")
    _timed(recs, n(), "move down", lambda: w._move_slide(0, +1))
    _check_invariants(w, "move down")
    _timed(recs, n(), "move up", lambda: w._move_slide(1, -1))
    _check_invariants(w, "move up")

    worst_op, worst_settle = _report(recs)
    assert worst_op < SMALL_OP_MS, f"small-deck op too slow: {worst_op:.1f}ms"
    assert worst_settle < SETTLE_MS, \
        f"small-deck settle too slow: {worst_settle:.1f}ms"


def test_stress_paste_renders(tmp_path):
    from core.clipboard import write_text
    w = _designer(tmp_path, "# T\n\n\n*1\naaa\n")
    write_text("*N\nx\n\n\ny\n\n\n*2\nz\n")
    w._activate(0)
    from PyQt6.QtTest import QTest as _QTest
    from PyQt6.QtCore import Qt as _Qt
    recs = []
    _timed(recs, len(w._slides), "tier ladder to 4", lambda: [
        _QTest.keyClick(w._edit, _Qt.Key.Key_A,
                        _Qt.KeyboardModifier.ControlModifier)
        for _ in range(4)], settle=False)
    assert w._sel_tier == 4
    _timed(recs, len(w._slides), "tier4 paste", lambda: _QTest.keyClick(
        w._edit, _Qt.Key.Key_V, _Qt.KeyboardModifier.ControlModifier))
    _qt().processEvents()
    _check_invariants(w, "tier4 paste")
    assert [(s.get("section"), s.get("text")) for s in w._slides] == [
        ("N", "x"), ("N", "y"), ("2", "z")]
    worst_op, worst_settle = _report(recs)
    assert worst_op < SMALL_OP_MS, f"paste op too slow: {worst_op:.1f}ms"
    assert worst_settle < SETTLE_MS, \
        f"paste settle too slow: {worst_settle:.1f}ms"


def test_stress_many_slides_timing(tmp_path):
    raw = "# T\n\n\n" + "\n\n\n".join(
        f"*S{i}\nwords number {i} here" for i in range(40))
    w = _designer(tmp_path, raw)
    w._confirm = lambda *a: True
    recs = []
    n = lambda: len(w._slides)
    w._cards[5].set_section("Renamed")
    _timed(recs, n(), "section commit @40",
           lambda: w._on_section_changed(5, "Renamed"))
    _timed(recs, n(), "add slide @40", lambda: w._add_slide(10))
    _timed(recs, n(), "delete head @40", lambda: w._delete_slide(0))
    _timed(recs, n(), "move @40", lambda: w._move_slide(3, +1))
    from core.clipboard import write_text
    write_text("*N\n" + "\n\n\n".join(f"pasted {i}" for i in range(5)) + "\n")
    w._activate(0)
    from PyQt6.QtTest import QTest as _QTest
    from PyQt6.QtCore import Qt as _Qt
    for _ in range(4):
        _QTest.keyClick(w._edit, _Qt.Key.Key_A,
                        _Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 4
    _timed(recs, n(), "tier4 paste @40", lambda: _QTest.keyClick(
        w._edit, _Qt.Key.Key_V, _Qt.KeyboardModifier.ControlModifier))
    _qt().processEvents()
    _check_invariants(w, "40 slides")
    worst_op, worst_settle = _report(recs)
    assert worst_op < LARGE_OP_MS, f"large-deck op too slow: {worst_op:.1f}ms"
    assert worst_settle < SETTLE_MS, \
        f"large-deck settle too slow: {worst_settle:.1f}ms"
