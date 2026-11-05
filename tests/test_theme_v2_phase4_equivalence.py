"""
tests/test_theme_v2_phase4_equivalence.py

Phase 4 gate tests for docs/theme_schema_v2.md:
- Equivalence test: resolved v1-migrated dict deep-equals the resolved v2 file
  for every shipped theme (freeform/slides + 5 scripture themes).
- Animation equivalence: verify that a migrated v1 dict with
  `display_enter`/`between_slides`/`display_exit` produces matching phase
  selection, timing, and keyframes in v2.
- Golden comparison: verify that resolved v2 container metrics match the
  Phase 2 golden fixture measurements (rect, styles).
"""

import json
from pathlib import Path
import pytest

from core.theme_migrate import migrate_v1_to_v2
from core.theme_schema import normalize_theme, BUILTIN_ANIMATIONS
from core.theme_loader import resolve_theme, get_theme

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "tests" / "fixtures" / "v1_shipped_themes.json"
GOLDEN_PATH = ROOT / "tests" / "golden_fixtures_phase2.json"

SHIPPED_THEMES = [
    ("slides", "freeform"),
    ("default", "scripture"),
    ("fullscreen", "scripture"),
    ("fullscreen_2", "scripture"),
    ("reference", "scripture"),
    ("reference_2", "scripture"),
]


@pytest.fixture(scope="module")
def v1_fixtures():
    assert FIXTURES_PATH.exists(), f"Missing {FIXTURES_PATH}"
    return json.loads(FIXTURES_PATH.read_text("utf-8"))


@pytest.fixture(scope="module")
def golden_fixtures():
    assert GOLDEN_PATH.exists(), f"Missing {GOLDEN_PATH}"
    return json.loads(GOLDEN_PATH.read_text("utf-8"))


# ─── 1. Deep Equality of Resolved v1 Migrated vs Resolved v2 File ───────────


@pytest.mark.parametrize("name,kind", SHIPPED_THEMES)
def test_shipped_themes_v1_migrated_deep_equals_v2_resolved(name, kind, v1_fixtures):
    """The resolved v1-migrated dict must deep-equal the resolved v2 file on disk."""
    v1_raw = v1_fixtures[name]
    v1_migrated = migrate_v1_to_v2(v1_raw, kind=kind)
    resolved_v1, report_v1 = normalize_theme(v1_migrated, kind=kind, name=name)
    assert report_v1.warnings == [], f"v1 migration had warnings: {report_v1.warnings}"

    # Resolve from disk via standard loader
    res_name, resolved_v2 = resolve_theme(name)
    assert res_name == name
    assert resolved_v2["schema_version"] == 2

    # Verify deep equality of all keys
    assert resolved_v1["kind"] == resolved_v2["kind"]
    assert resolved_v1["canvas"] == resolved_v2["canvas"]
    assert len(resolved_v1["containers"]) == len(resolved_v2["containers"])

    c1 = resolved_v1["containers"][0]
    c2 = resolved_v2["containers"][0]
    assert c1["id"] == c2["id"]
    assert c1["position"] == c2["position"]
    assert c1["width"] == c2["width"]
    assert c1["height"] == c2["height"]
    assert c1["background"] == c2["background"]
    assert c1["border"] == c2["border"]
    assert c1["border_radius"] == c2["border_radius"]
    assert c1["box_shadow"] == c2["box_shadow"]
    assert c1["blocks"] == c2["blocks"]

    assert resolved_v1 == resolved_v2, f"Discrepancy in resolved dict for {name}"


# ─── 2. Animation Equivalence ───────────────────────────────────────────────


def test_migrated_v1_animation_timing_and_phases_match_v2():
    """Verify that a migrated v1 animations dict maps onto the v2 container
    structure with exact phase timings and preset keyframes."""
    v1_doc = {
        "containers": {"main": {"x": 0, "y": 0, "text": {}}},
        "animations": {
            "display_enter": {"type": "fade_up", "duration_ms": 450},
            "between_slides": {
                "in_type": "scale_up",
                "out_type": "fade_down",
                "duration_ms": 350,
            },
            "display_exit": {"type": "fade_out", "duration_ms": 250},
        },
    }
    migrated = migrate_v1_to_v2(v1_doc, kind="scripture")
    resolved, report = normalize_theme(migrated, kind="scripture", name="anim_test")
    assert report.warnings == []

    anim = resolved["containers"][0]["animation"]
    registry = resolved["animations"]

    # 1. Entry phase
    assert anim["entry"]["use"] == "fade_up"
    assert anim["entry"]["duration_ms"] == 450
    assert "fade_up" in registry
    assert registry["fade_up"]["keyframes"] == BUILTIN_ANIMATIONS["fade_up"]["keyframes"]

    # 2. Transition phase
    trans = anim["transition"]
    assert trans["in"]["use"] == "scale_up"
    assert trans["in"]["duration_ms"] == 350
    assert "scale_up" in registry
    assert registry["scale_up"]["keyframes"] == BUILTIN_ANIMATIONS["scale_up"]["keyframes"]

    # 3. Exit phase
    assert anim["out"]["use"] == "fade_out"
    assert anim["out"]["duration_ms"] == 250
    assert "fade_out" in registry
    assert registry["fade_out"]["keyframes"] == BUILTIN_ANIMATIONS["fade_out"]["keyframes"]


# ─── 3. Golden Fixture Container Metrics ─────────────────────────────────────


@pytest.mark.parametrize("name,kind", SHIPPED_THEMES)
def test_golden_fixture_container_metrics_match_resolved_v2(name, kind, golden_fixtures):
    """Verify that the resolved v2 container metrics match the golden fixture bounding box."""
    assert name in golden_fixtures, f"Missing {name} in golden fixtures"
    golden_entry = golden_fixtures[name]["short"]["container"]
    golden_rect = golden_entry["rect"]
    golden_styles = golden_entry["styles"]

    _, resolved = resolve_theme(name)
    c = resolved["containers"][0]

    # Geometric position matches to the pixel
    assert c["position"]["anchor"] == "top_left"
    assert float(c["position"]["x"]) == float(golden_rect["left"])
    assert float(c["position"]["y"]) == float(golden_rect["top"])
    assert float(c["width"]) == float(golden_rect["width"])
    assert float(c["height"]) == float(golden_rect["height"])

    # Basic CSS properties match
    assert golden_styles["position"] == "absolute"
    assert golden_styles["opacity"] == "1"
    assert golden_styles["display"] == "flex"
