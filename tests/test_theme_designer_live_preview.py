"""Theme Designer live preview: one frame per burst, immediate on release.

The left panel writes a drag value into the document while the pointer moves
and a committed value on release. The preview has to follow both without ever
publishing per event:

* a burst of drag values coalesces into ONE publish on the next frame, and the
  theme it publishes is the newest value, not the first;
* a release publishes synchronously (``flush=True``) and cancels a frame that
  has not fired yet (one that already fired is not undone: the document is
  then published again, which is what the preview relies on);
* replacing the whole document (theme load, import, Apply JSON) reloads the
  preview instead of patching the page that is already showing.

The property field's half of the live-edit path — a drag's commit signal and
its in-flight value — is pinned in ``test_theme_kit_color_field.py``. What is
pinned here is the tab boundary: how much reaches ``PreviewManager`` and when.

QtWebEngine is not used: the tab is built with a stub preview and a recording
replacement for ``PreviewManager``, which is the boundary under test.
"""

from __future__ import annotations

import copy
import os
import shutil
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

# Import WebEngine before QApplication exists; the module import is enough for
# the real preview import chain, while these tests construct a stub instead.
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

import core.theme_loader as theme_loader  # noqa: E402
from core.constants import THEME_PREVIEW_FRAME_MS  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_THEMES = _ROOT / "themes"

_QAPP = None
_TAB_MODULE = None
_REAL_PREVIEW = None


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


@pytest.fixture(scope="module")
def theme_tree(tmp_path_factory):
    """A disposable copy of themes/ so nothing here reads the operator's tree."""
    root = tmp_path_factory.mktemp("live-preview") / "themes"
    shutil.copytree(_THEMES, root)
    previous = theme_loader._THEMES_DIR
    theme_loader._THEMES_DIR = root
    theme_loader.reload_themes()
    try:
        yield root
    finally:
        theme_loader._THEMES_DIR = previous
        theme_loader.reload_themes()


class RecordingPreviewManager:
    """Stands in for PreviewManager and records what the tab publishes."""

    def __init__(self):
        self.calls: list[tuple] = []

    def update_theme(self, theme, paths=(), *, flush=False):
        self.calls.append(
            ("update", copy.deepcopy(theme), tuple(paths), bool(flush)))

    def load_theme(self, theme, sample_id=None):
        self.calls.append(("load", copy.deepcopy(theme), sample_id))

    def __getattr__(self, _name):
        def _ignore(*_args, **_kwargs):
            return None
        return _ignore


@pytest.fixture
def designer(qapp, theme_tree, monkeypatch):
    global _TAB_MODULE, _REAL_PREVIEW
    if _TAB_MODULE is None:
        from ui.tabs import theme_designer_tab as module
        _TAB_MODULE = module
        _REAL_PREVIEW = module.ThemePreview

    class _PreviewStub(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.theme = {}
            self.sample = ""

        def apply_theme(self, theme):
            self.theme = copy.deepcopy(theme)

        def set_verse(self, sample_id):
            self.sample = str(sample_id)

    monkeypatch.setattr(_TAB_MODULE, "ThemePreview", _PreviewStub)
    tab = _TAB_MODULE.ThemeDesignerTab()
    tab.resize(1400, 900)

    # Swap the manager before any frame can fire: the tab arms one while
    # loading its default theme, and that publish belongs to the real manager.
    recorder = RecordingPreviewManager()
    tab._preview_manager = recorder
    timer = getattr(tab, "_preview_timer", None)
    if timer is not None:
        timer.stop()
    tab._preview_pending = None
    tab._preview_paths = ()
    tab._preview_reload = False

    yield tab, recorder
    tab.close()
    tab.deleteLater()
    qapp.processEvents()


def _wait_for_publish(recorder, count: int = 1, timeout_ms: int = 2000) -> bool:
    """Pump the event loop until the frame timer has published ``count`` calls."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while len(recorder.calls) < count and time.monotonic() < deadline:
        QTest.qWait(5)
    return len(recorder.calls) >= count


# ── drag: coalesce, newest value wins, then re-arm ──────────────────────────

def test_a_burst_of_drag_values_is_published_once_with_the_newest(designer):
    tab, recorder = designer

    tab._document.preview(("canvas", "background"), "#101010")
    tab._document.preview(("canvas", "background"), "#202020")
    tab._document.preview(("canvas", "background"), "#303030")

    # Never one publish per drag step: the newest value waits for the frame.
    assert recorder.calls == [], "a drag step must be coalesced, not painted"

    assert _wait_for_publish(recorder), "the frame timer never published"
    QTest.qWait(THEME_PREVIEW_FRAME_MS * 4)      # a second frame must not replay
    assert len(recorder.calls) == 1, recorder.calls

    kind, theme, paths, flush = recorder.calls[0]
    assert kind == "update"
    assert theme["canvas"]["background"] == "#303030"   # newest, not first
    # A style paint only: no animation phase, so nothing replays.
    assert paths == ()
    assert flush is False
    assert tab._preview_timer.isActive() is False


def test_the_next_drag_after_an_idle_frame_publishes_again(designer):
    tab, recorder = designer
    tab._document.preview(("canvas", "background"), "#111111")
    assert _wait_for_publish(recorder)

    # The one-shot timer is re-armed by the next change.
    tab._document.preview(("canvas", "background"), "#222222")
    assert _wait_for_publish(recorder, count=2), recorder.calls
    assert recorder.calls[1][1]["canvas"]["background"] == "#222222"


def test_a_drag_that_returns_to_the_stored_value_repaints_it_back(designer):
    """A drag that goes back to where it started must repaint the original.

    The first frame already painted the abandoned colour, so the second frame
    has to carry the document as it now stands — a scheduler holding the first
    value it saw would leave the preview on the colour the pointer left.
    """
    tab, recorder = designer
    original = tab._document.get(("canvas", "background"))

    tab._document.preview(("canvas", "background"), "#abcdef")
    assert _wait_for_publish(recorder), "the armed frame never fired"
    assert recorder.calls[0][1]["canvas"]["background"] == "#abcdef"

    tab._document.preview(("canvas", "background"), original)
    assert _wait_for_publish(recorder, count=2), recorder.calls
    assert recorder.calls[1][1]["canvas"]["background"] == original


# ── release: synchronous, and the pending frame is cancelled ────────────────

def test_release_publishes_immediately_and_cancels_the_pending_frame(designer):
    tab, recorder = designer

    tab._document.preview(("canvas", "background"), "#abcdef")
    assert tab._preview_timer.isActive(), "the drag should have armed a frame"

    tab._on_property_committed()

    # Synchronous: no event loop turn, no waiting for the frame.
    assert len(recorder.calls) == 1, recorder.calls
    kind, theme, _paths, flush = recorder.calls[0]
    assert kind == "update"
    assert flush is True, "a release must paint now, not on the next frame"
    assert theme["canvas"]["background"] == "#abcdef"
    assert tab._preview_timer.isActive() is False

    # The frame the drag armed was cancelled, not merely overtaken.
    QTest.qWait(THEME_PREVIEW_FRAME_MS * 5)
    assert len(recorder.calls) == 1, recorder.calls


def test_the_release_publish_is_independent_of_the_frame_publish(designer):
    """The frame publish clears the pending state; the release must still
    paint. Today that means the document is published twice — once by the
    frame, once flushed by the release — and that is the behavior the preview
    relies on: a commit never has to wait for, or defer to, a frame."""
    tab, recorder = designer
    tab._document.preview(("canvas", "background"), "#fedcba")
    tab._flush_preview()                       # the frame, however it arrives
    assert len(recorder.calls) == 1, recorder.calls
    assert recorder.calls[0][3] is False

    tab._on_property_committed()
    assert len(recorder.calls) == 2, recorder.calls
    assert recorder.calls[1][3] is True
    assert recorder.calls[1][1]["canvas"]["background"] == "#fedcba"


# ── whole-document swap: reload, do not patch ───────────────────────────────

def test_replacing_the_document_reloads_the_preview_after_one_frame(designer):
    tab, recorder = designer
    theme = copy.deepcopy(tab._document.snapshot())
    theme["canvas"]["background"] = "#123456"
    theme["label"] = "Swapped"

    tab._document.replace(theme)
    assert recorder.calls == [], "a document swap still waits for the frame"

    assert _wait_for_publish(recorder), "the swap never reached the preview"
    kinds = [call[0] for call in recorder.calls]
    assert kinds == ["load"], "a swapped document must reload, not patch"
    kind, published, sample = recorder.calls[0]
    assert published["canvas"]["background"] == "#123456"
    assert published["label"] == "Swapped"
    assert sample == tab._samples.current()
