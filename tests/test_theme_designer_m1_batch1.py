"""M1 batch 1 proof: shipped-theme round-trip gate (M1-25) and offscreen
Designer smoke (M1-26).

The tab is built with a lightweight preview stub: these gates exercise the
real property/workspace/animation panels and the one tab-owned document, but
not QtWebEngine. The display-renderer tests own that path.
"""

from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

# Import WebEngine before QApplication exists; the module import is enough for
# the real preview import chain, while these gates construct a stub instead.
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

import core.theme_loader as theme_loader  # noqa: E402
from core import theme_schema as schema  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_THEMES = _ROOT / "themes"
SHIPPED = sorted(
    (kind, path.stem, path)
    for kind in ("scripture", "freeform")
    for path in (_THEMES / kind).glob("*.json")
)

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
    """A disposable copy of themes/ so Save never touches the repository."""
    root = tmp_path_factory.mktemp("themes-tree") / "themes"
    shutil.copytree(_THEMES, root)
    previous = theme_loader._THEMES_DIR
    theme_loader._THEMES_DIR = root
    theme_loader.reload_themes()
    try:
        yield root
    finally:
        theme_loader._THEMES_DIR = previous
        theme_loader.reload_themes()


@pytest.fixture
def designer(qapp, theme_tree, monkeypatch):
    """A real ThemeDesignerTab with only the QtWebEngine preview stubbed."""
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
    yield tab
    tab.close()
    tab.deleteLater()
    qapp.processEvents()


# ── leaf helpers ────────────────────────────────────────────────────────────

def _flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _flatten(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def _leaves(value):
    return dict(_flatten(value))


def _resolve(raw, kind, name):
    return schema.normalize_theme(copy.deepcopy(raw), kind=kind, name=name)


# ── M1-25 ───────────────────────────────────────────────────────────────────

def _edit_one_field_per_group(tab, raw):
    """Touch every Designer property group through real widget APIs."""
    props = tab._properties_panel
    props.set_field("canvas.background", "#123456")
    props.set_field("canvas.fit", "contain")
    props.set_field("containers.0.opacity", 0.9)
    props.set_field("containers.0.border_radius", 9)
    if isinstance(raw.get("slide"), dict):
        props.set_field("slide.show_title", True)

    containers = raw.get("containers") or []
    for index, container in enumerate(containers):
        if not isinstance(container, dict):
            continue
        border = container.get("border")
        if isinstance(border, dict) and "shared" not in border:
            key = "radius" if "radius" in border else (
                "width" if "width" in border else "")
            if key:
                props.set_field(f"containers.{index}.border.{key}", 11)
        shadow = container.get("box_shadow")
        if isinstance(shadow, dict) and "shared" not in shadow:
            key = "blur" if "blur" in shadow else (
                "x" if "x" in shadow else "")
            if key:
                props.set_field(f"containers.{index}.box_shadow.{key}", 12)
        if "backdrop_filter" in container:
            props.set_field(f"containers.{index}.backdrop_filter", "none")
        blocks = container.get("blocks") or {}
        for block_id, block in blocks.items():
            if not isinstance(block, dict):
                continue
            base = f"containers.{index}.blocks.{block_id}"
            if block_id == "body":
                props.set_field(f"{base}.gap", 11)
            elif block_id == "text":
                props.set_field(f"{base}.size", 43)
                props.set_field(f"{base}.line_height", 1.25)
            elif block_id in ("reference", "title"):
                props.set_field(f"{base}.color", "#a1b2c3")
            elif block_id == "translation":
                props.set_field(f"{base}.margin_left", 9)
            elif block_id == "verse_num":
                props.set_field(f"{base}.opacity", 0.8)

    # Split group, on the first text-bearing block that exists.
    split_done = False
    for index, container in enumerate(containers):
        if split_done or not isinstance(container, dict):
            continue
        blocks = container.get("blocks") or {}
        for block_id in schema.SPLIT_BLOCKS:
            block = blocks.get(block_id)
            if not isinstance(block, dict):
                continue
            animation = block.get("animation")
            existing = (animation.get("split")
                        if isinstance(animation, dict) else None)
            split = dict(existing) if isinstance(existing, dict) else {}
            split.update({"by": "word", "stagger_ms": 120})
            props.set_field(
                f"containers.{index}.blocks.{block_id}.animation.split",
                split)
            split_done = True
            break

    # Geometry group: the workspace field emits exactly like an operator edit.
    first_id = tab._container_ids()[0]
    tab._on_container_selected(first_id)
    tab._workspace.x_field.changed.emit(37)

    # Animation group: add a phase the theme does not use, so no authored
    # slot is replaced. If all four exist, add a timing override instead.
    panel = tab._animations_panel
    animation = (containers[0].get("animation")
                 if containers and isinstance(containers[0], dict) else None)
    animation = animation if isinstance(animation, dict) else {}
    transition = animation.get("transition")
    transition = transition if isinstance(transition, dict) else {}
    phases = {
        "entry": animation.get("entry"),
        "out": animation.get("out"),
        "transition_in": transition.get("in"),
        "transition_out": transition.get("out"),
    }
    absent = next((phase for phase, value in phases.items()
                   if value in (None, "none", "")), None)
    if absent:
        card = panel.card(absent)
        card.set_value("fade_up")
        card.changed.emit(card.value())
    else:
        panel.card("entry")._write_override("duration_ms", 777)


@pytest.mark.parametrize(
    "kind,name,path", SHIPPED,
    ids=[f"{kind}/{name}" for kind, name, path in SHIPPED])
def test_every_shipped_theme_survives_designer_edit_save_reload(
        designer, theme_tree, kind, name, path):
    raw = theme_loader.get_theme(name)
    assert raw is not None, name
    before_warnings = _resolve(raw, kind, name)[1].warnings
    source_keys = set(_leaves(raw))

    designer.set_theme(name)
    _edit_one_field_per_group(designer, raw)

    working = copy.deepcopy(designer._working_theme)
    designer._on_save()
    theme_loader.reload_themes()
    saved = theme_loader.get_theme(name)

    assert saved is not None, name
    assert (theme_tree / kind / f"{name}.json").is_file()

    lost = sorted(source_keys - set(_leaves(saved)))
    assert lost == [], f"{name} lost keys after Save: {lost}"
    assert set(_leaves(saved)) == set(_leaves(working))

    # The edits itself must have landed, not merely preserved the source.
    saved_leaves = _leaves(saved)
    assert saved_leaves["canvas.background"] == "#123456"
    assert saved_leaves["containers[0].position.x"] == 37
    assert any(key.startswith("containers[") and key.endswith(".animation.split.by")
               and value == "word" for key, value in saved_leaves.items())

    resolved, report = _resolve(saved, kind, name)
    assert not report.errors, f"{name} resolve errors: {report.errors}"
    assert len(report.warnings) <= len(before_warnings), (
        f"{name} gained warnings: {report.warnings}")
    assert resolved["schema_version"] == 2
    assert resolved["containers"], name
    assert not designer.is_dirty()


# ── M1-26 ───────────────────────────────────────────────────────────────────

def test_designer_opens_every_pane_every_block_tab_and_saves(designer, qapp):
    from ui.theme_kit import BlockTabBar

    designer.show()
    designer.set_theme("default_quiet")
    qapp.processEvents()

    # Left panel: all three property pages.
    props = designer._properties_panel
    for page in ("canvas", "container", "blocks"):
        props._pages.set_value(page, emit=True)
        qapp.processEvents()
        assert props._page() == page
        assert props._layout.count() >= 2

    # Every block tab the theme's kind offers.
    allowed = list(schema.BLOCK_IDS["scripture"])
    bar = props.findChild(BlockTabBar)
    assert bar is not None
    for block in allowed:
        bar.set_current(block, emit=True)
        qapp.processEvents()
        assert props._block == block

    # Centre stack: Preview and Editor (the real workspace).
    for view, index in (("multi", 0), ("editor", 1)):
        designer._switch_center_view(view)
        qapp.processEvents()
        assert designer._center_stack.currentIndex() == index

    # Right panel: Animations and JSON.
    for tab, index in (("animations", 0), ("json", 1)):
        designer._switch_right_tab(tab)
        qapp.processEvents()
        assert designer._right_stack.currentIndex() == index

    # Editor view actually mounts the workspace; canvas becomes visible.
    designer._switch_center_view("editor")
    qapp.processEvents()
    assert designer._workspace.isVisible()

    designer._on_save()
    theme_loader.reload_themes()
    saved = theme_loader.get_theme("default_quiet")
    assert saved is not None
    assert set(_leaves(saved)) == set(_leaves(designer._working_theme))
    assert not designer.is_dirty()
    assert designer.can_unload()[0] is True


def test_panels_share_the_tab_owned_document(designer):
    """The tab owns one document; panels request edits instead of merging."""
    document = designer._document
    assert designer._properties_panel._document is document
    assert designer._animations_panel._document is document
    assert designer._workspace._document is document

    designer._properties_panel.set_field("canvas.background", "#123456")
    designer._animations_panel._write_slot("entry", "fade_up")

    working = designer._working_theme
    assert working["canvas"]["background"] == "#123456"
    assert working["containers"][0]["animation"]["entry"] == "fade_up"
    assert document.snapshot() == working
