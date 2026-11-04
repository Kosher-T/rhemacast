"""
core/theme_loader.py

Modular theme system. Themes are JSON files grouped by kind:
  themes/scripture/*.json  — verse/schedule display themes
  themes/freeform/*.json   — song/slide display themes

To create a new theme:
1. Copy themes/scripture/default.json (or the freeform slides theme)
2. Modify the values
3. Save under themes/scripture/ or themes/freeform/ as your_theme_name.json
4. The theme appears automatically in the matching picker.

Two shapes live side by side:

- **raw** (`get_theme`) — exactly what is on disk. v1 themes stay v1 until the
  designer saves them as v2. The designer edits this dict.
- **resolved** (`resolve_theme`) — a complete, validated, migrated v2 theme.
  Every payload builder and preview uses this.

Paths whose name starts with `_` (`themes/_shared/`) are support files, not
themes: they never appear in a picker and never count as a theme kind.
"""

import copy
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# themes/ directory is at project root
_THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"

# Known theme kinds (= subfolder names). Loose themes/*.json files left over
# from before the split are treated as "scripture" for backward compat.
SCRIPTURE = "scripture"
FREEFORM = "freeform"

# Cache: name -> raw theme dict (as loaded from disk)
_cache: dict[str, dict] = {}
# name -> resolved v2 theme + the mtime it was resolved from
_resolved_cache: dict[str, tuple[float, dict]] = {}
# name -> source file path (so saves write back to the right subfolder)
_paths: dict[str, Path] = {}
_loaded = False
_current_theme: str = "default"
# Track file modification times to detect edits
_file_mtimes: dict[str, float] = {}


def set_current_theme(name: str):
    """Set the globally active theme name."""
    global _current_theme
    _current_theme = name
    # Persist to settings
    try:
        from core.database import set_setting
        set_setting("display.last_theme", name)
    except Exception:
        pass


def get_current_theme_name() -> str:
    """Return the globally active theme name."""
    return _current_theme


def _kind_for_path(path: Path) -> str:
    """Theme kind from file location (subfolder name, else scripture)."""
    try:
        rel = path.relative_to(_THEMES_DIR)
        if len(rel.parts) > 1:
            return rel.parts[0]
    except ValueError:
        pass
    return SCRIPTURE


def _is_theme_path(path: Path) -> bool:
    """True unless any path segment under themes/ starts with `_`.

    `themes/_shared/` holds borders/shadows/palettes/animations. It is not a
    theme kind and its files are not themes.
    """
    try:
        rel = path.relative_to(_THEMES_DIR)
    except ValueError:
        return True
    return not any(part.startswith("_") for part in rel.parts)


def _theme_name(theme: dict, path: Path) -> str:
    name = theme.get("name")
    if isinstance(name, str) and name.strip():
        return name
    return path.stem


def _store(name: str, theme: dict, path: Path, mtime: float) -> None:
    _cache[name] = theme
    _paths[name] = path
    _file_mtimes[str(path)] = mtime
    _resolved_cache.pop(name, None)


def _load_all():
    """Scan themes/ subdirectories and load all .json files."""
    global _loaded
    if _loaded:
        return

    if not _THEMES_DIR.exists():
        logger.warning(f"Themes directory not found: {_THEMES_DIR}")
        _loaded = True
        return

    for path in sorted(_THEMES_DIR.rglob("*.json")):
        if not _is_theme_path(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                theme = json.load(f)
            if not isinstance(theme, dict):
                logger.error(f"Ignoring theme {path.name}: root is not an object")
                continue
            name = _theme_name(theme, path)
            if name in _cache:
                logger.warning(
                    "Duplicate theme name '%s': %s replaces %s",
                    name, path, _paths.get(name))
            _store(name, theme, path, os.path.getmtime(path))
        except Exception as e:
            logger.error(f"Failed to load theme {path.name}: {e}")

    _loaded = True
    logger.info(f"Loaded {len(_cache)} themes: {list(_cache.keys())}")

    # Load saved theme from settings
    try:
        from core.database import get_setting
        saved = get_setting("display.last_theme")
        if saved and saved in _cache:
            global _current_theme
            _current_theme = saved
            logger.info(f"Loaded saved theme: {saved}")
    except Exception:
        pass


def _check_for_changes():
    """Check if any theme files were modified on disk; reload changed ones."""
    if not _loaded or not _THEMES_DIR.exists():
        return

    for path in _THEMES_DIR.rglob("*.json"):
        if not _is_theme_path(path):
            continue
        try:
            mtime = os.path.getmtime(path)
            key = str(path)
            if key in _file_mtimes and mtime > _file_mtimes[key]:
                # File changed — reload it
                with open(path, "r", encoding="utf-8") as f:
                    theme = json.load(f)
                if not isinstance(theme, dict):
                    logger.error(f"Ignoring theme {path.name}: root is not an object")
                    continue
                name = _theme_name(theme, path)
                _store(name, theme, path, mtime)
                logger.info(f"Theme '{name}' reloaded from disk (file changed)")
        except Exception as e:
            logger.error(f"Failed to reload theme {path.name}: {e}")


STAGE_W = 1920
STAGE_H = 1080


def _is_new_containers(containers) -> bool:
    """New-style `containers: {name: {...blocks...}}` vs the legacy absolute
    text/reference boxes (`{text: {x, y, ...}, ...}`). A new-style container
    always nests at least one content block (body/text/reference/...)."""
    if not isinstance(containers, dict):
        return False
    return any(isinstance(v, dict) and any(
        isinstance(v.get(k), dict) for k in
        ("body", "text", "reference", "translation", "verse_num", "title"))
        for v in containers.values())


def _containers_list(theme_data: dict) -> list:
    containers = theme_data.get("containers")
    if isinstance(containers, list):
        return [c for c in containers if isinstance(c, dict)]
    if isinstance(containers, dict) and _is_new_containers(containers):
        return [c for c in containers.values() if isinstance(c, dict)]
    return []


def theme_container(theme_data: Optional[dict], name: Optional[str] = None) -> dict:
    """The active container: geometry plus nested content blocks.

    Handles both shapes:

    - v2 / resolved: `containers` is an array; `name` matches `container.id`.
      A named lookup misses with a warning and falls back to the first.
    - v1 raw: `containers` is a dict of named nested containers.
    - legacy absolute boxes / flat themes: `{}` (callers treat absent blocks
      as "no opinion").

    A hidden container is still returned: the designer needs to edit it.
    """
    if not isinstance(theme_data, dict):
        return {}
    containers = theme_data.get("containers")

    if isinstance(containers, list):
        items = [c for c in containers if isinstance(c, dict)]
        if not items:
            return {}
        if name is not None:
            for container in items:
                if container.get("id") == name:
                    return container
            logger.warning(f"Container '{name}' not found — using first container.")
        return items[0]

    if not isinstance(containers, dict) or not containers:
        return {}
    if not _is_new_containers(containers):
        return {}
    if name is not None:
        if name in containers and isinstance(containers[name], dict):
            return containers[name]
        logger.warning(f"Container '{name}' not found — using first container.")
    for value in containers.values():
        if isinstance(value, dict):
            return value
    return {}


def container_block(theme_data: Optional[dict], block_id: str,
                    name: Optional[str] = None) -> dict:
    """One content block from the active container, both theme shapes.

    v2 keeps blocks under `container["blocks"]`; v1 keeps them directly on the
    container and older flat themes keep them at the top level. Returns `{}`
    when the block is absent.
    """
    if not isinstance(theme_data, dict):
        return {}
    container = theme_container(theme_data, name)
    blocks = container.get("blocks")
    if isinstance(blocks, dict):
        block = blocks.get(block_id)
        if isinstance(block, dict):
            return block
    block = container.get(block_id)
    if isinstance(block, dict):
        return block
    if name is None:
        block = theme_data.get(block_id)
        if isinstance(block, dict):
            return block
    return {}


def get_theme(name: str) -> Optional[dict]:
    """Get a theme's raw JSON by name. Returns None if not found.

    Raw means exactly what is on disk (v1 or v2). Use `resolve_theme()` for a
    complete, validated v2 dict.
    """
    _load_all()
    _check_for_changes()
    return _cache.get(name)


# Contract fallback (docs/theme-switch-contract.md): switch payloads must
# never carry a null theme_data. Unknown names resolve to a per-kind
# default with a loud warning — per-machine settings may name themes that
# do not exist on that machine (renamed/deleted files), and the switch
# must stay clean.
#
# Fallbacks are per content KIND, never app-wide: the scripture "default"
# theme is only the default for scriptures. Slides/freeform fall back to
# "slides"; future kinds (images, video) get their own entry here.
_FALLBACK_THEME = "default"

DEFAULT_THEME_FOR_KIND = {
    SCRIPTURE: "default",
    FREEFORM: "slides",
}


def _resolved_for(name: str) -> dict:
    """Resolve (and cache) one theme by name. Returns the live cache dict."""
    raw = _cache.get(name)
    if not isinstance(raw, dict):
        from core.theme_schema import normalize_theme
        resolved, _report = normalize_theme({}, kind=SCRIPTURE, name=name)
        return resolved

    path = _paths.get(name)
    mtime = _file_mtimes.get(str(path), 0.0) if path is not None else 0.0
    cached = _resolved_cache.get(name)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    try:
        from core.theme_schema import normalize_theme
        kind = _kind_for_path(path) if path is not None else SCRIPTURE
        resolved, _report = normalize_theme(raw, kind=kind, name=name)
    except Exception as exc:  # normalization must never break a broadcast
        from core.theme_schema import SAFE_THEME
        logger.exception("Theme '%s' failed to resolve: %s", name, exc)
        resolved = copy.deepcopy(SAFE_THEME)
        resolved["name"] = name
    _resolved_cache[name] = (mtime, resolved)
    return resolved


def resolve_theme(name: str, fallback: Optional[str] = None) -> tuple[str, dict]:
    """Resolve a theme name to (name, deepcopy of the resolved v2 theme).

    Unknown/empty names fall back to `fallback` (default: the scripture
    "default" theme) and log an error naming the bad configured value.
    Slide/freeform callers MUST pass fallback="slides" (or
    DEFAULT_THEME_FOR_KIND[FREEFORM]) so a missing slides theme never renders
    with the scripture theme.

    The returned dict is migrated, validated, default-filled v2. It is a
    deepcopy: payload builders must never hand out (or mutate) the live cache
    reference.
    """
    _load_all()
    _check_for_changes()
    theme = _cache.get(name) if name else None
    if theme is None:
        if fallback is None:
            fallback = _FALLBACK_THEME
        logger.error(
            f"Theme '{name}' not found — falling back to "
            f"'{fallback}'. Check output theme settings and "
            f"themes/*.json on this machine."
        )
        name = fallback
        if name not in _cache:
            from core.theme_schema import SAFE_THEME
            safe = copy.deepcopy(SAFE_THEME)
            safe["name"] = name or "default"
            return name or "default", safe
    return name, copy.deepcopy(_resolved_for(name))


def get_all_themes() -> dict[str, dict]:
    """Return all loaded raw themes as {name: theme_dict}. Checks for changes."""
    _load_all()
    _check_for_changes()
    return dict(_cache)


def get_theme_names() -> list[str]:
    """Return list of available theme names."""
    _load_all()
    return list(_cache.keys())


def get_theme_kind(name: str) -> str:
    """Return the kind ("scripture" / "freeform") of a theme by name."""
    _load_all()
    path = _paths.get(name)
    if path is None:
        return SCRIPTURE
    return _kind_for_path(path)


def get_themes_by_kind(kind: str) -> dict[str, dict]:
    """Return loaded raw themes of one kind as {name: theme_dict}."""
    _load_all()
    _check_for_changes()
    return {n: t for n, t in _cache.items()
            if _kind_for_path(_paths.get(n, _THEMES_DIR)) == kind}


def slide_title_visible(theme_data: Optional[dict]) -> bool:
    """Whether a slide payload rendered with this theme shows the deck title.

    The resolved v2 `title` block is authoritative; `slide.show_title` is the
    v1 fallback (and the resolved theme preserves it, so both shapes answer).
    Defaults to True so scripture themes (which have no "slide" section) are
    unaffected.
    """
    if not isinstance(theme_data, dict):
        return True
    slide = theme_data.get("slide")
    if isinstance(slide, dict) and "show_title" in slide:
        return slide.get("show_title", True) is not False
    title = container_block(theme_data, "title")
    if title:
        return title.get("visible", True) is not False
    return True


# A hard shadow: dx dy blur color, any `px` suffix optional (themes write
# single-axis shadows as "-2px 0 0 #000"), blur must be exactly zero.
_HARD_SHADOW_RE = re.compile(
    r"^\s*(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+"
    r"(#[0-9a-fA-F]{3,6})\s*$")


def theme_outline(text_block: Optional[dict]) -> Optional[str]:
    """A theme's text block -> canonical outline value ("2px #000000").

    Prefers an explicit `text_outline` key. Falls back to `text_shadow` when
    that shadow is actually a hard outline: zero blur, one color, uniform
    offsets — the classic hand-rolled 8-direction outline. Its thickness is
    the offset magnitude, so the theme's outline and a deck's `outline=Npx`
    are the same knob. Real drop shadows (blur > 0, or mixed colors) are left
    alone: they are depth, not outline.
    """
    if not isinstance(text_block, dict):
        return None
    explicit = str(text_block.get("text_outline") or "").strip()
    if explicit:
        # An explicit "none" is a decision, not an absence: it switches the
        # outline off even when a legacy hard text_shadow is present (that
        # shadow then renders literally, as the shadow it claims to be).
        if explicit.lower() in ("none", "off"):
            return None
        from core.slide_parser import _parse_outline
        parsed = _parse_outline(explicit)
        if parsed and parsed != "none":
            return parsed
    shadow = str(text_block.get("text_shadow") or "").strip()
    if not shadow or shadow.lower() == "none":
        return None
    from core.slide_parser import _parse_hex_color
    axis = 0.0      # pure "2px 0 0 #000" style offsets: the author's intent
    diagonal = 0.0  # magnitude of the corner copies
    colors = set()
    for part in shadow.split(","):
        m = _HARD_SHADOW_RE.match(part)
        if not m or float(m.group(3)) != 0:
            return None  # blur or an odd shape: a real drop shadow
        dx, dy = float(m.group(1)), float(m.group(2))
        magnitude = (dx * dx + dy * dy) ** 0.5
        if dy == 0:
            axis = max(axis, abs(dx))
        elif dx == 0:
            axis = max(axis, abs(dy))
        else:
            diagonal = max(diagonal, magnitude)
        colors.add(_parse_hex_color(m.group(4)))
    if not colors or len(colors) != 1:
        return None
    color = colors.pop()
    if not color:
        return None
    # An 8-direction outline spells out its thickness on the axes; fall back
    # to the corner magnitude only when there are no axis offsets at all.
    thickness = axis or diagonal
    if thickness <= 0:
        return None
    return f"{max(1, min(25, int(round(thickness))))}px {color}"


def _text_block(theme_data: Optional[dict]) -> dict:
    """The active container's text block, v2 or v1, or {}."""
    if not isinstance(theme_data, dict):
        return {}
    block = container_block(theme_data, "text")
    return block if isinstance(block, dict) else {}


def display_format_defaults(theme_data: Optional[dict]) -> dict:
    """Theme's baseline text formatting, for the designer ribbon.

    The theme styles the DISPLAY (weight, shadow/outline, case, align),
    but a card's document only carries what the deck's txt stores — so
    with nothing focused the ribbon would show everything inactive even
    though the theme makes the text bold and outlined on display. This
    maps the theme's "text" block onto the same switches the display
    renderer uses (see display_view: weight/text_shadow/text_transform/
    text_align), so the ribbon reflects the effective formatting.

    Works on both shapes: a resolved v2 theme (`container.blocks.text`) and
    a raw v1 theme (`container.text`, or flat `theme.text`). Only keys the
    theme actually sets are returned: absent means "no opinion", letting the
    deck's own run props decide.
    """
    t = _text_block(theme_data)
    if not t:
        return {}
    out: dict = {}

    color = t.get("color")
    if isinstance(color, str):
        from core.slide_parser import _parse_hex_color
        parsed_color = _parse_hex_color(color)
        if parsed_color:
            out["color"] = parsed_color

    size = t.get("size")
    if size is not None:
        try:
            out["size"] = max(1, int(float(str(size).rstrip("px").strip())))
        except (TypeError, ValueError):
            pass

    weight = t.get("weight")
    if weight is not None:
        try:
            out["bold"] = int(float(str(weight).rstrip("px").strip())) >= 600
        except (TypeError, ValueError):
            pass

    # The theme's outline is ONE property (`outline = "Npx #hex"`), the same
    # one a deck run sets, so `outline=12` in the txt simply broadens it and
    # `outline=none` switches it off. Themes may declare it directly, or keep
    # the legacy hard multi-direction `text_shadow`, which is an outline in
    # disguise (single color, zero blur, uniform offsets) and is converted.
    outline = theme_outline(t)
    if outline:
        out["outline"] = outline

    # Shadow as the ribbon needs it: "none" when the theme says none, or
    # when its hard ring was consumed as the outline above (it paints as
    # outline, not shadow); the raw value when a genuine drop shadow
    # rides along; absent when the theme says nothing at all.
    ts = t.get("text_shadow")
    if isinstance(ts, str) and ts.strip():
        slow = ts.strip().lower()
        if slow in ("none", "off"):
            out["shadow"] = "none"
        elif not (outline and theme_outline({"text_shadow": ts}) == outline):
            out["shadow"] = ts.strip()

    transform = str(t.get("text_transform") or "").strip().lower()
    if transform == "uppercase":
        out["case"] = "upper"
    elif transform == "lowercase":
        out["case"] = "lower"

    align = str(t.get("text_align") or "").strip().lower()
    if align in ("left", "center", "right", "justify"):
        out["align"] = align
    return out


def slide_display_ref(title: str, section: Optional[str],
                      theme_data: Optional[dict]) -> str:
    """Reference line for a slide payload under the rendering theme.

    Mirrors what the display output shows: themes opting out with
    {"slide": {"show_title": false}} (e.g. the freeform "slides" theme)
    render a blank reference line; all other themes show "Title · Section"
    (or just the title). Every slide preview MUST go through here so
    previews render exactly what display renders.
    """
    if not slide_title_visible(theme_data):
        return ""
    title = title or "(untitled)"
    return f"{title} · {section}" if section else title


def reload_themes():
    """Force reload all themes from disk."""
    global _loaded
    _loaded = False
    _cache.clear()
    _paths.clear()
    _file_mtimes.clear()
    _resolved_cache.clear()
    _load_all()


def save_theme(name: str, theme_dict: dict, subdir: Optional[str] = None):
    """Write a theme dict to its subfolder file and update the cache.

    The dict is written exactly as given — no normalization. The designer's
    v2 fields and any unknown keys must survive a load-edit-save round trip;
    validation happens on load/resolve, never here.

    Existing themes save back to their own file; new themes go under
    themes/{subdir}/ (default "scripture").
    """
    _load_all()
    if name in _paths:
        path = _paths[name]
    else:
        path = _THEMES_DIR / (subdir or SCRIPTURE) / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(theme_dict, f, indent=4, ensure_ascii=False)
        _store(name, theme_dict, path, os.path.getmtime(path))
        logger.info(f"Theme '{name}' saved to {path}")
    except Exception as e:
        logger.error(f"Failed to save theme '{name}': {e}")
        raise


def create_theme(name: str, label: str, source_name: str = "default",
                 subdir: Optional[str] = None) -> dict:
    """Create a new theme by cloning an existing one. Returns the new theme dict.

    The clone is raw (whatever is on disk). Without subdir, the clone lands in
    the source theme's own subfolder.
    """
    _load_all()
    source = _cache.get(source_name, _cache.get("default", {}))
    new_theme = copy.deepcopy(source)
    new_theme["name"] = name
    new_theme["label"] = label
    new_theme.pop("description", None)
    new_theme.pop("author", None)
    if subdir is None and source_name in _paths:
        subdir = _kind_for_path(_paths[source_name])
    save_theme(name, new_theme, subdir=subdir)
    return new_theme
