"""
tests/test_theme_v2_shared.py

Shared-definition gate for docs/theme_schema_v2.md §5:
- `themes/_shared/{borders,shadows,palettes,animations}.json` load through the
  same validators as inline values, one family per file, mtime-cached;
- a malformed file or entry degrades to empty/dropped without raising;
- palette entries may chain `@name` references (depth 4 + cycle detection);
- `{ "shared": name }` looks in the field's own family first, then the other
  family only when unambiguous;
- `@name` expands in colors, structured border/shadow colors, paints, and
  `text_outline`, never inside shadow/gradient strings;
- theme-local animations shadow shared ones, which shadow the built-in
  registry, and `_shared` never appears as a theme or a theme kind.

Every test writes its own shared directory and monkeypatches `SHARED_DIR`, so
nothing here depends on the real `themes/_shared/` existing.
"""

import json
import os
from pathlib import Path

import pytest

from core import theme_shared
from core.theme_schema import ThemeReport, normalize_theme
from core.theme_shared import clear_cache, load_family, resolve_shared


# ─── Fixtures ───────────────────────────────────────────────────────────────

DEFAULT_FAMILIES = {
    "palettes": {
        "schema_version": 2,
        "colors": {
            "gold": "#D4AF37",
            "ink": "rgba(0,0,0,0.6)",
            "alias": "@gold",
            "white": "#ffffff",
        },
    },
    "borders": {
        "schema_version": 2,
        "borders": {
            "gold_frame": {
                "width": 2, "style": "solid", "color": "@gold", "radius": 12,
                "sides": {"top": {"width": 4}},
            },
            "hairline": {
                "width": 1, "style": "solid",
                "color": "rgba(255,255,255,0.18)",
            },
        },
    },
    "shadows": {
        "schema_version": 2,
        "shadows": {
            "soft": {"x": 0, "y": 24, "blur": 48, "spread": -12,
                     "color": "rgba(0,0,0,0.55)"},
            "ring": {"x": 0, "y": 0, "blur": 0, "spread": 1,
                     "color": "rgba(255,255,255,0.08)", "inset": True},
        },
    },
    "animations": {
        "schema_version": 2,
        "animations": {
            "verse_rise": {
                "type": "custom", "label": "Verse rise", "duration_ms": 700,
                "easing": "ease-out",
                "keyframes": [
                    {"at": 0, "opacity": 0, "translate_y": 36},
                    {"at": 70, "opacity": 0.85, "translate_y": 6, "blur": 0},
                    {"at": 100, "opacity": "base", "translate_y": 0, "blur": 0},
                ],
            },
            "lyric_typewriter": {
                "type": "typewriter", "label": "Lyric typewriter",
                "duration_ms": 1400, "easing": "linear", "reveal": "char",
                "cursor": {"char": "\u258c", "color": "@gold",
                           "blink_ms": 500, "hide_after_ms": 600},
            },
        },
    },
}


class SharedDir:
    """Small writer for a fake `themes/_shared/` directory."""

    def __init__(self, root: Path):
        self.root = root

    def write(self, family: str, payload: dict, *, mtime: float = None) -> Path:
        path = self.root / f"{family}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def write_text(self, family: str, text: str, *,
                   mtime: float = None) -> Path:
        path = self.root / f"{family}.json"
        path.write_text(text, encoding="utf-8")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def remove(self, family: str) -> None:
        (self.root / f"{family}.json").unlink()


@pytest.fixture
def shared(tmp_path, monkeypatch):
    root = tmp_path / "themes" / "_shared"
    root.mkdir(parents=True)
    for family, payload in DEFAULT_FAMILIES.items():
        (root / f"{family}.json").write_text(json.dumps(payload, indent=2),
                                             encoding="utf-8")
    monkeypatch.setattr(theme_shared, "SHARED_DIR", root)
    clear_cache()
    try:
        yield SharedDir(root)
    finally:
        clear_cache()


def _joined(report: ThemeReport) -> str:
    return "\n".join(report.warnings)


def _resolve(raw, kind="scripture", name="probe"):
    return normalize_theme(raw, kind=kind, name=name)


# ─── Loading ────────────────────────────────────────────────────────────────


def test_missing_shared_directory_yields_empty_families(tmp_path, monkeypatch):
    empty = tmp_path / "nowhere"
    empty.mkdir()
    monkeypatch.setattr(theme_shared, "SHARED_DIR", empty)
    clear_cache()
    report = ThemeReport()
    for family in ("borders", "shadows", "palettes", "animations"):
        assert load_family(family, report=report) == {}
    # A missing support directory is normal, not a theme error.
    assert report.warnings == []
    clear_cache()


def test_each_family_reads_its_documented_key(shared):
    assert load_family("palettes")["gold"] == "#D4AF37"
    assert load_family("borders")["hairline"]["width"] == 1
    assert load_family("shadows")["soft"]["blur"] == 48
    assert load_family("animations")["verse_rise"]["duration_ms"] == 700


def test_palettes_use_the_colors_key_not_the_family_name(tmp_path, monkeypatch):
    root = tmp_path / "shared"
    root.mkdir()
    monkeypatch.setattr(theme_shared, "SHARED_DIR", root)
    clear_cache()
    (root / "palettes.json").write_text(json.dumps({
        "schema_version": 2,
        "palettes": {"gold": "#D4AF37"},      # wrong key: ignored
    }), encoding="utf-8")
    assert load_family("palettes") == {}
    (root / "palettes.json").write_text(json.dumps({
        "schema_version": 2,
        "colors": {"gold": "#D4AF37"},
    }), encoding="utf-8")
    clear_cache()
    assert load_family("palettes") == {"gold": "#D4AF37"}
    clear_cache()


def test_unknown_family_is_empty(shared):
    assert load_family("easing") == {}


def test_malformed_json_is_treated_as_empty(shared):
    shared.write_text("borders", "{ not json")
    assert load_family("borders") == {}


def test_non_object_root_is_treated_as_empty(shared):
    shared.write_text("shadows", "[1, 2, 3]")
    assert load_family("shadows") == {}


def test_future_shared_schema_version_is_ignored_with_a_warning(shared):
    shared.write("palettes", {"schema_version": 9,
                              "colors": {"gold": "#D4AF37"}})
    report = ThemeReport()
    assert load_family("palettes", report=report) == {}
    assert "unsupported shared schema version" in _joined(report)


def test_string_schema_version_is_accepted(shared):
    shared.write("palettes", {"schema_version": "2",
                              "colors": {"gold": "#D4AF37"}})
    assert load_family("palettes")["gold"] == "#D4AF37"


def test_entries_must_be_an_object(shared):
    shared.write("borders", {"schema_version": 2, "borders": ["nope"]})
    report = ThemeReport()
    assert load_family("borders", report=report) == {}
    assert "shared entries must be an object" in _joined(report)


def test_an_absent_entries_key_is_silent(shared):
    shared.write("borders", {"schema_version": 2})
    report = ThemeReport()
    assert load_family("borders", report=report) == {}
    assert report.warnings == []


@pytest.mark.parametrize("bad_name", [
    "has space",
    "1leading",
    "a" * 65,
    "punctuation!",
])
def test_invalid_entry_names_are_dropped(shared, bad_name):
    shared.write("palettes", {"schema_version": 2,
                              "colors": {bad_name: "#ffffff"}})
    report = ThemeReport()
    assert load_family("palettes", report=report) == {}
    assert "invalid shared name" in _joined(report)


def test_invalid_palette_colors_are_dropped_and_valid_ones_kept(shared):
    shared.write("palettes", {"schema_version": 2, "colors": {
        "good": "#D4AF37",
        "bad": "url(https://evil.example/x)",
        "worse": "not a color",
    }})
    report = ThemeReport()
    assert load_family("palettes", report=report) == {"good": "#D4AF37"}
    assert "invalid shared color" in _joined(report)


def test_invalid_border_entry_is_dropped(shared):
    shared.write("borders", {"schema_version": 2, "borders": {
        "ok": {"width": 2, "style": "solid", "color": "#ffffff"},
        "bad": "2px solid url(x)",
    }})
    report = ThemeReport()
    loaded = load_family("borders", report=report)
    assert set(loaded) == {"ok"}
    assert "invalid" in _joined(report)


def test_border_entry_cannot_reference_another_shared_entry(shared):
    shared.write("borders", {"schema_version": 2, "borders": {
        "a": {"width": 1, "style": "solid", "color": "#ffffff"},
        "b": {"shared": "a"},
    }})
    report = ThemeReport()
    assert set(load_family("borders", report=report)) == {"a"}
    assert "shared border cannot reference another" in _joined(report)


def test_shadow_entry_cannot_reference_another_shared_entry(shared):
    shared.write("shadows", {"schema_version": 2, "shadows": {
        "s": {"x": 0, "y": 4, "blur": 8, "color": "#000000"},
        "t": {"shared": "s"},
    }})
    report = ThemeReport()
    assert set(load_family("shadows", report=report)) == {"s"}
    assert "shared shadow cannot reference another" in _joined(report)


def test_invalid_animation_entries_are_dropped(shared):
    shared.write("animations", {"schema_version": 2, "animations": {
        "ok": {"type": "fade_in", "duration_ms": 300},
        "bad_type": {"type": "explode", "duration_ms": 300},
        "not_object": "fade_in",
    }})
    report = ThemeReport()
    loaded = load_family("animations", report=report)
    assert set(loaded) == {"ok"}
    joined = _joined(report)
    assert "unknown animation type" in joined
    assert "not an object" in joined


def test_animation_missing_duration_warns_and_defaults_to_600(shared):
    shared.write("animations", {"schema_version": 2, "animations": {
        "pop": {"type": "fade_in"},
    }})
    report = ThemeReport()
    loaded = load_family("animations", report=report)
    assert loaded["pop"]["duration_ms"] == 600
    assert "duration is required" in _joined(report)


def test_preset_animation_with_keyframes_is_dropped(shared):
    # §4.9.4: only type=custom accepts keyframes; a preset carrying them is a
    # mistake and must fall back per phase rather than silently ignore them.
    shared.write("animations", {"schema_version": 2, "animations": {
        "preset_with_frames": {
            "type": "fade_in", "duration_ms": 300,
            "keyframes": [{"at": 0, "scale": 0.5}, {"at": 100, "scale": 1}],
        },
    }})
    report = ThemeReport()
    assert load_family("animations", report=report) == {}
    assert "only type=custom accepts keyframes" in _joined(report)


def test_typewriter_entry_keeps_cursor_defaults(shared):
    shared.write("animations", {"schema_version": 2, "animations": {
        "ty": {"type": "typewriter", "duration_ms": 800},
    }})
    definition = load_family("animations")["ty"]
    assert definition["easing"] == "linear"
    assert definition["reveal"] == "char"
    assert definition["cursor"] == {
        "char": "\u258c", "color": "currentColor",
        "blink_ms": 500, "hide_after_ms": 600,
    }


# ─── Caching ────────────────────────────────────────────────────────────────


def test_cache_returns_the_same_object_until_the_mtime_changes(shared):
    first = load_family("palettes")
    second = load_family("palettes")
    assert first is second

    shared.write("palettes", {"schema_version": 2,
                              "colors": {"gold": "#222222"}},
                 mtime=os.path.getmtime(shared.root / "palettes.json") + 30)
    third = load_family("palettes")
    assert third is not first
    assert third["gold"] == "#222222"


def test_rewriting_a_file_invalidates_the_cache(shared):
    assert load_family("borders")["hairline"]["width"] == 1
    shared.write("borders", {"schema_version": 2, "borders": {
        "hairline": {"width": 5, "style": "dotted", "color": "#ffffff"},
    }}, mtime=os.path.getmtime(shared.root / "borders.json") + 30)
    assert load_family("borders")["hairline"]["width"] == 5


def test_editing_the_palette_invalidates_dependent_families(shared):
    # Border entries are palette-expanded before caching, so a palette edit
    # must invalidate them even when borders.json itself did not change.
    assert load_family("borders")["gold_frame"]["color"] == "#D4AF37"
    shared.write("palettes", {"schema_version": 2,
                              "colors": {"gold": "#00FF00"}},
                 mtime=os.path.getmtime(shared.root / "palettes.json") + 30)
    assert load_family("borders")["gold_frame"]["color"] == "#00FF00"


def test_cache_is_scoped_to_the_directory(tmp_path, shared):
    other = tmp_path / "other_shared"
    other.mkdir()
    stamp = os.path.getmtime(shared.root / "palettes.json")
    payload = {"schema_version": 2, "colors": {"gold": "#123456"}}
    (other / "palettes.json").write_text(json.dumps(payload), encoding="utf-8")
    os.utime(other / "palettes.json", (stamp, stamp))

    assert load_family("palettes")["gold"] == "#D4AF37"
    assert load_family("palettes", base_dir=other)["gold"] == "#123456"
    # ... and the first directory's cache entry is untouched by the second.
    assert load_family("palettes")["gold"] == "#D4AF37"


def test_deleting_a_file_invalidates_the_cache(shared):
    assert load_family("shadows")
    shared.remove("shadows")
    assert load_family("shadows") == {}


# ─── Reference resolution ───────────────────────────────────────────────────


def test_own_family_border_reference_resolves(shared):
    report = ThemeReport()
    theme = {"containers": [{"border": {"shared": "gold_frame"}}]}
    resolve_shared(theme, report=report)
    border = theme["containers"][0]["border"]
    assert border["width"] == 2
    assert border["color"] == "#D4AF37"       # @gold already expanded
    assert border["sides"] == {"top": {"width": 4}}
    assert report.warnings == []


def test_own_family_shadow_reference_resolves(shared):
    report = ThemeReport()
    theme = {"containers": [{"box_shadow": {"shared": "ring"}}]}
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["box_shadow"] == {
        "x": 0, "y": 0, "blur": 0, "spread": 1,
        "color": "rgba(255,255,255,0.08)", "inset": True,
    }
    assert report.warnings == []


def test_cross_family_lookup_warns_and_resolves(shared):
    report = ThemeReport()
    # `soft` lives in shadows.json; looking it up from `border` is allowed
    # because the name is unambiguous, but it must be logged.
    theme = {"containers": [{"border": {"shared": "soft"}}]}
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["border"]["blur"] == 48
    assert "shared name found in another family" in _joined(report)


def test_unknown_shared_name_removes_the_field_and_warns(shared):
    report = ThemeReport()
    theme = {"containers": [{"border": {"shared": "nope"}}]}
    resolve_shared(theme, report=report)
    assert "border" not in theme["containers"][0]
    assert "unknown shared border name" in _joined(report)


def test_invalid_shared_reference_object_warns(shared):
    report = ThemeReport()
    theme = {"containers": [{"box_shadow": {"shared": 42}}]}
    resolve_shared(theme, report=report)
    assert "box_shadow" not in theme["containers"][0]
    assert "invalid shared reference" in _joined(report)


def test_at_colors_expand_on_paints_and_block_colors(shared):
    report = ThemeReport()
    theme = {
        "canvas": {"background": "@alias"},
        "containers": [{
            "background": "@gold",
            "blocks": {"text": {"color": "@white"}},
        }],
    }
    resolve_shared(theme, report=report)
    assert theme["canvas"]["background"] == "#D4AF37"
    assert theme["containers"][0]["background"] == "#D4AF37"
    assert theme["containers"][0]["blocks"]["text"]["color"] == "#ffffff"


def test_at_colors_expand_inside_a_structured_border(shared):
    report = ThemeReport()
    theme = {"containers": [{"border": {
        "width": 1, "style": "solid", "color": "@gold",
    }}]}
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["border"]["color"] == "#D4AF37"
    assert report.warnings == []


def test_at_colors_expand_in_a_text_outline(shared):
    report = ThemeReport()
    theme = {"containers": [{"blocks": {"text": {
        "text_outline": "2px @gold",
    }}}]}
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["blocks"]["text"]["text_outline"] \
        == "2px #D4AF37"


def test_at_colors_are_not_expanded_inside_shadows(shared):
    # §5.6: `@name` is not expanded inside shadow strings.
    theme = {"containers": [{"box_shadow": "0 2px 8px @gold"}]}
    resolve_shared(theme, report=ThemeReport())
    assert theme["containers"][0]["box_shadow"] == "0 2px 8px @gold"


def test_palette_references_are_recursive(shared):
    shared.write("palettes", {"schema_version": 2, "colors": {
        "a": "@b", "b": "@c", "c": "#123456",
    }}, mtime=os.path.getmtime(shared.root / "palettes.json") + 30)
    theme = {"containers": [{"background": "@a"}]}
    resolve_shared(theme, report=ThemeReport())
    assert theme["containers"][0]["background"] == "#123456"


def test_palette_chains_resolve_up_to_the_depth_limit(shared):
    # Five lookups deep is fine; the sixth is rejected.
    colors = {f"n{i}": f"@n{i + 1}" for i in range(4)}
    colors["n4"] = "#abcdef"
    shared.write("palettes", {"schema_version": 2, "colors": colors},
                 mtime=os.path.getmtime(shared.root / "palettes.json") + 30)
    theme = {"containers": [{"background": "@n0"}]}
    report = ThemeReport()
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["background"] == "#abcdef"
    assert "nested too deep" not in _joined(report)


def test_a_palette_chain_beyond_the_depth_limit_is_rejected(shared):
    colors = {f"n{i}": f"@n{i + 1}" for i in range(5)}
    colors["n5"] = "#abcdef"
    shared.write("palettes", {"schema_version": 2, "colors": colors},
                 mtime=os.path.getmtime(shared.root / "palettes.json") + 30)
    theme = {"containers": [{"background": "@n0"}]}
    report = ThemeReport()
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["background"] == "@n0"
    assert "nested too deep" in _joined(report)


def test_a_palette_cycle_is_reported(shared):
    shared.write("palettes", {"schema_version": 2, "colors": {
        "a": "@b", "b": "@a", "ok": "#ffffff",
    }}, mtime=os.path.getmtime(shared.root / "palettes.json") + 30)
    theme = {"containers": [{"background": "@a"}]}
    report = ThemeReport()
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["background"] == "@a"
    assert "shared color cycle" in _joined(report)


def test_an_unknown_palette_name_warns_and_keeps_the_literal(shared):
    theme = {"containers": [{"background": "@missing"}]}
    report = ThemeReport()
    resolve_shared(theme, report=report)
    assert theme["containers"][0]["background"] == "@missing"
    assert "unknown shared color" in _joined(report)


def test_shared_animations_expand_palette_colors_without_double_expanding(shared):
    first = load_family("animations")
    assert first["lyric_typewriter"]["cursor"]["color"] == "#D4AF37"

    theme = {"containers": [{"animation": {"entry": "lyric_typewriter"}}]}
    shared_defs = resolve_shared(theme, report=ThemeReport())
    assert shared_defs["lyric_typewriter"]["cursor"]["color"] == "#D4AF37"

    # The cached family is the canonical (expanded) form; resolving must not
    # mutate it or expand an already-expanded value twice.
    again = load_family("animations")
    assert again is first
    assert again["lyric_typewriter"]["cursor"]["color"] == "#D4AF37"


def test_resolve_shared_returns_an_empty_library_when_no_files_exist(
        tmp_path, monkeypatch):
    empty = tmp_path / "nowhere"
    empty.mkdir()
    monkeypatch.setattr(theme_shared, "SHARED_DIR", empty)
    clear_cache()
    theme = {"containers": [{"border": "none"}]}
    assert resolve_shared(theme, report=ThemeReport()) == {}
    clear_cache()


# ─── End-to-end through normalize_theme ─────────────────────────────────────


def test_theme_using_a_shared_border_and_shadow_resolves_cleanly(shared):
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "border": {"shared": "gold_frame"},
            "box_shadow": {"shared": "soft"},
        }],
    })
    container = resolved["containers"][0]
    assert container["border"]["color"] == "#D4AF37"
    assert container["border"]["width"] == 2
    assert container["box_shadow"]["blur"] == 48
    assert report.warnings == []


def test_theme_using_a_shared_animation_embeds_its_definition(shared):
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "animation": {"entry": "verse_rise"},
            "blocks": {"text": {"animation": {"entry": "lyric_typewriter"}}},
        }],
    })
    assert report.warnings == []
    assert resolved["containers"][0]["animation"]["entry"] == {"use": "verse_rise"}
    verse_rise = resolved["animations"]["verse_rise"]
    assert verse_rise["type"] == "custom"
    assert verse_rise["duration_ms"] == 700
    assert [frame["at"] for frame in verse_rise["keyframes"]] == [0, 70, 100]
    # Named definitions the theme never references stay out of the payload.
    assert "fade_in" not in resolved["animations"]
    typewriter = resolved["animations"]["lyric_typewriter"]
    assert typewriter["type"] == "typewriter"
    assert typewriter["cursor"]["color"] == "#D4AF37"


def test_unknown_shared_border_falls_back_to_none(shared):
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "border": {"shared": "missing"}}],
    })
    assert resolved["containers"][0]["border"] == "none"
    assert len(report.warnings) == 1
    assert "unknown shared border name" in report.warnings[0]


def test_a_malformed_shared_file_does_not_break_the_theme(shared):
    shared.write_text("borders", "{{{")
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "border": {"shared": "gold_frame"},
            "blocks": {"text": {}},
        }],
    })
    assert [c["id"] for c in resolved["containers"]] == ["main"]
    assert resolved["containers"][0]["border"] == "none"
    assert "unknown shared border name" in _joined(report)


def test_a_dropped_shared_animation_falls_back_per_phase(shared):
    shared.write("animations", {"schema_version": 2, "animations": {
        "verse_rise": {"type": "nope", "duration_ms": 400},
    }}, mtime=os.path.getmtime(shared.root / "animations.json") + 30)
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "animation": {"entry": "verse_rise", "out": "verse_rise"},
        }],
    })
    animation = resolved["containers"][0]["animation"]
    assert animation["entry"] == {"use": "fade_in"}
    assert animation["out"] == {"use": "fade_out"}
    assert "unknown animation name" in _joined(report)


def test_theme_local_animations_shadow_shared_and_builtin(shared):
    resolved, report = _resolve({
        "schema_version": 2,
        "animations": {
            "verse_rise": {"type": "fade_in", "duration_ms": 200},
            "fade_in": {"type": "slide_up", "duration_ms": 250},
        },
        "containers": [{
            "id": "main",
            "animation": {"entry": "verse_rise",
                          "transition": {"in": "fade_in"}},
        }],
    })
    assert report.warnings == []
    definitions = resolved["animations"]
    assert definitions["verse_rise"]["type"] == "fade_in"
    assert definitions["verse_rise"]["duration_ms"] == 200
    assert definitions["fade_in"]["type"] == "slide_up"


def test_a_shared_animation_shadows_a_builtin(shared):
    shared.write("animations", {"schema_version": 2, "animations": {
        "fade_in": {"type": "scale_up", "duration_ms": 320},
    }}, mtime=os.path.getmtime(shared.root / "animations.json") + 30)
    resolved, report = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main", "animation": {"entry": "fade_in"}}],
    })
    assert report.warnings == []
    assert resolved["animations"]["fade_in"]["type"] == "scale_up"
    assert resolved["animations"]["fade_in"]["duration_ms"] == 320


def test_an_unreferenced_builtin_is_not_shipped(shared):
    resolved, _ = _resolve({
        "schema_version": 2,
        "containers": [{"id": "main"}],
    })
    assert resolved["animations"] == {}


def test_resolving_twice_is_deterministic(shared):
    raw = {
        "schema_version": 2,
        "canvas": {"background": "@alias"},
        "containers": [{
            "id": "main",
            "border": {"shared": "gold_frame"},
            "box_shadow": {"shared": "soft"},
            "animation": {"entry": "verse_rise", "out": "fade_out"},
            "blocks": {"text": {"color": "@gold"}},
        }],
    }
    first, _ = _resolve(raw)
    second, _ = _resolve(raw)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_shared_palette_values_survive_a_raw_load_edit_save_cycle(shared):
    # The designer edits the raw theme; `{ "shared": ... }` and `@name` must
    # not be baked into the file by loading it.
    from core import theme_loader

    raw = {
        "name": "probe",
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "border": {"shared": "gold_frame"},
            "blocks": {"text": {"color": "@gold"}},
        }],
    }
    resolved, _ = _resolve(raw)
    assert resolved["containers"][0]["border"]["color"] == "#D4AF37"
    assert raw["containers"][0]["border"] == {"shared": "gold_frame"}
    assert raw["containers"][0]["blocks"]["text"]["color"] == "@gold"
    assert theme_loader  # imported for parity with the designer path


# ─── `_shared` is invisible to the theme lister ─────────────────────────────


@pytest.fixture
def themes_root(tmp_path, monkeypatch):
    from core import theme_loader

    root = tmp_path / "themes"
    (root / "scripture").mkdir(parents=True)
    (root / "freeform").mkdir()
    (root / "_shared" / "nested").mkdir(parents=True)
    (root / "scripture" / "_drafts").mkdir()

    (root / "_shared" / "borders.json").write_text(
        json.dumps({"borders": {}}), encoding="utf-8")
    (root / "_shared" / "nested" / "animations.json").write_text(
        json.dumps({"animations": {}}), encoding="utf-8")
    (root / "_hidden.json").write_text(json.dumps({"name": "_hidden"}),
                                       encoding="utf-8")
    (root / "scripture" / "ok.json").write_text(
        json.dumps({"name": "ok", "containers": {}}), encoding="utf-8")
    (root / "scripture" / "_drafts" / "draft.json").write_text(
        json.dumps({"name": "draft"}), encoding="utf-8")
    (root / "freeform" / "slides.json").write_text(
        json.dumps({"name": "slides", "containers": {}}), encoding="utf-8")

    monkeypatch.setattr(theme_loader, "_THEMES_DIR", root)
    # Never touch the operator's real settings database from a unit test.
    monkeypatch.setattr("core.database.get_setting", lambda *a, **k: None)
    theme_loader._cache.clear()
    theme_loader._paths.clear()
    theme_loader._file_mtimes.clear()
    theme_loader._resolved_cache.clear()
    theme_loader._loaded = False
    try:
        yield root
    finally:
        theme_loader._cache.clear()
        theme_loader._paths.clear()
        theme_loader._file_mtimes.clear()
        theme_loader._resolved_cache.clear()
        theme_loader._loaded = False


def test_shared_files_are_not_themes(themes_root):
    from core import theme_loader

    assert set(theme_loader.get_theme_names()) == {"ok", "slides"}
    assert theme_loader.get_theme("_shared") is None
    assert theme_loader.get_theme("borders") is None
    assert theme_loader.get_theme("_hidden") is None
    assert theme_loader.get_theme("draft") is None


def test_shared_is_not_a_theme_kind(themes_root):
    from core import theme_loader

    assert theme_loader.get_themes_by_kind("_shared") == {}
    assert theme_loader.get_theme_kind("ok") == "scripture"
    assert theme_loader.get_theme_kind("slides") == "freeform"


def test_underscore_segments_are_skipped_at_any_depth(themes_root):
    from core import theme_loader

    assert theme_loader._is_theme_path(themes_root / "_shared" / "borders.json") is False
    assert theme_loader._is_theme_path(
        themes_root / "_shared" / "nested" / "animations.json") is False
    assert theme_loader._is_theme_path(
        themes_root / "scripture" / "_drafts" / "draft.json") is False
    assert theme_loader._is_theme_path(
        themes_root / "scripture" / "ok.json") is True
