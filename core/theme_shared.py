"""
core/theme_shared.py

Shared theme definitions: `themes/_shared/{borders,shadows,palettes,animations}.json`.

The lister skips every path with a `_`-prefixed segment, so these files are
never offered as themes. They are loaded here, validated with the same rules
as inline values, cached by mtime, and expanded into the theme copy that the
validator sees. The raw theme keeps its `{shared: ...}` / `@color` references.

Public API:
    resolve_shared(theme, report=..., base_dir=...) -> dict
    load_family(family, report=..., base_dir=...) -> dict
    clear_cache()
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from core.theme_schema import (
    SCHEMA_VERSION,
    ThemeReport,
    _coerce_border,
    _coerce_shadow,
    sanitize_color,
    validate_animation_definition,
)

logger = logging.getLogger(__name__)

SHARED_DIR = Path(__file__).resolve().parent.parent / "themes" / "_shared"

FAMILIES = ("borders", "shadows", "palettes", "animations")
# Family -> the key that holds its entries in the file.
_FAMILY_KEY = {
    "borders": "borders",
    "shadows": "shadows",
    "palettes": "colors",
    "animations": "animations",
}

_AT_NAME_RE = re.compile(r"^@([A-Za-z_][A-Za-z0-9_-]{0,63})$")
_AT_OUTLINE_RE = re.compile(
    r"^(\d+(?:\.\d+)?(?:px|em))\s+@([A-Za-z_][A-Za-z0-9_-]{0,63})$", re.I)

# family -> (file mtime, palette mtime, entries). Palette entries are expanded
# into every other family before validation, so a palette edit must invalidate
# borders/shadows/animations too — hence the second mtime.
_cache: dict[str, tuple[float, float, dict]] = {}


def clear_cache() -> None:
    """Forget every cached shared file (tests and Settings reloads)."""
    _cache.clear()


def _shared_path(family: str, base_dir: Optional[Path] = None) -> Path:
    root = Path(base_dir) if base_dir is not None else SHARED_DIR
    return root / f"{family}.json"


def _cache_key(family: str, base_dir: Optional[Path] = None) -> str:
    """Cache identity: the directory *and* family.

    Keying by family alone would let a test (or a relocated `themes/` dir)
    read a stale entry when two directories happen to share an mtime.
    """
    return f"{_shared_path(family, base_dir).parent.resolve()}:{family}"


def _empty(report: Optional[ThemeReport], path: str, message: str) -> dict:
    if report is not None:
        report.warn(path, message, None, "{}")
    return {}


def _validate_entries(family: str, entries: dict, *,
                      report: ThemeReport, path: str) -> dict:
    out: dict = {}
    for name, raw in entries.items():
        if not isinstance(name, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$",
                                                     name):
            report.warn(f"{path}.{name}", "invalid shared name", name, "dropped")
            continue
        entry_path = f"{path}.{name}"
        if family == "palettes":
            # A palette entry may point at another palette entry; the chain
            # (with its depth limit and cycle detection) resolves at expansion.
            if isinstance(raw, str) and _AT_NAME_RE.match(raw.strip()):
                out[name] = raw.strip()
                continue
            color = sanitize_color(raw)
            if color is None:
                report.warn(entry_path, "invalid shared color", raw, "dropped")
                continue
            out[name] = color
        elif family == "borders":
            validated = _coerce_border(raw, None, path=entry_path, report=report)
            if validated is None or validated == "none":
                report.warn(entry_path, "invalid shared border", raw, "dropped")
                continue
            if isinstance(validated, dict) and set(validated) == {"shared"}:
                report.warn(entry_path, "shared border cannot reference another",
                            validated, "dropped")
                continue
            out[name] = validated
        elif family == "shadows":
            validated = _coerce_shadow(raw, None, path=entry_path, report=report)
            if validated is None or validated == "none":
                report.warn(entry_path, "invalid shared shadow", raw, "dropped")
                continue
            if isinstance(validated, dict) and set(validated) == {"shared"}:
                report.warn(entry_path, "shared shadow cannot reference another",
                            validated, "dropped")
                continue
            out[name] = validated
        elif family == "animations":
            validated = validate_animation_definition(raw, name,
                                                      path=entry_path,
                                                      report=report)
            if validated is None:
                continue
            out[name] = validated
    return out


def load_family(family: str, *, report: Optional[ThemeReport] = None,
                base_dir: Optional[Path] = None) -> dict:
    """Load and validate one shared family. Missing/broken -> {}.

    Non-palette families have their `@color` references expanded *before*
    validation, because a border entry may legitimately say `"color": "@gold"`
    (§5.2). That makes the palette file an input to every family, so the cache
    entry records both mtimes.
    """
    if family not in FAMILIES:
        return {}
    path = _shared_path(family, base_dir)
    cache_key = _cache_key(family, base_dir)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache.pop(cache_key, None)
        return {}

    palette_mtime = 0.0
    if family != "palettes":
        try:
            palette_mtime = _shared_path("palettes", base_dir).stat().st_mtime
        except OSError:
            palette_mtime = 0.0

    cached = _cache.get(cache_key)
    if cached and cached[0] == mtime and cached[1] == palette_mtime:
        return cached[2]

    def remember(entries: dict) -> dict:
        _cache[cache_key] = (mtime, palette_mtime, entries)
        return entries

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Shared theme file %s failed to load: %s", path, exc)
        return remember({})

    if not isinstance(raw, dict):
        logger.error("Shared theme file %s is not an object", path)
        return remember({})

    version = raw.get("schema_version", SCHEMA_VERSION)
    if isinstance(version, str) and version.strip().isdigit():
        version = int(version.strip())
    if not isinstance(version, int) or isinstance(version, bool) \
            or version > SCHEMA_VERSION:
        if report is not None:
            report.warn(f"{path.name}", "unsupported shared schema version",
                        raw.get("schema_version"), "ignored")
        return remember({})

    entries = raw.get(_FAMILY_KEY[family])
    if not isinstance(entries, dict):
        if entries is not None and report is not None:
            report.warn(f"{path.name}.{_FAMILY_KEY[family]}",
                        "shared entries must be an object",
                        type(entries).__name__, "{}")
        return remember({})

    local_report = report if report is not None else ThemeReport()
    if family != "palettes":
        palette = load_family("palettes", report=local_report,
                              base_dir=base_dir)
        if palette:
            entries = expand_colors(entries, palette,
                                    path=f"{path.name}.{_FAMILY_KEY[family]}",
                                    report=local_report)
    validated = _validate_entries(family, entries, report=local_report,
                                  path=path.name)
    return remember(validated)


# ─── Reference expansion ────────────────────────────────────────────────────


def _palette_lookup(name: str, palette: dict, *, path: str,
                    report: ThemeReport, depth: int = 0,
                    seen: Optional[set] = None) -> Optional[str]:
    if depth > 4:
        report.warn(path, "shared color reference nested too deep", name, None)
        return None
    seen = set() if seen is None else seen
    if name in seen:
        report.warn(path, "shared color cycle", name, None)
        return None
    seen.add(name)
    value = palette.get(name)
    if value is None:
        report.warn(path, "unknown shared color", name, None)
        return None
    if isinstance(value, str):
        match = _AT_NAME_RE.match(value.strip())
        if match:
            return _palette_lookup(match.group(1), palette, path=path,
                                   report=report, depth=depth + 1, seen=seen)
    return value


def _expand_at_string(value: str, palette: dict, *, path: str,
                      report: ThemeReport) -> str:
    text = value.strip()
    match = _AT_NAME_RE.match(text)
    if match:
        resolved = _palette_lookup(match.group(1), palette, path=path,
                                   report=report)
        return resolved if resolved is not None else value
    match = _AT_OUTLINE_RE.match(text)
    if match:
        resolved = _palette_lookup(match.group(2), palette, path=path,
                                   report=report)
        if resolved is not None:
            return f"{match.group(1)} {resolved}"
    return value


def expand_colors(value: Any, palette: dict, *, path: str,
                  report: ThemeReport) -> Any:
    """Recursively expand `@name` strings; leave gradients/shadows literal."""
    if isinstance(value, dict):
        return {key: expand_colors(item, palette, path=f"{path}.{key}",
                                   report=report)
                for key, item in value.items()}
    if isinstance(value, list):
        return [expand_colors(item, palette, path=f"{path}[{index}]",
                              report=report)
                for index, item in enumerate(value)]
    if isinstance(value, str) and "@" in value:
        return _expand_at_string(value, palette, path=path, report=report)
    return value


def _resolve_ref(value: Any, *, family: str, own: dict, other: dict,
                 other_family: str, palette: dict, path: str,
                 report: ThemeReport) -> Any:
    if not (isinstance(value, dict) and set(value) == {"shared"}):
        return value
    name = value.get("shared")
    if not isinstance(name, str):
        report.warn(path, "invalid shared reference", value, "field default")
        return None
    entry = own.get(name)
    if entry is None and name in other:
        report.warn(path, "shared name found in another family", name,
                    other_family)
        entry = other[name]
    if entry is None:
        report.warn(path, f"unknown shared {family} name", name, "field default")
        return None
    return expand_colors(entry, palette, path=f"{family}.{name}", report=report)


def _resolve_fields(container: dict, *, palette: dict, borders: dict,
                    shadows: dict, path: str, report: ThemeReport) -> None:
    if "border" in container:
        resolved = _resolve_ref(container["border"], family="border",
                                own=borders, other=shadows,
                                other_family="shadows", palette=palette,
                                path=f"{path}.border", report=report)
        if resolved is None:
            container.pop("border", None)
        else:
            container["border"] = expand_colors(resolved, palette,
                                                path=f"{path}.border",
                                                report=report)
    if "box_shadow" in container:
        resolved = _resolve_ref(container["box_shadow"], family="box_shadow",
                                own=shadows, other=borders,
                                other_family="borders", palette=palette,
                                path=f"{path}.box_shadow", report=report)
        if resolved is None:
            container.pop("box_shadow", None)
        else:
            container["box_shadow"] = expand_colors(resolved, palette,
                                                    path=f"{path}.box_shadow",
                                                    report=report)
    for key in ("background",):
        if key in container:
            container[key] = expand_colors(container[key], palette,
                                           path=f"{path}.{key}",
                                           report=report)
    for block_id, block in (container.get("blocks") or {}).items():
        if not isinstance(block, dict):
            continue
        block_path = f"{path}.blocks.{block_id}"
        for key in ("color", "text_outline"):
            if key in block:
                block[key] = expand_colors(block[key], palette,
                                           path=f"{block_path}.{key}",
                                           report=report)


def resolve_shared(theme: dict, *, report: Optional[ThemeReport] = None,
                   base_dir: Optional[Path] = None) -> dict:
    """Expand shared references in `theme` in place; return shared animations.

    The caller passes a working copy (normalize_theme deep-copies first), so
    mutating it is safe. The returned map is the validated `_shared` animation
    library used for slot name resolution.
    """
    report = report if report is not None else ThemeReport()
    palette = load_family("palettes", report=report, base_dir=base_dir)
    borders = load_family("borders", report=report, base_dir=base_dir)
    shadows = load_family("shadows", report=report, base_dir=base_dir)
    animations = load_family("animations", report=report, base_dir=base_dir)

    if palette:
        animations = expand_colors(animations, palette, path="animations",
                                   report=report)
        theme["animations"] = expand_colors(
            theme.get("animations"), palette, path="animations", report=report)
        canvas = theme.get("canvas")
        if isinstance(canvas, dict) and "background" in canvas:
            canvas["background"] = expand_colors(
                canvas["background"], palette, path="canvas.background",
                report=report)

    containers = theme.get("containers")
    if isinstance(containers, list):
        for index, container in enumerate(containers):
            if isinstance(container, dict):
                _resolve_fields(container, palette=palette, borders=borders,
                                shadows=shadows, path=f"containers[{index}]",
                                report=report)

    return animations
