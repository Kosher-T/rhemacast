"""
tests/harness/lite_editing.py

The Lite Designer slide-editing harness — the closed loop for working on
the slide-card text editing experience.

What "closed loop" means here: every scenario drives the REAL LiteDesigner
widget with REAL input events (QTest key/mouse delivery, IME events), then
observes the full chain:

    keystroke ──▶ widget state ──▶ slide model ──▶ saved deck txt ──▶
    fresh re-open ──▶ visible cards again

`Lab.checkpoint()` runs that entire chain mid-scenario: it stores the live
docs, serializes, parses (and re-serializes for canonical stability),
opens a NEW designer from the saved txt, compares everything visible, and
swaps the lab over to the reopened window. A scenario that survives
checkpoints is a scenario whose edits are truly saved and truly restored —
not just alive in memory.

Usage — writing a scenario:

    from tests.harness.lite_editing import Lab

    def test_something(tmp_path):
        lab = Lab(tmp_path, "# T\\n\\n\\n*1\\nAmazing grace\\n")
        lab.focus_text(0)
        lab.enter(); lab.enter()               # split the slide
        lab.text("How sweet the sound")
        lab.checkpoint()                       # save + reopen + continue
        lab.expect_brief([("1", "Amazing grace"),
                          ("1", "How sweet the sound")])

Every primitive is recorded in `lab.trace` together with focus, caret and
a model hash, so a failing expectation can show the exact causal chain:

    AssertionError: slides after Enter+Enter:
      got:  [...]
      want: [...]
      trace:
        [ 3] enter            focus=text:0 caret=(0,11,11) model=b41f..a9
        [ 4] enter            focus=text:0 caret=(0,12,12) model=b41f..a9
        ...

Manual probe (a scripted natural session, traced):

    venv/bin/python -m tests.harness.lite_editing
"""

import hashlib
import os

os.environ["QT_QPA_PLATFORM"] = os.environ.get("RC_HARNESS_PLATFORM", "offscreen")

import ui.widgets.display_view  # noqa: F401  (WebEngine BEFORE any QApplication)

import time

from PyQt6.QtCore import Qt, QPoint, QEvent
from PyQt6.QtGui import QInputMethodEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import core.database as db
from core.slide_parser import deck_to_txt, parse_slide_txt, slide_owns_marker


# ────────────────────────────────────────────────────────────────


def _norm_slides(slides: list) -> list:
    """(section, text) tuples with None-sections normalized to ''."""
    return [((s.get("section") or ""), s.get("text") or "") for s in slides]


def _norm_parsed(parsed: dict) -> list:
    return _norm_slides(parsed.get("slides") or [])


class Lab:
    """One live designer session, driven like a user drives it."""

    # The QApplication MUST outlive every widget: a locally-scoped app
    # object gets garbage-collected the moment the boot function returns,
    # and its destruction takes the whole widget tree with it — the
    # symptom is a baffling "wrapped C/C++ object has been deleted" on
    # the first post-boot interaction.
    _APP = None

    def __init__(self, tmp_path, deck_txt="# T\n\n\nStart\n", *, show=True):
        from pathlib import Path
        self._tmp = Path(tmp_path)
        self._deck_txt = deck_txt
        self.confirm_answer = True
        self.confirm_calls = 0
        self.trace: list[dict] = []
        self.closed: list = []
        self.frame_runs: list[dict] = []
        self._boot(deck_txt, first=True)
        self._show = show

    # ── boot / teardown ─────────────────────────────────────────

    def _boot(self, deck_txt: str, first=False):
        app = QApplication.instance()
        if app is None:
            app = QApplication(["harness"])
        Lab._APP = app
        if first:
            db.DB_PATH = str(self._tmp / "harness.db")
            db.init_db()
        from core.slide_service import create_deck
        from ui.widgets.lite_designer.lite_designer import LiteDesigner
        deck = create_deck(deck_txt)
        self.deck_id = deck["id"]
        self.w = LiteDesigner(deck_id=deck["id"], live=False)
        self.w._confirm = self._confirm
        self.w.show()
        self.w.activateWindow()
        # A real WM activating the window makes Qt auto-focus the first
        # focusable widget in the chain; offscreen QPA skips that on
        # show(). Offscreen focus is not gated on an active window (and
        # QApplication.setActiveWindow here trips the pre-existing
        # WebEngine teardown segfault), so emulate just the handoff.
        if os.environ.get("RC_HARNESS_WM_FOCUS", "1") != "0":
            first = self._first_focusable()
            if first is not None:
                first.setFocus()
        self.settle()

    def _first_focusable(self):
        """First focusable widget in the window's chain — what a real WM
        activation would hand focus to on show()."""
        from PyQt6.QtCore import Qt as _Qt
        w = self.w.nextInFocusChain()
        seen = set()
        while w is not None and id(w) not in seen:
            seen.add(id(w))
            if (w is not self.w
                    and w.focusPolicy() != _Qt.FocusPolicy.NoFocus
                    and w.isVisible() and w.isEnabled()):
                return w
            w = w.nextInFocusChain()
        return None

    def _confirm(self, _text):
        self.confirm_calls += 1
        return self.confirm_answer

    def close(self):
        try:
            self.w._force_close = True
            self.w.close()
            self.w.deleteLater()
        except RuntimeError:
            pass
        for extra in self.closed:
            try:
                extra.close()
                extra.deleteLater()
            except RuntimeError:
                pass
        self.closed.clear()
        self.settle()

    def settle(self, passes: int = 3):
        app = QApplication.instance()
        for _ in range(passes):
            if app is not None:
                app.processEvents()
        time.sleep(0.001)

    # ── observation ─────────────────────────────────────────────

    @property
    def edit(self):
        return self.w._edit

    def active(self) -> int:
        return self.w._active

    def slides(self) -> list:
        """The model's (section, text) pairs, AFTER flushing live docs.

        This is what Save would persist. `raw_slides()` is the same view
        without the flush (what the model holds mid-keystroke).
        """
        self.w._store_active()
        return _norm_slides(self.w._slides)

    def raw_slides(self) -> list:
        return _norm_slides(self.w._slides)

    def visible(self) -> list:
        """What the user can read, card by card: chip + body text.

        The active card's body lives in the shared editor; inactive cards
        render into their display boxes. Bodies are read through
        `doc_to_txt`, the SAME projection the model and the save format
        use — `toPlainText()` renders a soft break (U+2028) as \\n, which
        would compare unlike a model that keeps the distinction.
        """
        from ui.widgets.lite_designer.rich_txt import doc_to_txt
        out = []
        for i, card in enumerate(self.w._cards):
            if i == self.w._active and card._editor_hosted:
                body = doc_to_txt(self.edit.document(),
                                  base_spacing=self.w._base_spacing())
            else:
                body = doc_to_txt(card._display_box.document(),
                                  base_spacing=self.w._base_spacing())
            out.append(((card._chip.toPlainText() or ""), body))
        return out

    def caret(self):
        """(slide, position, anchor) of the focused text box, or None.

        Section boxes are part of the editable queue, so their caret is
        the real one when they hold focus — reading the body editor there
        would report a place the keystroke never touched.
        """
        if not self.w._cards:
            return None
        f = QApplication.focusWidget()
        if f is None:
            f = self.w.focusWidget()
        for i, card in enumerate(self.w._cards):
            try:
                if f is card._chip:
                    cur = f.textCursor()
                    return (i, cur.position(), cur.anchor())
            except RuntimeError:
                continue
        doc = self.edit.document()
        if doc is None:
            return None
        cur = self.edit.textCursor()
        return (self.w._active, cur.position(), cur.anchor())

    def focus(self) -> str:
        """Where keyboard input lands right now, by role.

        Prefers the app-level focus widget; falls back to the window-level
        one (offscreen windows are often "inactive" while their internal
        focus chain is perfectly real).
        """
        f = QApplication.focusWidget()
        if f is None:
            f = self.w.focusWidget()
        if f is None:
            return "none"
        if f is self.edit:
            return f"text:{self.w._active}"
        try:
            if f is self.w._title_field:
                return "title"
        except (AttributeError, RuntimeError):
            pass
        for i, card in enumerate(self.w._cards):
            try:
                if f is card._chip:
                    return f"section:{i}"
            except RuntimeError:
                continue
        return f"other:{type(f).__name__}"

    def saved_txt(self) -> str:
        self.w._store_active()
        return deck_to_txt(self.w._title, self.w._slides, self.w._format)

    def parsed(self) -> dict:
        return parse_slide_txt(self.saved_txt())

    def body_doc_parts(self, i: int) -> list:
        """(text, params_dict) runs of slide i's document, for run-level
        assertions (formatting smuggled through editing)."""
        from ui.widgets.lite_designer.rich_txt import doc_to_txt
        doc = self.w._doc_for(i)
        return doc_to_txt(doc, base_spacing=self.w._base_spacing()), [
            r for r in _doc_runs(doc)]

    def chip_text(self, i: int) -> str:
        return self.w._cards[i]._chip.toPlainText()

    # ── invariants ──────────────────────────────────────────────

    def check(self, label: str = ""):
        """Full structural sweep — run after every structural op.

        Raised AssertionErrors carry the trace tail so the failing step
        is visible without a debugger.
        """
        w = self.w
        self._expect(len(w._cards) == len(w._slides),
                     f"cards {len(w._cards)} != slides {len(w._slides)}", label)
        hosted = 0
        for i, card in enumerate(w._cards):
            s = w._slides[i]
            expect_chip = (s.get("section") or "") \
                if slide_owns_marker(w._slides, i) else ""
            self._expect(card._chip.toPlainText() == expect_chip,
                         f"card {i} chip {card._chip.toPlainText()!r} "
                         f"want {expect_chip!r}", label)
            self._expect(card._index == i,
                         f"card {i} thinks index {card._index}", label)
            if i == w._active:
                self._expect(card._editor_hosted, f"active card {i} not hosting",
                             label)
                self._expect(w._edit.document() is w._doc_for(i),
                             f"editor doc is not slide {i}'s doc", label)
                hosted += 1
            else:
                self._expect(not card._editor_hosted,
                             f"inactive card {i} claims the editor", label)
            if i != w._active:
                self._expect(card._display_box.height() > 0,
                             f"card {i} display box has zero height", label)
        self._expect(hosted == 1, f"editor hosted {hosted}x", label)
        # marker invariant: a section value changing from the slide above
        # must own its marker (or the serializer drops it on save).
        for i, s in enumerate(w._slides):
            cur = s.get("section") or None
            prev = (w._slides[i - 1].get("section") or None) if i else None
            if cur != prev:
                self._expect(bool(s.get("marker")),
                             f"slide {i} section {cur!r} inherits (no marker)",
                             label)

    def _expect(self, cond, what, label=""):
        if not cond:
            raise AssertionError(
                f"{label + ': ' if label else ''}{what}\n"
                f"trace:\n{self._trace_tail()}")

    # ── expectations (trace-attached) ───────────────────────────

    def expect_brief(self, expected, label="slides"):
        got = self.slides()
        exp = [(a or "", b or "") for a, b in expected]
        if got != exp:
            raise AssertionError(
                f"{label}:\n  got:  {got}\n  want: {exp}\n"
                f"trace:\n{self._trace_tail()}")

    def expect_visible(self, expected, label="visible cards"):
        got = self.visible()
        exp = [(a or "", b or "") for a, b in expected]
        if got != exp:
            raise AssertionError(
                f"{label}:\n  got:  {got}\n  want: {exp}\n"
                f"trace:\n{self._trace_tail()}")

    def expect_focus(self, want, label="focus"):
        got = self.focus()
        if got != want:
            raise AssertionError(
                f"{label}: got {got!r} want {want!r}\n"
                f"trace:\n{self._trace_tail()}")

    def expect_caret(self, pos, label="caret"):
        got = self.caret()[1] if self.caret() else None
        if got != pos:
            raise AssertionError(
                f"{label}: got {got} want {pos}\n"
                f"trace:\n{self._trace_tail()}")

    # ── closed loop: save / reopen / continue ───────────────────

    def checkpoint(self, label="checkpoint"):
        """Persist, re-parse, re-open, compare — then keep driving.

        The pre-checkpoint model must survive: (1) serialization,
        (2) canonical re-serialization (stable txt), (3) a fresh open.
        Visible cards in the fresh window must read exactly like the
        pre-save model. The lab then operates on the reopened window.
        """
        self.w._store_active()
        txt = deck_to_txt(self.w._title, self.w._slides, self.w._format)
        pre = _norm_slides(self.w._slides)
        title = self.w._title
        fmt = dict(self.w._format)

        parsed = parse_slide_txt(txt)
        if _norm_parsed(parsed) != pre:
            raise AssertionError(
                f"{label}: txt round-trip lost data.\n"
                f"  before: {pre}\n  reparsed: {_norm_parsed(parsed)}\n"
                f"  txt:\n{txt}\n trace:\n{self._trace_tail()}")
        canon = deck_to_txt(parsed.get("title") or title,
                            parsed.get("slides") or [], fmt)
        if canon != txt:
            raise AssertionError(
                f"{label}: serialization is not canonical (save would "
                f"churn).\n  first:\n{txt}\n  again:\n{canon}\n"
                f"trace:\n{self._trace_tail()}")

        old = self.w
        self._boot(txt)
        self.closed.append(old)
        if _norm_slides(self.w._slides) != pre:
            raise AssertionError(
                f"{label}: reopen lost data.\n"
                f"  before: {pre}\n  after: {_norm_slides(self.w._slides)}\n"
                f"  txt:\n{txt}\n trace:\n{self._trace_tail()}")
        vis = self.visible()
        want = [(s if slide_owns_marker(self.w._slides, i) else "",
                 t) for i, (s, t) in enumerate(pre)]
        if vis != want:
            raise AssertionError(
                f"{label}: reopened cards don't read like the model.\n"
                f"  visible: {vis}\n  want:    {want}\n"
                f"trace:\n{self._trace_tail()}")
        self._record(f"checkpoint({label}) ok")

    # ── input primitives ────────────────────────────────────────

    def _target(self):
        """The true keyboard destination — NEVER a comfort fallback.

        If nothing holds focus, keys go to the window exactly like a real
        user's would, and they land nowhere. Silently rerouting to the
        editor would mask real "focus was lost" bugs (e.g. after a
        double-Enter split) by letting the scenario keep typing.
        """
        f = QApplication.focusWidget()
        if f is None:
            f = self.w.focusWidget()
        return f if f is not None else self.w

    def _record(self, op: str):
        self.trace.append({
            "op": op,
            "focus": self.focus(),
            "caret": self.caret(),
            "model": hashlib.sha1(
                repr(self.raw_slides()).encode()).hexdigest()[:10],
        })

    def _trace_tail(self, n=12):
        lines = []
        for i, e in enumerate(self.trace[-n:], start=len(self.trace) - min(n, len(self.trace))):
            care = e["caret"]
            lines.append(
                f"  [{i:>3}] {e['op']:<28} focus={e['focus']:<11} "
                f"caret={care} model={e['model']}")
        return "\n".join(lines) or "  (empty)"

    def tap(self, key, *mods):
        """One key press to the focused widget, like a real keyboard."""
        modifier = Qt.KeyboardModifier.NoModifier
        for m in mods:
            modifier |= m
        QTest.keyClick(self._target(), key, modifier)
        self.settle()
        prefix = ""
        if modifier & Qt.KeyboardModifier.ControlModifier:
            prefix += "Ctrl+"
        if modifier & Qt.KeyboardModifier.ShiftModifier:
            prefix += "Shift+"
        if modifier & Qt.KeyboardModifier.AltModifier:
            prefix += "Alt+"
        self._record(f"tap({prefix}{_key_name(key)})")

    def request_close(self):
        self.w.close()
        self.settle()
        self._record("close()")

    def answer_close(self, discard: bool):
        from PyQt6.QtWidgets import QPushButton
        label = "Discard" if discard else "Cancel"
        btn = next(b for b in self.w.findChildren(QPushButton)
                   if b.text() == label and b.isVisible())
        btn.click()
        self.settle()
        self._record(f"close({label})")

    def save(self):
        """Click the real Save button (the full save path, not a shortcut)."""
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in self.w.findChildren(QPushButton)
                   if b.text() == "Save")
        btn.click()
        self.settle()
        self._record("save()")

    def undo(self):
        self.tap(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    def redo(self):
        self.tap(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier,
                 Qt.KeyboardModifier.ShiftModifier)

    def text(self, s: str):
        """Type characters (typable ASCII), like a real keyboard."""
        QTest.keyClicks(self._target(), s)
        self.settle()
        self._record(f"text({s!r})")

    def ime(self, s: str):
        """Commit text through the input-method event (unicode, emoji)."""
        target = self._target()
        app = QApplication.instance()
        app.sendEvent(target, QInputMethodEvent("", []))
        app.sendEvent(target, QInputMethodEvent("", []))  # clear preedit
        target.setFocus()
        ev = QInputMethodEvent("", [])
        ev.setCommitString(s)
        app.sendEvent(target, ev)
        self.settle()
        self._record(f"ime({s!r})")

    def ime_preedit(self, s: str):
        """Start a composition (preedit) — must never touch the model."""
        target = self._target()
        attr = QInputMethodEvent.Attribute(
            QInputMethodEvent.AttributeType.TextFormat,
            0, 0, None)
        QApplication.instance().sendEvent(
            target, QInputMethodEvent(s, [attr]))
        self.settle()
        self._record(f"ime_preedit({s!r})")

    # semantic keys ─────────────────────────────────────────────

    def enter(self):
        self.tap(Qt.Key.Key_Return)

    def shift_enter(self):
        self.tap(Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

    def ctrl_insert(self):
        self.tap(Qt.Key.Key_Insert, Qt.KeyboardModifier.ControlModifier)

    def ctrl_enter(self):
        self.tap(Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)

    def escape(self):
        self.tap(Qt.Key.Key_Escape)

    def backspace(self, times=1):
        for _ in range(times):
            self.tap(Qt.Key.Key_Backspace)

    def delete(self, times=1):
        for _ in range(times):
            self.tap(Qt.Key.Key_Delete)

    def left(self, n=1, shift=False):
        for _ in range(n):
            self.tap(Qt.Key.Key_Left,
                     *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def right(self, n=1, shift=False):
        for _ in range(n):
            self.tap(Qt.Key.Key_Right,
                     *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def up(self, n=1, shift=False):
        for _ in range(n):
            self.tap(Qt.Key.Key_Up,
                     *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def down(self, n=1, shift=False):
        for _ in range(n):
            self.tap(Qt.Key.Key_Down,
                     *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def home(self, shift=False):
        """Start of the LINE (Qt default), not of the document."""
        self.tap(Qt.Key.Key_Home,
                 *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def end(self, shift=False):
        """End of the LINE (Qt default), not of the document."""
        self.tap(Qt.Key.Key_End,
                 *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def home_doc(self, shift=False):
        self.tap(Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier,
                 *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def end_doc(self, shift=False):
        self.tap(Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier,
                 *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def ctrl_left(self, shift=False):
        self.tap(Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier,
                 *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def ctrl_right(self, shift=False):
        self.tap(Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier,
                 *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    def ctrl_backspace(self):
        self.tap(Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier)

    def ctrl_delete(self):
        self.tap(Qt.Key.Key_Delete, Qt.KeyboardModifier.ControlModifier)

    def tab(self, shift=False):
        self.tap(Qt.Key.Key_Tab,
                 *([Qt.KeyboardModifier.ShiftModifier] if shift else []))

    # the app's Ctrl+A tier ladder ──────────────────────────────

    def select_all_tier(self, climbs=1):
        for _ in range(climbs):
            self.tap(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self._record(f"tier={self.w._sel_tier}")

    # clipboard ─────────────────────────────────────────────────

    def set_clipboard(self, text, html=None):
        from core.clipboard import read_text, write_text
        write_text(text)
        if html is not None:
            cb = QApplication.clipboard()
            if cb is not None:
                from PyQt6.QtCore import QMimeData
                mime = QMimeData()
                mime.setText(text)
                mime.setHtml(html)
                cb.setMimeData(mime)
        if text:
            got = read_text()
            assert got == text, (
                f"clipboard did not take our text: {got[:60]!r}")
        self._record(f"clipboard({text[:24]!r}{' +html' if html else ''})")

    def copy(self):
        self.tap(Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)

    def cut(self):
        self.tap(Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)

    def paste(self):
        self.tap(Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

    def undo(self):
        self.tap(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    def redo(self):
        self.tap(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier,
                 Qt.KeyboardModifier.ShiftModifier)

    # mouse ─────────────────────────────────────────────────────

    def _box_for(self, i: int):
        """The user-visible body box of card i (editor if hosted)."""
        card = self.w._cards[i]
        if i == self.w._active and card._editor_hosted:
            return self.edit
        return card._display_box

    def _pos_for(self, box, offset: int) -> QPoint:
        cur = box.textCursor()
        cur.setPosition(max(0, offset))
        rect = box.cursorRect(cur)
        return rect.center()

    def click_at(self, i: int, offset: int = 0):
        """Click into slide i's body at a character offset."""
        box = self._box_for(i)
        pos = self._pos_for(box, offset)
        QTest.mouseClick(box.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        self.settle()
        self._record(f"click_at({i},{offset})")

    def click_chip_at(self, i: int, offset: int = 0):
        chip = self.w._cards[i]._chip
        pos = self._pos_for(chip, offset)
        QTest.mouseClick(chip.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        self.settle()
        self._record(f"click_chip_at({i},{offset})")

    def click_card(self, i: int):
        card = self.w._cards[i]
        QTest.mouseClick(card, Qt.MouseButton.LeftButton,
                         pos=card.rect().center())
        self.settle()
        self._record(f"click_card({i})")

    def dblclick_at(self, i: int, offset: int):
        box = self._box_for(i)
        pos = self._pos_for(box, offset)
        QTest.mouseDClick(box.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        self.settle()
        self._record(f"dblclick_at({i},{offset})")

    def triple_at(self, i: int, offset: int):
        box = self._box_for(i)
        pos = self._pos_for(box, offset)
        interval = QApplication.doubleClickInterval()
        QTest.mouseClick(box.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        time.sleep(0.02)
        QTest.mouseDClick(box.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        time.sleep(0.02)
        QTest.mouseClick(box.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        self.settle()
        self._record(f"triple_at({i},{offset})")

    def drag(self, i_from: int, off_from: int, i_to: int, off_to: int):
        """Press at one offset, drag, release at another (cross-card ok)."""
        box_a = self._box_for(i_from)
        box_b = self._box_for(i_to)
        pa = self._pos_for(box_a, off_from)
        pb = self._pos_for(box_b, off_to)
        QTest.mousePress(box_a.viewport(), Qt.MouseButton.LeftButton, pos=pa)
        self.settle(1)
        steps = 4
        for k in range(1, steps + 1):
            mid = QPoint(pa.x() + (pb.x() - pa.x()) * k // steps,
                         pa.y() + (pb.y() - pa.y()) * k // steps)
            QTest.mouseMove(box_b.viewport(), mid)
            self.settle(1)
        QTest.mouseMove(box_b.viewport(), pb)
        self.settle(1)
        QTest.mouseRelease(box_b.viewport(), Qt.MouseButton.LeftButton, pos=pb)
        self.settle()
        self._record(f"drag({i_from},{off_from}->{i_to},{off_to})")

    # focus helpers ─────────────────────────────────────────────

    def focus_text(self, i: int, offset: int | None = None):
        """Activate slide i with the caret in its body."""
        self.w._activate(i)
        self.settle()
        self.edit.setFocus()
        if offset is not None:
            cur = self.edit.textCursor()
            cur.setPosition(offset)
            self.edit.setTextCursor(cur)
        self.settle()
        self._record(f"focus_text({i}{',' + str(offset) if offset is not None else ''})")

    def focus_section(self, i: int, offset: int | None = None):
        self.w._activate(i)
        self.settle()
        chip = self.w._cards[i]._chip
        chip.setFocus()
        if offset is not None:
            cur = chip.textCursor()
            cur.setPosition(offset)
            chip.setTextCursor(cur)
        self.settle()
        self._record(f"focus_section({i})")

    def select_range(self, i: int, start: int, end: int):
        """Programmatic range selection in slide i's body (setup aid)."""
        self.w._activate(i)
        self.settle()
        cur = self.edit.textCursor()
        cur.setPosition(start)
        cur.setPosition(end, cur.MoveMode.KeepAnchor)
        self.edit.setTextCursor(cur)
        self.settle()
        self._record(f"select_range({i},{start},{end})")

    # ── structural buttons (the action pill) ────────────────────

    def click_add(self, i: int):
        QTest.mouseClick(self.w._cards[i]._btn_add,
                         Qt.MouseButton.LeftButton)
        self.settle()
        self._record(f"click_add({i})")

    def click_delete(self, i: int):
        QTest.mouseClick(self.w._cards[i]._btn_del,
                         Qt.MouseButton.LeftButton)
        self.settle()
        self._record(f"click_delete({i})")

    def click_move_up(self, i: int):
        QTest.mouseClick(self.w._cards[i]._btn_up, Qt.MouseButton.LeftButton)
        self.settle()
        self._record(f"click_move_up({i})")

    def click_move_down(self, i: int):
        QTest.mouseClick(self.w._cards[i]._btn_down,
                         Qt.MouseButton.LeftButton)
        self.settle()
        self._record(f"click_move_down({i})")

    # ── motion frames (60fps evidence for structural rerenders) ──

    def capture_frames(self, op, label="frames", window_ms=350,
                       interval_ms=17, scope=None):
        """Grab the designer (or `scope` inside it) every ~17ms across a
        structural change.

        Pass `scope` to watch just the region under test — the preview pane
        repaints on its own debounce (~180ms) and is not part of the
        structural rerender being judged.

        A structural edit (add/delete/split/paste) must either animate
        smoothly or rearrange perfectly in one frame — never show a
        half-built intermediate. This records the evidence: lossless PNGs
        plus a per-frame pixel-delta summary, so a human (or an agent)
        can review the actual motion instead of trusting a timing log.

        Frames are grabbed in memory (a warm grab is a few ms) and written
        to disk after the window — encoding mid-run would stretch the
        cadence and fake a stutter.

        Returns the frame rows and remembers the run in ``frame_runs``.
        ``op()`` runs once, immediately after the idle frame.
        """
        from pathlib import Path
        out = self._tmp / "frames" / label
        out.mkdir(parents=True, exist_ok=True)
        app = QApplication.instance()
        self.w.repaint()
        if app is not None:
            app.processEvents()

        t0 = time.perf_counter()
        frames: list[tuple[float, object, str]] = []

        grab_widget = scope if scope is not None else self.w

        def snap(tag: str):
            img = grab_widget.grab().toImage()
            frames.append((time.perf_counter() - t0, img, tag))

        snap("0000ms")
        op()
        n = 1
        while (time.perf_counter() - t0) * 1000 < window_ms:
            target = t0 + (n * interval_ms) / 1000.0
            wait_s = target - time.perf_counter()
            if wait_s > 0:
                time.sleep(wait_s)
            if app is not None:
                app.processEvents()
            snap(f"{n * interval_ms:04d}ms")
            n += 1

        rows = []
        prev = None
        for t_ms, img, tag in frames:
            small = img.scaled(160, 90,
                               Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            small = small.convertToFormat(
                small.Format.Format_RGB32)
            diff = 0.0
            if prev is not None:
                same = 0
                for y in range(small.height()):
                    for x in range(small.width()):
                        if small.pixel(x, y) == prev.pixel(x, y):
                            same += 1
                diff = 1.0 - same / (small.width() * small.height())
            prev = small
            path = out / f"{tag}.png"
            img.save(str(path))
            rows.append({"t_ms": round(t_ms * 1000, 1),
                         "diff": round(diff, 4),
                         "png": str(path)})
        self.frame_runs.append({"label": label, "dir": str(out),
                                "frames": rows})
        self._record(f"capture_frames({label}, {len(rows)}f)")
        return rows


def _key_name(key) -> str:
    try:
        return Qt.Key(key).name.replace("Key_", "")
    except (ValueError, TypeError):
        return str(key)


def _doc_runs(doc):
    """Per-fragment (text, format-summary) runs — for run-level asserts."""
    out = []
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                out.append((frag.text(), {
                    "bold": fmt.fontWeight(),
                    "italic": fmt.fontItalic(),
                    "underline": fmt.fontUnderline(),
                    "color": fmt.foreground().color().name()
                    if fmt.foreground().style() else None,
                }))
            it += 1
        block = block.next()
    return out


# ── manual probe ────────────────────────────────────────────────


def probe():
    """A scripted natural editing session, traced end to end.

    Run:  venv/bin/python -m tests.harness.lite_editing
    """
    import tempfile
    tmp = tempfile.mkdtemp(prefix="lite-lab-")
    lab = Lab(tmp, "# Amazing Grace\n\n\n*Verse 1\nAmazing grace how sweet\n"
                   "the sound\n\n\n*Chorus\nMy chains are gone\n")
    try:
        lab.focus_text(0)
        lab.text("!")                       # type at caret 0
        lab.end_doc()
        lab.enter()
        lab.enter()                          # split into a new slide
        lab.focus_text(1, 0)                 # split leaves focus nowhere
        lab.text("that saved a wretch like me")
        lab.checkpoint("mid-edit")
        lab.dblclick_at(0, 3)                # word select
        lab.text("GRACE")                    # replace the word
        lab.home()
        lab.right(4)
        lab.shift_enter()                    # soft break mid-line, same card
        lab.text("first ")
        lab.checkpoint("after-soft-break")
        print("final slides:")
        for s, t in lab.slides():
            print(f"  [{s or '-'}] {t!r}")
        print(f"trace: {len(lab.trace)} steps")
        print(lab._trace_tail(30))
        print("OK — full closed loop survived.")
    finally:
        # Deliberately NOT lab.close(): tearing a WebEngine-backed
        # designer down mid-process segfaults on exit (pre-existing,
        # repo-wide — `pytest tests/test_lite_designer_cards.py` prints
        # "3 passed" and still exits 139). Keeping the window referenced
        # mirrors tests/test_lite_designer_select.py and exits clean.
        pass


if __name__ == "__main__":
    probe()
