"""Ctrl+S saves the schedule — in display tabs, and nowhere else.

Ctrl+S is deliberately NOT a QShortcut: inside the display view Chromium
claims it as "save page" before shortcut matching runs. These tests pin the
interception contract (binding id, display-tab scoping, one save per press).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QCoreApplication

# Must precede the QApplication: the main window imports QtWebEngine, which
# refuses to initialise after the app exists.
QCoreApplication.setAttribute(
    Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)


class _FakeEvent:
    def __init__(self, key, mods=()):
        self._key = key
        self._mods = mods

    def key(self):
        return self._key

    def modifiers(self):
        return self._mods


class _Panel:
    """Stand-in for SchedulePanel: records saves instead of prompting."""

    def __init__(self, current_file="service.json", items=None):
        self.current_file = current_file
        self._items = [{"ref": "JHN 3:16"}] if items is None else items
        self.saved = 0

    def get_schedule_data(self):
        return list(self._items)

    def save_schedule(self, file_path=None):
        self.saved += 1
        return True


class _Tab:
    def __init__(self, panel=None):
        if panel is not None:
            self.schedule_panel = panel


class _Placeholder:
    """A lazy tab that has not been built yet — no schedule_panel of its own."""

    def __init__(self, real_widget=None):
        self.real_widget = real_widget
        self._loaded = real_widget is not None


class _Stack:
    current = 0

    def currentIndex(self):
        return self.current


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(["test-save-schedule"])


def _stub(qapp):
    """Minimal MainWindow stand-in: tabs, stack, bindings, no widgets."""
    import ui.main_window as mw

    class _Stub:
        # Production reads both tables off the class; the stand-in must carry
        # them too or the display-tab guard silently sees "no tab".
        _HOTKEY_DEFAULTS = mw.MainWindow._HOTKEY_DEFAULTS
        _DISPLAY_TAB_KEYS = mw.MainWindow._DISPLAY_TAB_KEYS

        def __init__(self):
            self._tabs = {}
            self.stack = _Stack()
            self._hotkey_bindings = dict(mw.MainWindow._HOTKEY_DEFAULTS)

        def isActiveWindow(self):
            return True

        def _hotkey_capture_active(self):
            return False

        def _binding_combo(self, action_id):
            return mw.MainWindow._binding_combo(self, action_id)

        def _active_display_tab(self):
            return mw.MainWindow._active_display_tab(self)

        def _save_active_schedule(self):
            return mw.MainWindow._save_active_schedule(self)

        def _maybe_save_schedule_key(self, event):
            return mw.MainWindow._maybe_save_schedule_key(self, event)

    return _Stub()


def _ctrl_s():
    return _FakeEvent(Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)


def _build(qapp, panels=(("SCRIPTURE", None), ("SLIDES", None),
                         ("LIBRARY", None), ("SETTINGS", None))):
    stub = _stub(qapp)
    for key, panel in panels:
        stub._tabs[key] = _Tab(panel) if panel is not None else _Tab()
    return stub


def test_default_binding_is_ctrl_s_and_editable(qapp):
    import ui.main_window as mw
    from ui.widgets.hotkey_editor import DEFAULT_BINDINGS

    name, desc, default, scope = DEFAULT_BINDINGS["save_schedule"]
    assert default == "Ctrl+S"
    assert scope == "global"
    assert "schedule" in desc.lower()
    # Both tables must agree, or Settings would show a key the window ignores.
    assert mw.MainWindow._HOTKEY_DEFAULTS["save_schedule"] == "Ctrl+S"
    assert name == "Save Schedule"


def test_ctrl_s_saves_on_the_active_display_tab(qapp):
    panel = _Panel()
    stub = _build(qapp, [("SCRIPTURE", panel), ("SLIDES", _Panel()),
                         ("LIBRARY", None), ("SETTINGS", None)])
    stub.stack.current = 0
    assert stub._maybe_save_schedule_key(_ctrl_s()) is True
    assert panel.saved == 1, "one press must save exactly once"


def test_ctrl_s_targets_the_slides_schedule_when_slides_is_shown(qapp):
    scripture, slides = _Panel(), _Panel()
    stub = _build(qapp, [("SCRIPTURE", scripture), ("SLIDES", slides),
                         ("LIBRARY", None), ("SETTINGS", None)])
    stub.stack.current = 1
    assert stub._maybe_save_schedule_key(_ctrl_s()) is True
    assert slides.saved == 1
    assert scripture.saved == 0


def test_ctrl_s_is_ignored_outside_display_tabs(qapp):
    scripture = _Panel()
    stub = _build(qapp, [("SCRIPTURE", scripture), ("SLIDES", _Panel()),
                         ("LIBRARY", None), ("SETTINGS", None)])
    for index in (2, 3):                      # LIBRARY, SETTINGS
        stub.stack.current = index
        assert stub._maybe_save_schedule_key(_ctrl_s()) is False, index
    assert scripture.saved == 0, "core tabs must not reach the schedule"


def test_unbuilt_slides_tab_saves_through_the_shared_model(qapp):
    """A lazy display tab has no panel yet; the model is shared, so the
    loaded workspace saves the one schedule — never a second copy."""
    scripture = _Panel()
    stub = _build(qapp, [("SCRIPTURE", scripture), ("LIBRARY", None)])
    stub._tabs["SLIDES"] = _Placeholder()     # never opened
    stub.stack.current = list(stub._tabs).index("SLIDES")
    assert stub._maybe_save_schedule_key(_ctrl_s()) is True
    assert scripture.saved == 1


def test_loaded_placeholder_uses_its_own_panel(qapp):
    scripture, slides = _Panel(), _Panel()
    stub = _build(qapp, [("SCRIPTURE", scripture), ("LIBRARY", None)])
    stub._tabs["SLIDES"] = _Placeholder(_Tab(slides))
    stub.stack.current = list(stub._tabs).index("SLIDES")
    stub._maybe_save_schedule_key(_ctrl_s())
    assert slides.saved == 1
    assert scripture.saved == 0


def test_empty_unsaved_schedule_does_not_prompt(qapp):
    """No file and no items: consuming the key is right, a Save dialog is not."""
    panel = _Panel(current_file=None, items=[])
    stub = _build(qapp, [("SCRIPTURE", panel), ("LIBRARY", None)])
    stub.stack.current = 0
    assert stub._maybe_save_schedule_key(_ctrl_s()) is True
    assert panel.saved == 0


def test_rebinding_moves_the_hotkey(qapp):
    panel = _Panel()
    stub = _build(qapp, [("SCRIPTURE", panel), ("LIBRARY", None)])
    stub.stack.current = 0
    stub._hotkey_bindings["save_schedule"] = "Ctrl+Shift+K"
    assert stub._maybe_save_schedule_key(_ctrl_s()) is False
    assert panel.saved == 0
    chord = _FakeEvent(Qt.Key.Key_K,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.ShiftModifier)
    assert stub._maybe_save_schedule_key(chord) is True
    assert panel.saved == 1


def test_plain_s_and_extra_modifiers_are_left_alone(qapp):
    panel = _Panel()
    stub = _build(qapp, [("SCRIPTURE", panel), ("LIBRARY", None)])
    stub.stack.current = 0
    assert stub._maybe_save_schedule_key(_FakeEvent(Qt.Key.Key_S)) is False
    assert stub._maybe_save_schedule_key(
        _FakeEvent(Qt.Key.Key_S,
                   Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.AltModifier)) is False
    assert panel.saved == 0


def test_hotkey_capture_state_suppresses_the_hotkey(qapp):
    panel = _Panel()
    stub = _build(qapp, [("SCRIPTURE", panel), ("LIBRARY", None)])
    stub.stack.current = 0
    stub._hotkey_capture_active = lambda: True
    assert stub._maybe_save_schedule_key(_ctrl_s()) is False
    assert panel.saved == 0


def test_replay_path_also_saves(qapp):
    """A press lost to window inactivation is replayed through
    _invoke_hotkey_action, which must know this action too."""
    import ui.main_window as mw
    panel = _Panel()
    stub = _build(qapp, [("SCRIPTURE", panel), ("LIBRARY", None)])
    stub.stack.current = 0
    assert mw.MainWindow._invoke_hotkey_action(stub, "save_schedule") is True
    assert panel.saved == 1
