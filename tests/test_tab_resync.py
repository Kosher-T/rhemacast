"""
tests/test_tab_resync.py

Tab-switch resync contract: arriving on a tab must never surface a
hidden view's last committed (stale) frame. Covers go up first, a
silent (animation-free) refresh replays no enter animation, and reveal
fires only after presented frames ack — with a timer fallback.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import first)

from PyQt6.QtWidgets import QApplication
import pytest


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


_OPEN = []


@pytest.fixture(autouse=True)
def _close_tabs():
    yield
    while _OPEN:
        w = _OPEN.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


# ── Renderer silent-path parity (both copies) ─────────────────────────

@pytest.mark.parametrize("path", [
    "display/display.js",
    "ui/widgets/display_view.py",
])
def test_silent_resync_path_exists(path):
    src = open(path).read()
    assert "handlePayload(data, silent)" in src
    assert "function refreshPayload(data)" in src
    assert "function refreshClear()" in src


def test_obs_renderer_skips_animation_on_silent():
    # Only display.js (OBS) has enter/exit animations — the silent
    # resync must replay neither nor touch transition memory.
    src = open("display/display.js").read()
    assert "if (!silent)" in src


# ── Panel orchestration ───────────────────────────────────────────────

def _panel(qapp):
    from ui.panels.live_preview_panel import LivePreviewPanel
    panel = LivePreviewPanel()
    _OPEN.append(panel)
    qapp.processEvents()
    return panel


def _fake_views(panel):
    calls = {}

    def _refresh(which):
        def _fn(payload, cb=None):
            calls.setdefault(which, []).append((payload, cb))
        return _fn

    panel.live_view.refresh = _refresh("live")
    panel.live_view.refresh_clear = lambda cb=None: calls.setdefault("clear-live", []).append(cb)
    panel.preview_view.refresh = _refresh("preview")
    return calls


def test_refresh_views_covers_then_reveals_on_acks(qapp):
    panel = _panel(qapp)
    calls = _fake_views(panel)
    done = []
    live = {"action": "display", "text": "A"}
    preview = {"action": "display", "text": "B"}
    panel.refresh_views(live, preview, lambda: done.append(True))
    assert panel._live_cover.isVisibleTo(panel) or panel._live_cover.isVisible()
    assert calls["live"] and calls["preview"]
    assert done == []
    # First ack: still covered.
    calls["live"][0][1]()
    assert done == []
    # Second ack: revealed + done.
    calls["preview"][0][1]()
    assert done == [True]
    assert not panel._live_cover.isVisible()
    assert not panel._preview_cover.isVisible()


def test_refresh_views_clear_path(qapp):
    panel = _panel(qapp)
    calls = _fake_views(panel)
    done = []
    panel.refresh_views("clear", None, lambda: done.append(True))
    assert "clear-live" in calls
    assert "preview" not in calls
    calls["clear-live"][0]()
    assert done == [True]
    assert not panel._live_cover.isVisible()


def test_refresh_views_skip_is_immediate(qapp):
    panel = _panel(qapp)
    _fake_views(panel)
    done = []
    panel.refresh_views(None, None, lambda: done.append(True))
    assert done == [True]
    assert not panel._live_cover.isVisible()
    assert not panel._preview_cover.isVisible()


def test_covers_are_native_windows(qapp):
    """Covers must occlude the WebEngine surface itself: only a native
    window stacks above a native child surface — a raster sibling may
    paint underneath it. Transparent-for-mouse keeps clicks reaching
    the overlays beneath."""
    from PyQt6.QtCore import Qt
    panel = _panel(qapp)
    for cover in (panel._live_cover, panel._preview_cover):
        assert cover.testAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        assert cover.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
