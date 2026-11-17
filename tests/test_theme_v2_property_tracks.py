"""Schema coverage for `animation.properties` tracks.

Property tracks are additive: a theme that has none resolves exactly as
before, and unknown track ids survive validation so a newer theme still
round-trips through an older build.
"""

from __future__ import annotations

import copy

from core import theme_schema as schema


def _theme(properties):
    return {
        "schema_version": 2,
        "name": "property_probe",
        "kind": "scripture",
        "canvas": {"width": 1920, "height": 1080},
        "containers": [{
            "id": "main",
            "visible": True,
            "width": 640,
            "height": 360,
            "position": {"anchor": "center"},
            "border": {"width": 2, "style": "solid", "color": "#ff00ff"},
            "animation": {"properties": copy.deepcopy(properties)},
            "blocks": {"text": {"visible": True, "size": 48}},
        }],
    }


def _resolve(properties):
    resolved, report = schema.normalize_theme(
        _theme(properties), kind="scripture", name="property_probe")
    anim = resolved["containers"][0].get("animation", {})
    return (anim.get("properties", {}), report)


def test_border_draw_survives_with_defaults():
    tracks, _report = _resolve({
        "border.draw": {"phase": "entry", "direction": "clockwise"},
    })

    track = tracks["border.draw"]
    assert track["phase"] == "entry"
    assert track["direction"] == "clockwise"
    assert track["duration_ms"] == 600
    assert track["delay_ms"] == 0
    assert track["easing"] == "ease-out"
    assert track["from"] == 0
    assert track["to"] == 1


def test_border_draw_keeps_direction_speed_and_range():
    tracks, _report = _resolve({
        "border.draw": {
            "phase": "transition_in",
            "direction": "start:left counterclockwise",
            "speed": 1200,
            "from": 0.25,
            "to": 0.75,
            "duration_ms": 900,
            "delay_ms": 80,
        },
    })

    track = tracks["border.draw"]
    assert track["phase"] == "transition_in"
    assert track["direction"] == "start:left counterclockwise"
    assert track["speed"] == 1200
    assert track["from"] == 0.25
    assert track["to"] == 0.75
    assert track["duration_ms"] == 900
    assert track["delay_ms"] == 80


def test_border_draw_values_are_clamped_and_direction_falls_back():
    tracks, _report = _resolve({
        "border.draw": {
            "phase": "entry",
            "direction": "sideways",
            "speed": 1,
            "from": -2,
            "to": 4,
            "duration_ms": 9000,
        },
    })

    track = tracks["border.draw"]
    assert track["direction"] == "clockwise"
    assert track["speed"] == 10
    assert track["from"] == 0
    assert track["to"] == 1
    assert track["duration_ms"] == 5000


def test_unknown_tracks_and_keys_are_preserved():
    tracks, report = _resolve({
        "background.fade": {
            "phase": "entry",
            "from": "#000000",
            "to": "#ffffff",
            "stops": ["#000000", "#ffffff"],
        },
    })

    track = tracks["background.fade"]
    assert track["phase"] == "entry"
    assert track["from"] == "#000000"
    assert track["to"] == "#ffffff"
    assert track["stops"] == ["#000000", "#ffffff"]
    assert any("unknown property track preserved" in note for note in report.notes)


def test_track_without_a_phase_is_dropped():
    tracks, _report = _resolve({
        "border.draw": {"direction": "clockwise"},
    })

    assert tracks == {}


def test_malformed_track_id_is_dropped():
    tracks, _report = _resolve({
        "border": {"phase": "entry"},
    })

    assert tracks == {}
