"""Translation badge / result row click semantics across the search lanes.

Contract (operator-facing):
  badge single-click -> navigate + preview in the badge's translation
  badge double-click -> push to live in the badge's translation
  row single-click   -> navigate to the highlighted ref
  row double-click   -> push to live in the browser's current translation
  presses on a badge never fire row-level actions (and vice versa)
  a failed translation switch in the browser must revert instead of
  leaving the browser half-switched ("click does nothing").

Double-click discrimination follows Qt's own synthesis (system double-click
interval); singles fire only after a wait longer than that interval.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ui.panels.fts_search_panel import _ResultRow as FtsRow
from ui.panels.fts_search_panel import _TransBadge as FtsBadge
from ui.panels.search_panel import SearchResultWidget as FuzzyRow
from ui.panels.search_panel import _TransBadge as FuzzyBadge
from ui.tabs.presentation_tab import PresentationTab

# Widgets stay referenced for the module's lifetime: dropping the last
# Python ref to a shown widget destroys it, and a pending timer then
# touches dead C++.
_KEEP = []

VERSE = {
    "book": "Genesis",
    "chapter": "1",
    "verse": "1",
    "verse_num": "1",
    "version": "KJV",
    "text": "In the beginning God created the heavens",
}
VERSE_WITH_TRANS = dict(VERSE, translations=[dict(
    version="KJV", text=VERSE["text"], book="Genesis",
    chapter="1", verse_num="1")])


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


def _interval():
    return QApplication.instance().doubleClickInterval()


def _shown(qapp, widget):
    widget.show()
    _KEEP.append(widget)
    return widget


def _badge(badge_cls):
    if badge_cls is FtsBadge:
        return badge_cls("KJV", VERSE)
    return badge_cls("KJV", "KJV", VERSE)


@pytest.mark.parametrize("badge_cls", [FtsBadge, FuzzyBadge])
def test_badge_single_fires_after_system_interval(qapp, badge_cls):
    badge = _shown(qapp, _badge(badge_cls))
    fired = []
    badge.single_clicked.connect(lambda v, d: fired.append("single"))
    badge.double_clicked.connect(lambda v, d: fired.append("double"))

    QTest.mouseClick(badge, Qt.MouseButton.LeftButton)
    QTest.qWait(_interval() + 80)

    assert fired == ["single"]


@pytest.mark.parametrize("badge_cls", [FtsBadge, FuzzyBadge])
def test_badge_double_click_cancels_single(qapp, badge_cls):
    badge = _shown(qapp, _badge(badge_cls))
    fired = []
    badge.single_clicked.connect(lambda v, d: fired.append("single"))
    badge.double_clicked.connect(lambda v, d: fired.append("double"))

    QTest.mouseDClick(badge, Qt.MouseButton.LeftButton)
    QTest.qWait(_interval() + 80)

    assert fired == ["double"]


@pytest.mark.parametrize("row_cls", [FtsRow, FuzzyRow])
def test_row_single_and_double_semantics(qapp, row_cls):
    if row_cls is FtsRow:
        row = _shown(qapp, row_cls(dict(VERSE_WITH_TRANS), "beginning"))
    else:
        row = _shown(qapp, row_cls(dict(VERSE_WITH_TRANS)))

    got = {"navigate": [], "live": []}
    row.navigate_requested.connect(lambda d: got["navigate"].append(d))
    row.live_requested.connect(lambda d: got["live"].append(d))

    # Single click: navigate only, once the system interval passed.
    QTest.mouseClick(row, Qt.MouseButton.LeftButton)
    QTest.qWait(_interval() + 80)
    assert len(got["navigate"]) == 1
    assert got["live"] == []

    # Double click: live only. The double CANCELS the pending single —
    # no stray navigate, exactly one live push.
    QTest.mouseDClick(row, Qt.MouseButton.LeftButton)
    QTest.qWait(_interval() + 80)
    assert len(got["navigate"]) == 1
    assert len(got["live"]) == 1


@pytest.mark.parametrize("row_cls", [FtsRow, FuzzyRow])
def test_row_press_on_badge_area_fires_no_row_actions(qapp, row_cls):
    """A press landing on the badge's rect must stay with the badge:
    no row navigate/live, whatever the cursor does."""
    if row_cls is FtsRow:
        row = _shown(qapp, row_cls(dict(VERSE_WITH_TRANS), "beginning"))
    else:
        row = _shown(qapp, row_cls(dict(VERSE_WITH_TRANS)))

    badge = getattr(row, "_trans_badge", None)
    if badge is None:
        pytest.skip("row built without a badge")

    got = {"navigate": [], "live": []}
    row.navigate_requested.connect(lambda d: got["navigate"].append(d))
    row.live_requested.connect(lambda d: got["live"].append(d))

    # Event posted to the row itself, positioned over the badge. The row's
    # own handler must bail via its geometry guard — no timers, no actions.
    pos = badge.geometry().center()
    QTest.mousePress(row, Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseRelease(row, Qt.MouseButton.LeftButton, pos=pos)
    QTest.qWait(_interval() + 80)

    assert got["navigate"] == []
    assert got["live"] == []


# ── Presentation tab handler guards ───────────────────────────────────────

class _FakeDisplay:
    def __init__(self):
        self.published_live = []
        self.published_preview = []

    def publish_live(self, payload, verse_dict, *args):
        self.published_live.append((payload, verse_dict))

    def publish_preview(self, payload, verse_dict):
        self.published_preview.append((payload, verse_dict))


def _tab():
    from types import SimpleNamespace

    tab = PresentationTab.__new__(PresentationTab)
    tab._display = _FakeDisplay()
    tab._current_display = None
    tab._current_preview = None
    tab._is_cleared = True
    tab._cloaked = False
    tab.ws_sent = []
    tab._themes_by_output = {}
    tab._set_cloak = lambda on: setattr(tab, "_cloaked", on)
    return tab


def _tab_with_browser():
    """Tab stub whose browser records navigate_to_reference calls."""
    class _Browser:
        def __init__(self):
            self.navigated = []

        def navigate_to_reference(self, *args, **kwargs):
            self.navigated.append((args, kwargs))
            return None

    tab = _tab()
    tab.browser_panel = _Browser()
    return tab


def test_badge_single_without_reference_is_ignored():
    tab = _tab_with_browser()

    PresentationTab._on_trans_badge_to_navigator(
        tab, {"book": "", "chapter": "1", "verse_num": "1"})
    PresentationTab._on_trans_badge_to_navigator(tab, {"book": "Genesis"})
    PresentationTab._on_trans_badge_to_navigator(tab, "not-a-dict")
    PresentationTab._on_trans_badge_to_navigator(tab, {"book": "Genesis"})
    PresentationTab._on_trans_badge_to_navigator(tab, "not-a-dict")

    assert tab.browser_panel.navigated == []
    assert tab._display.published_preview == []


import ui.tabs.presentation_tab  # noqa: E402


def test_badge_single_falls_back_to_verse_key():
    tab = _tab_with_browser()

    PresentationTab._on_trans_badge_to_navigator(
        tab, {"book": "Genesis", "chapter": "1", "verse": "1",
              "version": "KJV"})
    (args, kwargs), = tab.browser_panel.navigated
    assert args == ("Genesis", "1", "1")
    assert kwargs == {"translation": "KJV"}
    assert tab._display.published_preview, "preview still updates"


def test_badge_live_without_reference_is_ignored():
    tab = _tab()

    PresentationTab._on_trans_badge_to_live(
        tab, {"book": "", "chapter": "1", "verse_num": "1"})
    PresentationTab._on_trans_badge_to_live(tab, "junk")

    assert tab._display.published_live == []
    assert tab._is_cleared is True  # never pushed


# ── Browser: failed translation switch reverts ────────────────────────────

class _Btn:
    def __init__(self):
        self.active = None

    def set_active(self, on):
        self.active = on


class _VerseList:
    def __init__(self):
        self._translation = "KJV"


class _Predictive:
    def __init__(self):
        self.translations = []

    def set_translation(self, t):
        self.translations.append(t)


def _browser(monkeypatch, load_results):
    from ui.panels.browser_panel import BrowserPanel

    panel = BrowserPanel.__new__(BrowserPanel)
    panel._translation_buttons = {"KJV": _Btn(), "LUT": _Btn()}
    panel._current_translation = "KJV"
    panel.verse_list = _VerseList()
    panel.predictive_input = _Predictive()
    loads = []

    def _fake_load_bible(self):
        loads.append(self._current_translation)
        return load_results.pop(0)

    monkeypatch.setattr(BrowserPanel, "_load_bible", _fake_load_bible)
    return panel, loads


def test_failed_translation_switch_reverts_state(monkeypatch):
    panel, loads = _browser(monkeypatch, [False, True])

    assert panel._switch_translation("LUT") is False

    # Everything rolled back to the previous translation.
    assert panel._current_translation == "KJV"
    assert panel.verse_list._translation == "KJV"
    assert panel._translation_buttons["LUT"].active is False
    assert panel._translation_buttons["KJV"].active is True
    # The reverted translation was reloaded (viewer consistency).
    assert loads, "previous translation must be reloaded on revert"


def test_successful_translation_switch_sticks(monkeypatch):
    panel, _loads = _browser(monkeypatch, [True])

    assert panel._switch_translation("LUT") is True
    assert panel._current_translation == "LUT"
    assert panel.verse_list._translation == "LUT"
    assert panel._translation_buttons["KJV"].active is False
    assert panel._translation_buttons["LUT"].active is True


def test_navigate_to_reference_reverts_on_failed_load(monkeypatch):
    """Badge single-click path: a dead translation must not wedge the
    browser — the reference still highlights on the ORIGINAL translation."""
    from ui.panels.browser_panel import BrowserPanel

    panel, _loads = _browser(monkeypatch, [False, True])
    highlighted = []

    def _fake_set_highlight(self, book, chapter, verse):
        highlighted.append((book, chapter, verse))

    monkeypatch.setattr(BrowserPanel, "_set_highlight", _fake_set_highlight)
    monkeypatch.setattr(BrowserPanel, "_scroll_to_highlight",
                        lambda self: None)
    monkeypatch.setattr(BrowserPanel, "_update_navigator",
                        lambda self: None)

    panel.navigate_to_reference("Genesis", "1", "1", translation="LUT")

    assert panel._current_translation == "KJV"
    assert highlighted[-1] == ("Genesis", 1, 1)
