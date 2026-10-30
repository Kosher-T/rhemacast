"""Dialog and popup language: one style, one order, one keyboard contract.

These tests are the guard rails for ``ui/app_style.py``, ``ui/dialogs`` and
``ui/popups``. They do not open anything modal: the session fixture in
``tests/conftest.py`` turns an unstubbed dialog into an immediate failure.
"""

import os
import re
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ui.widgets.display_view  # noqa: F401  (WebEngine pre-import rule)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QListView, QStyleFactory, QWidget,
)

ROOT = Path(__file__).resolve().parents[1]

# The app stylesheet wraps the base style in QStyleSheetStyle, which reports
# an empty objectName(). Record the base name at install time instead.
_BASE_STYLE = {}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test-style-dialogs"])

    from ui.app_style import install as install_app_style
    assert install_app_style(app) is True
    _BASE_STYLE["name"] = app.style().objectName()

    # Mirrors core/ui.py: the application stylesheet is set BEFORE the app
    # font. See test_widget_font_comes_from_the_app_not_the_theme().
    from ui.tokens import scrollbar_qss
    from ui.popups import tooltip_qss
    app.setStyleSheet(scrollbar_qss() + "\n" + tooltip_qss())

    from ui.typography import install as install_typography
    install_typography(app)

    from ui.app_theme import apply_palette
    apply_palette(app)
    return app


# ── One widget style ────────────────────────────────────────────────────────
def test_fusion_is_the_active_style(qapp):
    assert _BASE_STYLE["name"].lower() == "fusion"
    assert QStyleFactory.create("fusion") is not None


def test_popup_animations_are_off(qapp):
    assert not qapp.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
    assert not qapp.isEffectEnabled(Qt.UIEffect.UI_FadeMenu)
    assert not qapp.isEffectEnabled(Qt.UIEffect.UI_FadeTooltip)


def test_widget_font_comes_from_the_app_not_the_theme(qapp):
    """The app stylesheet must not hand widget fonts to the platform theme.

    GTK and Windows platform themes each ship a default family. If the
    stylesheet is installed after the app font, QStyleSheetStyle resolves
    new widgets against that family instead of Inter. The fixture mirrors
    ``core/ui.py``'s order, so this fails on a themed desktop if the order
    regresses.
    """
    from PyQt6.QtWidgets import QLabel

    label = QLabel("text")
    assert label.font().family() == qapp.font().family()


# ── Painted icons / no platform icon lookup ─────────────────────────────────
def test_dialog_layer_never_asks_the_platform_for_an_icon():
    import ast

    for relative in ("ui/dialogs/__init__.py", "ui/popups.py",
                     "ui/app_style.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in (
                    "standardIcon", "fromTheme"):
                calls.append((node.attr, node.lineno))
        assert calls == [], (relative, calls)


# ── Direct use is banned outside the dialog package ─────────────────────────
def test_no_direct_message_or_input_dialog_outside_the_dialog_package():
    forbidden = ("QMessageBox", "QInputDialog", "QErrorMessage")
    offenders = []
    for folder in ("ui", "core", "cloud"):
        for path in (ROOT / folder).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.parent == ROOT / "ui" / "dialogs":
                continue
            text = path.read_text(encoding="utf-8")
            for name in forbidden:
                if re.search(rf"\b{name}\b", text):
                    offenders.append((str(path.relative_to(ROOT)), name))
    assert offenders == []


def test_dialog_layer_has_no_raw_colour_literals():
    """New dialog/popup modules must speak only in tokens."""
    for relative in ("ui/dialogs/__init__.py",
                     "ui/dialogs/add_translation_dialog.py",
                     "ui/popups.py", "ui/app_style.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", source)
        assert literals == [], (relative, literals)


# ── Button order and keyboard contract ──────────────────────────────────────
def _dialog(buttons, default=None):
    from ui import dialogs

    dialog = dialogs.MessageDialog(
        None, icon="question", title="Test", text="Body")
    dialog.setStandardButtons(buttons)
    if default is not None:
        dialog.setDefaultButton(default)
    return dialog


def _order(dialog):
    from ui import dialogs

    return dialogs.standard_button_order(dialog)


def _press(qapp, dialog, key):
    dialog.show()
    qapp.processEvents()
    QTest.keyClick(dialog, key)
    qapp.processEvents()
    clicked = dialog.clickedButton()
    text = clicked.text() if clicked is not None else None
    result = dialog.result()
    dialog.close()
    return text, result


def test_standard_button_order(qapp):
    from ui import dialogs

    assert _order(_dialog(dialogs.Ok | dialogs.Cancel)) == ["OK", "Cancel"]
    assert _order(_dialog(dialogs.Yes | dialogs.No)) == ["Yes", "No"]
    assert _order(_dialog(
        dialogs.Save | dialogs.Discard | dialogs.Cancel)) == [
            "Save", "Discard", "Cancel"]


def test_custom_actions_sit_before_the_dismissive_sequence(qapp):
    from ui import dialogs

    dialog = dialogs.MessageDialog(None, title="Test", text="Body")
    dialog.setStandardButtons(dialogs.Yes | dialogs.No)
    dialog.addButton("Skip existing", dialogs.ButtonRole.ActionRole)
    dialog.addButton("Overwrite existing", dialogs.ButtonRole.ActionRole)
    dialog.addButton(dialogs.Cancel)
    assert _order(dialog) == [
        "Skip existing", "Overwrite existing", "Yes", "No", "Cancel"]


def test_enter_and_escape_match_the_measured_qmessagebox_table(qapp):
    from ui import dialogs

    cases = (
        # buttons, default, key, expected label, expected standard result
        (dialogs.Ok, None, Qt.Key.Key_Return, "OK", dialogs.Ok),
        (dialogs.Ok, None, Qt.Key.Key_Escape, "OK", dialogs.Ok),
        (dialogs.Yes | dialogs.No, dialogs.No,
         Qt.Key.Key_Return, "No", dialogs.No),
        (dialogs.Yes | dialogs.No, dialogs.No,
         Qt.Key.Key_Escape, "No", dialogs.No),
        (dialogs.Save | dialogs.Discard | dialogs.Cancel, dialogs.Save,
         Qt.Key.Key_Return, "Save", dialogs.Save),
        (dialogs.Save | dialogs.Discard | dialogs.Cancel, dialogs.Save,
         Qt.Key.Key_Escape, "Cancel", dialogs.Cancel),
    )
    for buttons, default, key, label, result in cases:
        text, actual = _press(qapp, _dialog(buttons, default), key)
        assert text == label, (buttons, key)
        assert int(actual) == int(result), (buttons, key, actual)


def test_question_message_keeps_the_no_default(qapp, monkeypatch):
    """A Yes/No question is built with No as its explicit default."""
    from ui import dialogs

    captured = {}

    def fake_run(dialog):
        captured["dialog"] = dialog
        return dialogs.No

    monkeypatch.setattr(dialogs, "_run", fake_run)
    dialogs._message(None, "question", "Title", "Body",
                     dialogs.Yes | dialogs.No, dialogs.No)
    assert captured["dialog"]._default_button.text() == "No"


# ── Placement ───────────────────────────────────────────────────────────────
def test_dialog_centers_on_its_parent(qapp):
    if QGuiApplication.platformName().startswith("wayland"):
        pytest.skip("Wayland compositors place transient children")

    parent = QWidget()
    parent.setGeometry(120, 100, 800, 600)
    parent.show()
    qapp.processEvents()
    try:
        from ui import dialogs

        dialog = dialogs.MessageDialog(parent, icon="question",
                                       title="Test", text="Body")
        dialog.setStandardButtons(dialogs.Ok)
        dialog.show()
        qapp.processEvents()
        parent_center = parent.frameGeometry().center()
        dialog_center = dialog.frameGeometry().center()
        assert abs(parent_center.x() - dialog_center.x()) <= 2
        assert abs(parent_center.y() - dialog_center.y()) <= 2
        dialog.close()
    finally:
        parent.close()


def test_non_modal_offline_prompt_keeps_a_reference_and_does_not_block(
        qapp, monkeypatch, tmp_path):
    from ui import dialogs
    from ui.main_window import MainWindow
    import cloud.extraction as extraction

    queue = tmp_path / "offline_queue.jsonl"
    queue.write_text('{"service": "past"}\n', encoding="utf-8")
    monkeypatch.setattr(extraction, "OFFLINE_QUEUE_PATH", str(queue))

    host = QWidget()
    host.resize(640, 480)
    host.show()
    qapp.processEvents()

    # The old code used show(), not exec(). Make blocking impossible so a
    # regression fails here instead of hanging the suite.
    monkeypatch.setattr(
        dialogs.MessageDialog, "exec",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("offline prompt must not block")))

    started = time.monotonic()
    MainWindow._check_offline_queue(host)
    elapsed = time.monotonic() - started
    qapp.processEvents()

    message = getattr(host, "_offline_msg", None)
    assert message is not None
    assert message.parentWidget() is host
    assert message.isVisible()
    assert not message.isModal()
    assert elapsed < 1.0, "show() must return before the operator clicks"
    assert dialogs.standard_button_order(message) == [
        "Process Now", "After Service"]

    message.button(dialogs.Yes).click()
    qapp.processEvents()
    assert message.result() == int(dialogs.Yes)
    assert not message.isVisible()

    host.close()


# ── Combo dropdown plumbing ─────────────────────────────────────────────────
def test_install_combo_replaces_the_view_and_delegate(qapp):
    from ui.popups import ComboRowDelegate, install_combo

    combo = QComboBox()
    assert install_combo(combo) is combo
    assert install_combo(combo) is combo, "idempotent"
    assert combo.property("_rc_combo_installed") is True
    assert isinstance(combo.view(), QListView)
    assert isinstance(combo.view().itemDelegate(), ComboRowDelegate)
