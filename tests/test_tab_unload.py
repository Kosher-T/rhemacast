"""Tab unloading (Firefox-style): release a tab's view, reload on click.

Only tabs whose content is disposable or fully restorable may be released.
Scriptures and Decks own the live-output stepping ops and the STT/worker
bindings, so they are blocked with a reason; Library, Theme Designer, and
Settings unload and rebuild.

The live pipeline is not a participant in any of this: unloading a tab must
never stop the service, reset display state, or replace the Scripture tab.

One window is shared by the suite: every ``MainWindow`` owns QtWebEngine
views, and building one per test makes the file take minutes. The first test
asserts the pristine startup state, so it must stay first.
"""

import copy
import gc
import os
import weakref

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import rule)

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


@pytest.fixture(scope="module")
def window(qapp):
    # tests/conftest.py already redirects core.database at a throwaway DB
    # for the whole session.
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    w.resize(1600, 900)
    qapp.processEvents()
    try:
        yield w
    finally:
        w.close()
        w.deleteLater()
        qapp.processEvents()


@pytest.fixture(autouse=True)
def guard_messages(monkeypatch):
    """Record unload-guard messages instead of opening a modal dialog.

    ``_unload_tab`` shows ``ui.dialogs.information`` for a blocked tab; a
    modal box in a headless test run waits for a click that never comes.
    """
    from ui import dialogs

    calls = []

    def _information(parent, title, text, *args, **kwargs):
        calls.append((title, text))
        return dialogs.Ok

    monkeypatch.setattr(dialogs, "information", _information)
    return calls


def _flush(qapp):
    """Run deferred deletes now — deleteLater alone leaves the widget alive."""
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    qapp.processEvents()


def _open(window, key):
    window._switch_tab(list(window._tabs).index(key), key)


def test_startup_marks_only_scriptures_loaded(window):
    """Lazy tabs start pending (grey); only the eager tab is loaded."""
    loaded = {key: window._tab_buttons[key]._loaded for key in window._tabs}
    assert loaded == {
        "SCRIPTURE": True,
        "SLIDES": False,
        "LIBRARY": False,
        "THEME DESIGNER": False,
        "SETTINGS": False,
    }
    for key in ("SLIDES", "LIBRARY", "THEME DESIGNER", "SETTINGS"):
        placeholder = window._tabs[key]
        assert not placeholder.is_loaded
        # Pending, not "unloaded": nothing has been released yet.
        assert not placeholder.is_unloaded


def test_display_workspaces_refuse_to_unload(window, guard_messages):
    """Scriptures and Decks are live-output workspaces, not views."""
    for key in ("SCRIPTURE", "SLIDES"):
        allowed, reason = window._can_unload_tab(key)
        assert allowed is False
        assert reason
        assert window._unload_tab(key) is False
    assert len(guard_messages) == 2
    assert all(title == "Cannot unload tab" for title, _ in guard_messages)
    # Scriptures is eager content, not a placeholder: still fully alive.
    assert window._tabs["SCRIPTURE"].stt_panel is not None


def test_library_unload_releases_and_reload_rebuilds(window, qapp):
    _open(window, "LIBRARY")
    placeholder = window._tabs["LIBRARY"]
    assert placeholder.is_loaded
    old_widget = placeholder.real_widget
    old_ref = weakref.ref(old_widget)

    assert window._unload_tab("LIBRARY") is True
    assert not placeholder.is_loaded
    assert placeholder.is_unloaded
    assert placeholder.real_widget is None
    assert window._tab_buttons["LIBRARY"]._loaded is False
    assert "unloaded" in window._tab_buttons["LIBRARY"].toolTip().lower()
    assert "unload" in placeholder.loading_label.text().lower()

    _flush(qapp)
    del old_widget
    gc.collect()
    assert old_ref() is None, "the released tab must not stay referenced"

    _open(window, "LIBRARY")
    assert placeholder.is_loaded
    assert not placeholder.is_unloaded
    assert placeholder.real_widget is not None
    assert window._tab_buttons["LIBRARY"]._loaded is True
    assert window._tab_buttons["LIBRARY"].toolTip() == ""
    assert "LIBRARY" not in window._tab_state


def test_settings_refuses_to_unload_during_build_or_key_capture(window):
    _open(window, "SETTINGS")
    settings = window._tabs["SETTINGS"].real_widget

    settings._build_process = object()
    try:
        allowed, reason = window._can_unload_tab("SETTINGS")
        assert allowed is False
        assert "index build" in reason.lower()
    finally:
        settings._build_process = None

    from ui.widgets.hotkey_editor import KeyboardHandler

    class _Capturing:
        _capturing = True

    previous = KeyboardHandler._target
    KeyboardHandler._target = _Capturing()
    try:
        allowed, reason = window._can_unload_tab("SETTINGS")
        assert allowed is False
        assert "hotkey" in reason.lower()
    finally:
        KeyboardHandler._target = previous

    assert window._can_unload_tab("SETTINGS") == (True, "")


def test_settings_restores_section_after_reload(window, qapp):
    _open(window, "SETTINGS")
    placeholder = window._tabs["SETTINGS"]
    old_widget = placeholder.real_widget
    old_timer = old_widget._hw_timer
    old_widget._switch_section("Hotkeys")

    assert window._unload_tab("SETTINGS") is True
    assert window._tab_state["SETTINGS"]["section"] == "Hotkeys"

    _flush(qapp)
    with pytest.raises(RuntimeError):
        old_timer.isActive()  # the settings-owned timer died with the tab

    _open(window, "SETTINGS")
    assert placeholder.is_loaded
    assert placeholder.real_widget is not old_widget
    assert placeholder.real_widget._current_section == "Hotkeys"
    assert "SETTINGS" not in window._tab_state


def test_settings_signals_are_rewired_after_reload(window, monkeypatch):
    """A rebuilt Settings tab must be re-attached to the window's handlers."""
    _open(window, "SETTINGS")
    window._unload_tab("SETTINGS")

    calls = []
    monkeypatch.setattr(window, "_on_hotkey_bindings_changed",
                        lambda bindings: calls.append(bindings))

    _open(window, "SETTINGS")
    placeholder = window._tabs["SETTINGS"]
    placeholder.real_widget._hotkey_editor.bindings_changed.emit({"probe": "F1"})
    assert calls, "rebuilt Settings tab is not wired to the main window"


def test_theme_designer_refuses_to_unload_unsaved_edits(window):
    _open(window, "THEME DESIGNER")
    placeholder = window._tabs["THEME DESIGNER"]
    designer = placeholder.real_widget

    # A pristine designer has nothing to lose.
    assert designer.is_dirty() is False
    assert window._can_unload_tab("THEME DESIGNER") == (True, "")

    designer._working_theme["label"] = "Edited, not saved"
    allowed, reason = window._can_unload_tab("THEME DESIGNER")
    assert allowed is False
    assert "unsaved" in reason.lower()

    designer._working_theme = copy.deepcopy(designer._original_theme)
    assert window._can_unload_tab("THEME DESIGNER") == (True, "")
    assert window._unload_tab("THEME DESIGNER") is True
    assert window._theme_designer_tab is None

    _open(window, "THEME DESIGNER")
    assert placeholder.is_loaded
    assert window._theme_designer_tab is placeholder.real_widget


def test_unloading_a_safe_tab_never_touches_the_live_pipeline(window, monkeypatch):
    """Scriptures keeps its objects, its display handle, and the service."""
    import core.display_state as display_state
    import core.service_manager as service_manager

    side_effects = []

    def _tripwire(name):
        def _record(*args, **kwargs):
            side_effects.append(name)
        return _record

    monkeypatch.setattr(service_manager.manager, "initiate_shutdown",
                        _tripwire("service shutdown"))
    monkeypatch.setattr(display_state, "reset_display_states",
                        _tripwire("display reset"))

    scripture = window._tabs["SCRIPTURE"]
    stt_panel = scripture.stt_panel
    queue_panel = scripture.queue_panel
    handle = scripture._display

    _open(window, "LIBRARY")
    assert window._unload_tab("LIBRARY") is True
    _open(window, "LIBRARY")

    assert side_effects == []
    assert window._tabs["SCRIPTURE"] is scripture
    assert scripture.stt_panel is stt_panel
    # The operator-queue worker is bound to this panel for the app's life,
    # so transcripts still arrive while another tab was unloaded.
    assert scripture.queue_panel is queue_panel
    assert scripture._display is handle


def test_unloaded_state_does_not_survive_a_restart(qapp):
    """Unload state is in-memory only: a new window starts with pending tabs."""
    from ui.main_window import MainWindow

    first = MainWindow()
    first.show()
    qapp.processEvents()
    try:
        _open(first, "LIBRARY")
        assert first._unload_tab("LIBRARY") is True
    finally:
        first.close()
        first.deleteLater()
        qapp.processEvents()

    second = MainWindow()
    second.show()
    qapp.processEvents()
    try:
        library = second._tabs["LIBRARY"]
        assert not library.is_loaded
        assert not library.is_unloaded, "unload state was persisted"
        assert second._tab_state == {}
    finally:
        second.close()
        second.deleteLater()
        qapp.processEvents()
