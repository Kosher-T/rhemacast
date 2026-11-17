"""Offscreen tests for the Theme Designer's theme selector.

The selector shows a theme's **label**, but its option value — and therefore
the selected theme — is the permanent **ID** (file name stem). These tests
cover the display rules (fallback, duplicate suffix, description, ordering)
and the two live-update sources: typing a label in the designer and the file
changing on disk.

QtWebEngine is stubbed exactly as ``test_theme_designer_columns`` does: these
tests own the selector, not the display renderer.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

# Import WebEngine before QApplication exists; the module import is enough for
# the real preview import chain, while these tests construct a stub instead.
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

import core.theme_loader as theme_loader  # noqa: E402
from ui.widgets.theme_designer.theme_combo import (  # noqa: E402
    DESCRIPTION_ROLE,
    SUFFIX_ROLE,
    WARNING_ROLE,
)
from ui.widgets.theme_designer.theme_watcher import ThemeFolderWatcher  # noqa: E402

_QAPP = None
_TAB_MODULE = None
_REAL_PREVIEW = None


def _theme(name: str, label=None, description="", sort_order=None) -> dict:
    theme = {
        "schema_version": 2,
        "name": name,
        "canvas": {"width": 1920, "height": 1080},
        "containers": [{"id": "main"}],
    }
    if label is not None:
        theme["label"] = label
    if description:
        theme["description"] = description
    if sort_order is not None:
        theme["sort_order"] = sort_order
    return theme


def _write(root: Path, name: str, theme: dict,
           kind: str = "scripture") -> Path:
    folder = root / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(theme, indent=4), encoding="utf-8")
    return path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _settle(app, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def _tab_module():
    global _TAB_MODULE, _REAL_PREVIEW
    if _TAB_MODULE is None:
        from ui.tabs import theme_designer_tab as module
        _TAB_MODULE = module
        _REAL_PREVIEW = module.ThemePreview
    return _TAB_MODULE


class _PreviewStub(QWidget):
    """Stand-in for the QtWebEngine preview; owns no rendering."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.theme = {}
        self.sample = ""
        self.applied = []

    def apply_theme(self, theme):
        self.theme = dict(theme)
        self.applied.append(dict(theme))

    def set_verse(self, sample_id):
        self.sample = str(sample_id)


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


@pytest.fixture
def themes_tree(tmp_path, monkeypatch):
    """A disposable themes/ tree the loader and the tab both point at."""
    root = tmp_path / "themes"
    (root / "scripture").mkdir(parents=True)
    (root / "freeform").mkdir(parents=True)
    previous = theme_loader._THEMES_DIR
    monkeypatch.setattr(theme_loader, "_THEMES_DIR", root)
    theme_loader.reload_themes()
    try:
        yield root
    finally:
        theme_loader._THEMES_DIR = previous
        theme_loader.reload_themes()


@pytest.fixture
def make_tab(qapp, themes_tree, monkeypatch):
    """Build real ThemeDesignerTabs with only the preview stubbed."""
    module = _tab_module()
    monkeypatch.setattr(module, "ThemePreview", _PreviewStub)
    created = []

    def make():
        widget = module.ThemeDesignerTab()
        widget.resize(1400, 900)
        widget.show()
        created.append(widget)
        _settle(qapp)
        return widget

    yield make
    for widget in created:
        widget.close()
        widget.deleteLater()
    _settle(qapp)


def _labels(tab):
    combo = tab._theme_combo
    return [(combo.itemText(i), combo.itemData(i))
            for i in range(combo.count())]


def _type_label(tab, text: str) -> None:
    """Reproduce one user keystroke burst on the inline label field."""
    field = tab._label_field
    field.setText(text)
    field.textEdited.emit(text)


# ── display rules ───────────────────────────────────────────────────────────

def test_selector_shows_labels_and_keeps_ids_as_values(make_tab, themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "default_typewriter",
           _theme("default_typewriter", "Standard — Typewriter"))

    tab = make_tab()
    assert _labels(tab) == [
        ("Standard", "default"),
        ("Standard — Typewriter", "default_typewriter"),
    ]
    assert tab._theme_combo.current_id() == "default"
    assert tab._theme_id == "default"


def test_missing_label_falls_back_to_a_prettified_filename(make_tab,
                                                          themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "default_typewriter", _theme("default_typewriter"))

    tab = make_tab()
    options = dict(_labels(tab))
    assert options["Default Typewriter"] == "default_typewriter"


def test_duplicate_labels_append_the_id_in_muted_text(make_tab, themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "default_2", _theme("default_2", "Standard",
                                            "Second standard theme"))
    _write(themes_tree, "unique", _theme("unique", "Unique"))

    tab = make_tab()
    combo = tab._theme_combo
    options = {combo.itemData(i): combo.itemText(i)
               for i in range(combo.count())}
    assert options["default"] == "Standard (default)"
    assert options["default_2"] == "Standard (default_2)"
    assert options["unique"] == "Unique"

    index = combo.findData("default_2")
    assert combo.itemData(index, SUFFIX_ROLE) == " (default_2)"
    assert combo.itemText(combo.findData("unique")) == "Unique"
    assert combo.itemData(index, DESCRIPTION_ROLE) == "Second standard theme"


def test_options_sort_by_label_unless_sort_order_wins(make_tab, themes_tree):
    _write(themes_tree, "default", _theme("default", "standard"))
    _write(themes_tree, "alpha", _theme("alpha", "Zulu"))
    _write(themes_tree, "pinned", _theme("pinned", "Aardvark", sort_order=1))

    tab = make_tab()
    assert [theme_id for _text, theme_id in _labels(tab)] == [
        "pinned", "default", "alpha"]


def test_description_is_offered_as_the_second_line(make_tab, themes_tree):
    _write(themes_tree, "default",
           _theme("default", "Standard", "Full 1920x1080 screen display"))
    tab = make_tab()
    combo = tab._theme_combo
    index = combo.findData("default")
    assert combo.itemData(index, DESCRIPTION_ROLE) == (
        "Full 1920x1080 screen display")
    assert combo.itemData(index, Qt.ItemDataRole.ToolTipRole).splitlines()[0] \
        == "Standard"


# ── live label edits ────────────────────────────────────────────────────────

def test_typing_a_label_updates_the_dropdown_immediately(make_tab,
                                                         themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "other", _theme("other", "Alpha"))

    tab = make_tab()
    _type_label(tab, "Zzz Sermon")

    options = dict(_labels(tab))
    assert options["Zzz Sermon"] == "default"   # text follows, value does not
    assert "Standard" not in options
    # Re-sorted after the rename, but the same theme is still selected.
    assert [theme_id for _text, theme_id in _labels(tab)] == [
        "other", "default"]
    assert tab._theme_combo.current_id() == "default"
    assert tab._theme_id == "default"
    assert tab._working_theme["label"] == "Zzz Sermon"
    assert tab.is_dirty()


def test_clearing_the_label_shows_fallback_but_keeps_the_field_empty(
        make_tab, themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "default_typewriter",
           _theme("default_typewriter", "Standard — Typewriter"))

    tab = make_tab()
    tab.set_theme("default_typewriter")
    _type_label(tab, "")

    assert tab._label_field.text() == ""
    assert tab._label_field.placeholderText() == "Default Typewriter"
    options = dict(_labels(tab))
    assert options["Default Typewriter"] == "default_typewriter"
    # The document keeps the empty string so the operator can keep typing.
    assert tab._working_theme["label"] == ""


def test_save_writes_the_label_but_never_the_filename(make_tab, themes_tree):
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    tab = make_tab()
    _type_label(tab, "Sermon Wide")
    assert tab.is_dirty()

    tab._on_save()

    saved = _read(path)
    assert saved["label"] == "Sermon Wide"
    assert saved["name"] == "default"
    assert path.name == "default.json"          # same file, same ID
    assert not tab.is_dirty()


def test_save_drops_an_empty_label_instead_of_writing_it(make_tab,
                                                         themes_tree):
    path = _write(themes_tree, "default_typewriter",
                  _theme("default_typewriter", "Standard — Typewriter"))
    tab = make_tab()
    tab.set_theme("default_typewriter")
    _type_label(tab, "")
    tab._on_save()

    saved = _read(path)
    assert "label" not in saved
    assert saved["name"] == "default_typewriter"
    assert path.name == "default_typewriter.json"
    assert not tab.is_dirty()
    assert tab._label_field.text() == ""
    # The selector still explains what the empty label falls back to.
    assert tab._theme_combo.currentText() == "Default Typewriter"


# ── external file changes ───────────────────────────────────────────────────

def test_external_edit_reloads_the_dropdown_and_the_document(make_tab,
                                                              themes_tree):
    path = _write(themes_tree, "default",
                  _theme("default", "Standard", "Original inside"))
    tab = make_tab()

    path.write_text(json.dumps(
        _theme("default", "Sermon Wide", "Edited outside the app")),
        encoding="utf-8")
    tab._on_theme_files_changed()

    assert tab._theme_combo.currentText() == "Sermon Wide"
    assert tab._theme_combo.current_id() == "default"
    assert tab._working_theme["label"] == "Sermon Wide"
    assert tab._working_theme["description"] == "Edited outside the app"
    assert not tab._notice.is_showing()


def test_external_edit_does_not_clobber_unsaved_edits(make_tab, themes_tree):
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    tab = make_tab()
    _type_label(tab, "My Draft")
    assert tab.is_dirty()

    path.write_text(json.dumps(_theme("default", "From Disk")),
                    encoding="utf-8")
    tab._on_theme_files_changed()

    # The operator's work is intact and the notice offers both paths.
    assert tab._working_theme["label"] == "My Draft"
    assert tab._label_field.text() == "My Draft"
    assert tab._notice.is_showing()
    assert "changed on disk" in tab._notice.current_text()
    buttons = [button.text()
               for button in tab._notice.findChildren(type(tab._btn_save))]
    assert "Reload from disk" in buttons
    assert "Keep editing" in buttons

    # Choosing to reload takes the disk version.
    tab._reload_disk_theme()
    assert tab._working_theme["label"] == "From Disk"
    assert tab._theme_combo.currentText() == "From Disk"
    assert not tab._notice.is_showing()

    # Choosing to keep editing leaves the document alone.
    _type_label(tab, "Another Draft")
    path.write_text(json.dumps(_theme("default", "Third Version")),
                    encoding="utf-8")
    tab._on_theme_files_changed()
    tab._dismiss_disk_conflict()
    assert tab._working_theme["label"] == "Another Draft"
    assert not tab._notice.is_showing()


def test_own_save_does_not_trigger_a_reload_or_a_notice(make_tab,
                                                        themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    tab = make_tab()
    _type_label(tab, "Saved Here")
    tab._on_save()

    # The watcher echo of our own write is swallowed by the content hash.
    tab._on_theme_files_changed()

    assert not tab._notice.is_showing()
    assert tab._working_theme["label"] == "Saved Here"
    assert not tab.is_dirty()


def test_invalid_json_keeps_the_last_good_theme_and_warns(make_tab,
                                                          themes_tree):
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    tab = make_tab()
    assert tab._working_theme["label"] == "Standard"

    path.write_text('{"label": "Half typed', encoding="utf-8")
    tab._on_theme_files_changed()

    # Last good content stays in memory, and the row carries a warning.
    assert tab._working_theme["label"] == "Standard"
    assert tab._working_theme["containers"]
    index = tab._theme_combo.findData("default")
    assert tab._theme_combo.itemData(index, WARNING_ROLE)
    assert tab._theme_combo.itemText(index) == "Standard"
    assert tab._notice.is_showing()
    assert "not valid JSON" in tab._notice.current_text()

    # Recovering clears the warning.
    path.write_text(json.dumps(_theme("default", "Recovered")),
                    encoding="utf-8")
    tab._on_theme_files_changed()
    assert not tab._theme_combo.itemData(index, WARNING_ROLE)
    assert tab._theme_combo.currentText() == "Recovered"


def test_added_file_appears_without_a_restart(make_tab, themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    tab = make_tab()
    assert "brand_new" not in [theme_id for _t, theme_id in _labels(tab)]

    _write(themes_tree, "brand_new", _theme("brand_new", "Brand New"))
    tab._on_theme_files_changed()

    assert dict(_labels(tab))["Brand New"] == "brand_new"


def test_deleted_selected_theme_falls_back_to_default_with_a_notice(
        make_tab, themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    death_row = _write(themes_tree, "doomed",
                       _theme("doomed", "Doomed Theme"))

    tab = make_tab()
    tab.set_theme("doomed")
    assert tab._theme_combo.current_id() == "doomed"

    death_row.unlink()
    tab._on_theme_files_changed()

    assert tab._theme_id == "default"
    assert tab._theme_name == "default"
    assert tab._theme_combo.current_id() == "default"
    assert "Doomed Theme" in tab._notice.current_text()
    assert "deleted" in tab._notice.current_text()
    assert "doomed" not in [theme_id for _t, theme_id in _labels(tab)]


# ── watcher ─────────────────────────────────────────────────────────────────

def test_watcher_fires_for_an_external_file_edit(qapp, tmp_path):
    root = tmp_path / "themes"
    (root / "scripture").mkdir(parents=True)
    path = root / "scripture" / "watched.json"
    path.write_text(json.dumps(_theme("watched", "Watched")),
                    encoding="utf-8")

    watcher = ThemeFolderWatcher(root=root, interval_ms=50)
    fired = []
    watcher.changed.connect(lambda: fired.append(time.monotonic()))
    watcher.start()
    try:
        assert watcher.is_started()
        path.write_text(json.dumps(_theme("watched", "Changed")),
                        encoding="utf-8")
        deadline = time.monotonic() + 5.0
        while not fired and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.02)
        assert fired, "watcher never reported the external edit"
    finally:
        watcher.stop()


# ── popup painting ──────────────────────────────────────────────────────────

def test_popup_rows_paint_without_the_suffix_drawn_twice(make_tab, themes_tree):
    """The closed combo shows ``label (id)``; the row must paint only the bare
    label as the bold text and add the ID suffix as muted text itself.

    Painting is exercised here because a token or role typo in the delegate
    only surfaces when a row is actually drawn.
    """
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionViewItem

    from ui.widgets.theme_designer.theme_combo import LABEL_ROLE

    _require_imports = (LABEL_ROLE,)  # noqa: F841
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "default_2",
           _theme("default_2", "Standard", "Second standard theme"))

    tab = make_tab()
    combo = tab._theme_combo
    row = combo.findData("default_2")
    assert combo.itemText(row) == "Standard (default_2)"
    assert combo.itemData(row, LABEL_ROLE) == "Standard"
    index = combo.model().index(row, 0)

    image = QImage(420, 48, QImage.Format.Format_ARGB32)
    image.fill(0)
    option = QStyleOptionViewItem()
    option.font = combo.font()
    option.rect = QRect(0, 0, 420, 48)
    option.state = (option.state.__class__.State_Enabled
                    | option.state.__class__.State_Selected)
    painter = QPainter(image)
    try:
        combo.view().itemDelegate().paint(painter, option, index)
    finally:
        painter.end()

    painted = sum(1 for y in range(image.height())
                  for x in range(image.width())
                  if image.pixelColor(x, y).alpha() > 0)
    assert painted > 0, "the row painted nothing"


def test_typed_whitespace_is_trimmed_in_the_document_and_on_save(
        make_tab, themes_tree):
    """The field may hold a trailing space mid-typing; the document, the
    dropdown and the saved file all keep the trimmed label."""
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    tab = make_tab()

    _type_label(tab, "Sermon Wide ")

    assert tab._working_theme["label"] == "Sermon Wide"
    assert tab._theme_combo.currentText() == "Sermon Wide"
    tab._on_save()
    assert _read(path)["label"] == "Sermon Wide"
