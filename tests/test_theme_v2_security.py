"""
tests/test_theme_v2_security.py

Injection gate for docs/theme_schema_v2.md §6:
- every CSS-valued field rejects `url()`, `var()`, `expression()`, `;`, `}`,
  `</`, `javascript:` and friends, falling back to its documented default;
- ids and animation names are identifier-shaped, never markup or selectors;
- free text (labels, descriptions) is normalized to plain data with control
  characters removed and a length cap, never escaped-in-place;
- shared references and keyframe numbers cannot smuggle CSS;
- the resolved dict is JSON-serializable (it crosses the WebSocket).
"""

import json

import pytest

from core.theme_schema import (
    ThemeReport,
    normalize_theme,
    sanitize_backdrop_filter,
    sanitize_border_string,
    sanitize_color,
    sanitize_font_family,
    sanitize_outline,
    sanitize_shadow,
)

# Values that must never reach the renderer as CSS.
INJECTIONS = [
    "url(https://evil.example/x.png)",
    "#fff; background: url(https://evil.example/x)",
    "red}</style><script>alert(1)</script>",
    "var(--rc-bg)",
    "expression(alert(1))",
    "javascript:alert(1)",
    "#fff !important",
    "linear-gradient(red, url(https://evil.example/x))",
    "0 0 0 #000; background:url(x)",
    "'Nunito'; } body { background: url(x) }",
    "2px #000;} html{background:url(x)",
    "rgb(1,2,3)) ; color: red",
    "blur(10px) url(x)",
]


@pytest.mark.parametrize("payload", INJECTIONS)
def test_color_sanitizer_rejects_injection(payload):
    assert sanitize_color(payload) is None


@pytest.mark.parametrize("payload", INJECTIONS)
def test_shadow_sanitizer_rejects_injection(payload):
    assert sanitize_shadow(payload) is None


@pytest.mark.parametrize("payload", INJECTIONS)
def test_outline_sanitizer_rejects_injection(payload):
    assert sanitize_outline(payload) is None


@pytest.mark.parametrize("payload", INJECTIONS)
def test_border_sanitizer_rejects_injection(payload):
    assert sanitize_border_string(payload) is None


@pytest.mark.parametrize("payload", INJECTIONS)
def test_font_family_sanitizer_rejects_injection(payload):
    assert sanitize_font_family(payload) is None


@pytest.mark.parametrize("payload", INJECTIONS)
def test_filter_sanitizer_rejects_injection(payload):
    assert sanitize_backdrop_filter(payload) is None


@pytest.mark.parametrize("payload", INJECTIONS)
def test_container_css_fields_fall_back_to_defaults(payload):
    resolved, report = normalize_theme({
        "schema_version": 2,
        "canvas": {"background": payload},
        "containers": [{
            "id": "main",
            "background": payload,
            "border": payload,
            "box_shadow": payload,
            "backdrop_filter": payload,
            "blocks": {
                "text": {"color": payload},
            },
        }],
    }, name="evil")

    container = resolved["containers"][0]
    assert resolved["canvas"]["background"] == "transparent"
    assert container["background"] == "transparent"
    assert container["border"] == "none"
    assert container["box_shadow"] == "none"
    assert container["backdrop_filter"] == "none"
    assert container["blocks"]["text"]["color"] == "#f8fafc"
    assert report.warnings, "every rejected value must be reported"
    assert report.ok
    json.dumps(resolved)


@pytest.mark.parametrize("field, expected", [
    ("font_family", "'Nunito', sans-serif"),
    ("text_shadow", "0 4px 12px rgba(0,0,0,0.4)"),
    ("text_outline", "none"),
])
def test_text_block_css_fields_fall_back_to_defaults(field, expected):
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "blocks": {"text": {field: INJECTIONS[0]}}}],
    }, name="evil")
    assert resolved["containers"][0]["blocks"]["text"][field] == expected
    assert report.warnings


def test_structured_shadow_color_is_validated():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "box_shadow": {"x": 0, "y": 4, "blur": 12,
                           "color": "url(https://evil.example/x)"},
        }],
    }, name="evil")
    shadow = resolved["containers"][0]["box_shadow"]
    assert shadow["color"] == "rgba(0,0,0,0.5)"
    assert report.warnings


def test_structured_border_color_is_validated():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "border": {"width": 2, "style": "solid",
                       "color": "javascript:alert(1)"},
        }],
    }, name="evil")
    assert resolved["containers"][0]["border"]["color"] == "currentColor"
    assert report.warnings


@pytest.mark.parametrize("bad_id", [
    "main; } html { background: url(x)",
    "Main",
    "<script>",
    "a" * 40,
    "a b",
    "main)]",
])
def test_container_ids_are_identifier_shaped(bad_id):
    resolved, report = normalize_theme({
        "schema_version": 2, "containers": [{"id": bad_id}],
    }, name="evil")
    assert resolved["containers"][0]["id"] == "container0"
    assert report.warnings


def test_labels_and_descriptions_are_plain_data_with_controls_removed():
    label = "<img src=x onerror=alert(1)>\x1b[31m\x7f"
    resolved, report = normalize_theme({
        "schema_version": 2,
        "description": "line one\x00\x08line two\nline three",
        "author": "A\x0bB",
        "containers": [{"id": "main", "label": label}],
    }, name="evil")

    container = resolved["containers"][0]
    # Data, not markup: the characters survive as *text* (the renderer must
    # use textContent) but no control characters do.
    assert "<" not in container["label"] or container["label"].startswith("<img")
    assert "\x1b" not in container["label"]
    assert "\x7f" not in container["label"]
    assert resolved["description"] == "line oneline two\nline three"
    assert resolved["author"] == "AB"
    assert report.ok


def test_names_cannot_escape_the_identifier_grammar():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "name": "../../etc/passwd",
        "containers": [{"id": "main"}],
    }, name="fallback-name")
    assert resolved["name"] == "fallback-name"
    assert report.warnings


@pytest.mark.parametrize("bad_name", [
    "fade; alert(1)",
    "fade_in}",
    "<fade>",
    "fade in!",
    "1fade",
])
def test_animation_names_reject_injection(bad_name):
    resolved, report = normalize_theme({
        "schema_version": 2,
        "animations": {bad_name: {"type": "fade_in", "duration_ms": 300}},
        "containers": [{"id": "main", "animation": {"entry": bad_name}}],
    }, name="evil")
    assert bad_name not in resolved["animations"]
    # The slot degrades to the documented default, not to the bad name.
    assert resolved["containers"][0]["animation"]["entry"] == {"use": "fade_in"}
    assert report.warnings


def test_unknown_animation_names_fall_back_with_a_warning():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main",
                        "animation": {"entry": "does_not_exist"}}],
    }, name="probe")
    assert resolved["containers"][0]["animation"]["entry"] == {"use": "fade_in"}
    assert any("unknown animation name" in w for w in report.warnings)
    # The fallback definition is embedded, so the renderer never chases a name.
    assert resolved["animations"]["fade_in"]["type"] == "fade_in"


def test_keyframe_css_values_cannot_smuggle_functions():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "animations": {"bad": {
            "type": "custom", "duration_ms": 400,
            "keyframes": [
                {"at": 0, "translate_x": "url(x)", "blur": "url(x)"},
                {"at": 100, "translate_x": 0, "blur": 0},
            ],
        }},
        "containers": [{"id": "main", "animation": {"entry": "bad"}}],
    }, name="evil")
    frames = resolved["animations"]["bad"]["keyframes"]
    assert frames[0]["translate_x"] == 0
    assert frames[0]["blur"] == 0
    assert report.warnings


def test_typewriter_cursor_char_is_capped_and_color_is_validated():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "animations": {"ty": {
            "type": "typewriter", "duration_ms": 900,
            "cursor": {"char": "<script>", "color": "url(x)"},
        }},
        "containers": [{"id": "main", "animation": {"entry": "ty"}}],
    }, name="evil")
    cursor = resolved["animations"]["ty"]["cursor"]
    assert cursor["char"] == "<s"
    assert cursor["color"] == "currentColor"
    assert report.warnings


def test_shared_references_must_be_identifiers():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "border": {"shared": "x; } body { background: url(y)"},
            "box_shadow": {"shared": "../secrets"},
        }],
    }, name="evil")
    assert resolved["containers"][0]["border"] == "none"
    assert resolved["containers"][0]["box_shadow"] == "none"
    assert report.warnings


def test_easing_cannot_carry_css():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "animations": {"bad": {"type": "fade_in", "duration_ms": 300,
                               "easing": "ease-out; background: url(x)"}},
        "containers": [{"id": "main", "animation": {"entry": "bad"}}],
    }, name="evil")
    assert resolved["animations"]["bad"]["easing"] == "ease-out"
    assert report.warnings


def test_percentage_is_rejected_where_it_has_no_meaning():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "blocks": {"text": {"size": "50%", "padding": "10%"}},
        }],
    }, name="probe")
    block = resolved["containers"][0]["blocks"]["text"]
    assert block["size"] == 40          # documented default
    assert block["padding"] == 0
    assert len(report.warnings) >= 2


def test_length_fields_cannot_smuggle_functions():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{
            "id": "main",
            "width": "calc(100% - url(x))",
            "position": {"anchor": "top_left", "x": "url(x)"},
            "blocks": {"text": {"size": "url(x)", "margin_top": "url(x)"}},
        }],
    }, name="evil")
    container = resolved["containers"][0]
    assert container["width"] == "auto"
    assert container["position"] == {"anchor": "top_left", "x": 0}
    assert container["blocks"]["text"]["size"] == 40
    assert container["blocks"]["text"]["margin_top"] == 0
    assert report.warnings


def test_resolved_theme_from_a_hostile_document_is_json_safe():
    resolved, _ = normalize_theme({
        "schema_version": 2,
        "name": "evil",
        "description": "x" * 2000,
        "canvas": {"width": "1e9", "height": -5, "fit": "stretch"},
        "containers": [{
            "id": "<main>",
            "layer": "NaN",
            "opacity": "Infinity",
            "width": "calc(100vw)",
            "background": INJECTIONS[0],
            "blocks": {"text": {"size": "1e9", "weight": "bold"}},
        }],
    }, name="evil")
    dumped = json.dumps(resolved, allow_nan=False)
    assert "url(" not in dumped
    assert "Infinity" not in dumped
    assert "NaN" not in dumped
    assert len(resolved["description"]) == 500
    assert resolved["canvas"]["width"] == 1920
    assert resolved["canvas"]["height"] == 240
    assert resolved["containers"][0]["layer"] == 0
    assert resolved["containers"][0]["opacity"] == 1
    assert resolved["containers"][0]["width"] == "auto"


def test_a_report_never_contains_unescaped_newlines_from_values():
    report = ThemeReport(theme="probe")
    report.warn("x", "bad", "line1\nline2")
    assert "\n" not in report.warnings[0] or "value='line1\\nline2'" in report.warnings[0]
