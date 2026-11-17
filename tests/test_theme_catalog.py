"""Unit tests for the theme display catalog (ID vs label).

No Qt here: the catalog is the one in-memory store the Theme Designer's
selector reads, and these tests own its rules — fallback labels, duplicate
suffixes, ordering, live label edits, and disk sync (own writes, invalid
JSON, added and deleted files).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import core.theme_loader as theme_loader
from core.theme_catalog import (
    ThemeCatalog,
    build_entry,
    clean_description,
    prettify_id,
    resolve_label,
    sort_key,
)


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


def _write(root: Path, name: str, theme: dict, kind: str = "scripture") -> Path:
    folder = root / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(theme, indent=4), encoding="utf-8")
    return path


@pytest.fixture
def themes_tree(tmp_path, monkeypatch):
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


def _catalog(root: Path) -> ThemeCatalog:
    catalog = ThemeCatalog()
    catalog.load()
    return catalog


# ── labels ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_id,expected", [
    ("default_typewriter", "Default Typewriter"),
    ("default", "Default"),
    ("fullscreen-2", "Fullscreen 2"),
    ("myTheme", "MyTheme"),
    ("  spaced__id  ", "Spaced Id"),
    ("", "Untitled"),
])
def test_prettify_id(theme_id, expected):
    assert prettify_id(theme_id) == expected


def test_resolve_label_falls_back_when_missing_or_empty():
    assert resolve_label("Standard", "default") == "Standard"
    assert resolve_label("", "default_typewriter") == "Default Typewriter"
    assert resolve_label("   ", "reference_2") == "Reference 2"
    assert resolve_label(None, "slides") == "Slides"


def test_description_collapses_to_one_line():
    assert clean_description("line one\nline two") == "line one line two"
    assert clean_description(None) == ""
    assert clean_description(123) == ""


# ── catalog content ─────────────────────────────────────────────────────────

def test_entries_use_filename_stem_as_id_and_json_label_as_text(themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard",
                                          "Full screen display"))
    _write(themes_tree, "default_typewriter",
           _theme("default_typewriter", "Standard — Typewriter"))
    _write(themes_tree, "unlabelled", _theme("unlabelled"))

    catalog = _catalog(themes_tree)
    by_id = {entry.id: entry for entry in catalog.entries()}

    assert set(by_id) == {"default", "default_typewriter", "unlabelled"}
    assert by_id["default"].label == "Standard"
    assert by_id["default"].description == "Full screen display"
    assert by_id["unlabelled"].label == "Unlabelled"  # prettified fallback
    # The ID is the file stem, not the label.
    assert by_id["default"].path.name == "default.json"


def test_options_sort_by_label_case_insensitively(themes_tree):
    _write(themes_tree, "z_theme", _theme("z_theme", "alpha"))
    _write(themes_tree, "a_theme", _theme("a_theme", "Zulu"))
    _write(themes_tree, "m_theme", _theme("m_theme", "mike"))

    catalog = _catalog(themes_tree)
    assert [entry.label for entry in catalog.entries()] == [
        "alpha", "mike", "Zulu"]


def test_sort_order_takes_priority_over_label(themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "first", _theme("first", "Zzz First", sort_order=1))
    _write(themes_tree, "pinned", _theme("pinned", "Aaa Pinned", sort_order=-5))

    catalog = _catalog(themes_tree)
    assert [entry.id for entry in catalog.entries()] == [
        "pinned", "first", "default"]


def test_duplicate_labels_get_the_id_suffix(themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "default_2", _theme("default_2", "Standard"))
    _write(themes_tree, "unique", _theme("unique", "Unique"))

    catalog = _catalog(themes_tree)
    by_id = {entry.id: entry for entry in catalog.entries()}
    assert by_id["default"].duplicate is True
    assert by_id["default"].suffix == " (default)"
    assert by_id["default_2"].suffix == " (default_2)"
    assert by_id["unique"].duplicate is False
    assert by_id["unique"].suffix == ""


def test_duplicate_flag_clears_when_a_label_is_edited(themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    _write(themes_tree, "default_2", _theme("default_2", "Standard"))

    catalog = _catalog(themes_tree)
    assert catalog.get("default_2").duplicate

    assert catalog.set_label("default_2", "Shadowed") is True
    assert catalog.get("default_2").duplicate is False
    assert catalog.get("default").duplicate is False
    assert catalog.get("default_2").label == "Shadowed"
    assert catalog.get("default_2").id == "default_2"


def test_live_label_edit_keeps_id_and_updates_sort_position(themes_tree):
    _write(themes_tree, "alpha", _theme("alpha", "Alpha"))
    _write(themes_tree, "beta", _theme("beta", "Beta"))

    catalog = _catalog(themes_tree)
    assert [entry.id for entry in catalog.entries()] == ["alpha", "beta"]

    catalog.set_label("beta", "Aardvark")
    assert [entry.id for entry in catalog.entries()] == ["beta", "alpha"]
    assert catalog.get("beta").id == "beta"
    assert catalog.get("beta").path.stem == "beta"


def test_clearing_a_label_shows_the_fallback_without_losing_the_id(themes_tree):
    _write(themes_tree, "default_typewriter",
           _theme("default_typewriter", "Standard — Typewriter"))

    catalog = _catalog(themes_tree)
    assert catalog.set_label("default_typewriter", "") is True

    entry = catalog.get("default_typewriter")
    assert entry.id == "default_typewriter"
    assert entry.raw_label == ""
    assert entry.label == "Default Typewriter"


# ── disk sync ───────────────────────────────────────────────────────────────

def test_external_edit_is_detected_and_updates_the_store(themes_tree):
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    catalog = _catalog(themes_tree)

    path.write_text(json.dumps(_theme("default", "Sermon Wide")),
                    encoding="utf-8")
    # Even with the mtime forced back, the content hash catches the edit.
    os.utime(path, (1, 1))

    changes = catalog.sync_from_disk(theme_loader.iter_theme_files())
    assert [(c.theme_id, c.action) for c in changes] == [
        ("default", "updated")]
    assert catalog.get("default").label == "Sermon Wide"
    # The loader follows, so the rest of the app sees the same content.
    assert theme_loader.get_theme("default")["label"] == "Sermon Wide"


def test_invalid_json_keeps_the_last_good_entry(themes_tree):
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    catalog = _catalog(themes_tree)

    path.write_text('{"broken": ', encoding="utf-8")
    changes = catalog.sync_from_disk(theme_loader.iter_theme_files())

    assert [(c.theme_id, c.action) for c in changes] == [
        ("default", "invalid")]
    entry = catalog.get("default")
    assert entry.label == "Standard"     # last good version stays
    assert entry.stale is True
    assert entry.warning
    assert theme_loader.get_theme("default")["label"] == "Standard"

    # A later good save clears the warning and updates the entry.
    path.write_text(json.dumps(_theme("default", "Recovered")),
                    encoding="utf-8")
    catalog.sync_from_disk(theme_loader.iter_theme_files())
    assert catalog.get("default").stale is False
    assert catalog.get("default").label == "Recovered"


def test_added_and_deleted_files_enter_and_leave_the_store(themes_tree):
    _write(themes_tree, "default", _theme("default", "Standard"))
    catalog = _catalog(themes_tree)

    extra = _write(themes_tree, "brand_new", _theme("brand_new", "Brand New"))
    changes = catalog.sync_from_disk(theme_loader.iter_theme_files())
    assert [(c.theme_id, c.action) for c in changes] == [
        ("brand_new", "added")]
    assert catalog.get("brand_new").label == "Brand New"

    extra.unlink()
    changes = catalog.sync_from_disk(theme_loader.iter_theme_files())
    assert [(c.theme_id, c.action) for c in changes] == [
        ("brand_new", "removed")]
    assert catalog.get("brand_new") is None
    assert "brand_new" not in theme_loader.get_theme_names()


def test_own_save_is_not_reported_as_an_external_change(themes_tree):
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    catalog = _catalog(themes_tree)

    saved = _theme("default", "Saved Label")
    written = theme_loader.save_theme("default", saved)
    assert written == path
    catalog.note_written(written, saved, theme_loader.dump_theme(saved))

    # The watcher fires after our own write; the hash marker swallows it.
    assert catalog.sync_from_disk(theme_loader.iter_theme_files()) == []
    assert catalog.get("default").label == "Saved Label"


def test_a_stray_legacy_fit_key_is_not_a_meaningful_change(themes_tree):
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    catalog = _catalog(themes_tree)

    # Someone re-adds the retired canvas.fit key on disk; nothing else changed.
    stray = _theme("default", "Standard")
    stray["canvas"]["fit"] = "none"
    path.write_text(json.dumps(stray), encoding="utf-8")
    os.utime(path, (1, 1))

    assert catalog.sync_from_disk(theme_loader.iter_theme_files()) == []
    assert "fit" not in theme_loader.get_theme("default")["canvas"]


def test_reading_and_saving_a_theme_drops_the_retired_fit_key(themes_tree):
    legacy = _theme("default", "Standard")
    legacy["canvas"]["fit"] = "none"
    path = _write(themes_tree, "default", legacy)
    _catalog(themes_tree)                       # loads the tree for this test

    theme = theme_loader.get_theme("default")
    assert "fit" not in theme["canvas"]          # ignored on read

    theme_loader.save_theme("default", theme)
    assert "fit" not in json.loads(path.read_text(encoding="utf-8"))["canvas"]


def test_sort_key_puts_explicit_orders_first():
    ordered = build_entry("b", "b", Path("b.json"), "scripture",
                          _theme("b", "Bravo", sort_order=2))
    pinned = build_entry("a", "a", Path("a.json"), "scripture",
                         _theme("a", "Alpha", sort_order=1))
    plain = build_entry("c", "c", Path("c.json"), "scripture",
                        _theme("c", "Aardvark"))
    assert sorted([plain, ordered, pinned], key=sort_key) == [
        pinned, ordered, plain]


def test_build_entry_survives_non_dict_theme():
    entry = build_entry("x", "x", Path("x.json"), "scripture", {})
    assert entry.label == "X"
    assert entry.description == ""
    assert entry.sort_order is None


# ── retired keys at the disk boundary ───────────────────────────────────────

@pytest.mark.parametrize("value", [
    None, 42, "a theme name", [],
    {"containers": []}, {"canvas": None}, {"canvas": "nope"},
    {"canvas": {"width": 1920}},
])
def test_strip_obsolete_keys_survives_anything_a_file_may_hold(value):
    """A hand-edited theme can put anything at the root or under `canvas`;
    the stripping boundary must never raise on the way to the designer."""
    assert theme_loader.strip_obsolete_keys(value) == value


def test_the_mtime_reload_path_also_strips_a_retired_key(themes_tree):
    """`_check_for_changes` re-reads a file that changed on disk; that second
    read must strip the retired key too, or a stale `fit` reappears in the
    designer after any external edit."""
    path = _write(themes_tree, "default", _theme("default", "Standard"))
    _catalog(themes_tree)

    # The label is the positive marker: it proves the new bytes were read,
    # so a loader that simply skipped the reload cannot pass this test.
    stray = _theme("default", "Reloaded")
    stray["canvas"]["fit"] = "none"
    path.write_text(json.dumps(stray), encoding="utf-8")
    stamp = time.time() + 30          # past the mtime the loader recorded
    os.utime(path, (stamp, stamp))

    theme = theme_loader.get_theme("default")
    assert theme["label"] == "Reloaded", "the file was not re-read"
    assert "fit" not in theme["canvas"]
    _, resolved = theme_loader.resolve_theme("default")
    assert "fit" not in resolved["canvas"]


def test_cloning_a_legacy_theme_does_not_copy_a_retired_key(themes_tree):
    legacy = _theme("default", "Standard")
    legacy["canvas"]["fit"] = "none"
    _write(themes_tree, "default", legacy)
    _catalog(themes_tree)

    clone = theme_loader.create_theme("clone", "Clone")
    assert "fit" not in clone["canvas"]
    written = themes_tree / "scripture" / "clone.json"
    saved = json.loads(written.read_text(encoding="utf-8"))
    assert "fit" not in saved["canvas"], "the clone wrote the retired key"
