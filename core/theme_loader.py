"""
core/theme_loader.py

Modular theme system. Themes are JSON files in the themes/ directory.
Each theme defines colors, typography, and layout for the OBS display.

To create a new theme:
1. Copy themes/default.json
2. Modify the values
3. Save as themes/your_theme_name.json
4. The theme appears automatically in the Themes panel.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# themes/ directory is at project root
_THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"

# Cache: name -> theme dict
_cache: dict[str, dict] = {}
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


def _load_all():
    """Scan themes/ directory and load all .json files."""
    global _cache, _loaded
    if _loaded:
        return

    if not _THEMES_DIR.exists():
        logger.warning(f"Themes directory not found: {_THEMES_DIR}")
        _loaded = True
        return

    for path in sorted(_THEMES_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                theme = json.load(f)
            name = theme.get("name", path.stem)
            _cache[name] = theme
            _file_mtimes[str(path)] = os.path.getmtime(path)
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

    for path in _THEMES_DIR.glob("*.json"):
        try:
            mtime = os.path.getmtime(path)
            key = str(path)
            if key in _file_mtimes and mtime > _file_mtimes[key]:
                # File changed — reload it
                with open(path, "r", encoding="utf-8") as f:
                    theme = json.load(f)
                name = theme.get("name", path.stem)
                _cache[name] = theme
                _file_mtimes[key] = mtime
                logger.info(f"Theme '{name}' reloaded from disk (file changed)")
        except Exception as e:
            logger.error(f"Failed to reload theme {path.name}: {e}")


def get_theme(name: str) -> Optional[dict]:
    """Get a theme by name. Returns None if not found. Checks for file changes."""
    _load_all()
    _check_for_changes()
    return _cache.get(name)


def get_all_themes() -> dict[str, dict]:
    """Return all loaded themes as {name: theme_dict}. Checks for file changes."""
    _load_all()
    _check_for_changes()
    return dict(_cache)


def get_theme_names() -> list[str]:
    """Return list of available theme names."""
    _load_all()
    return list(_cache.keys())


def reload_themes():
    """Force reload all themes from disk."""
    global _loaded
    _loaded = False
    _cache.clear()
    _load_all()


def save_theme(name: str, theme_dict: dict):
    """Write a theme dict to themes/{name}.json and update the cache."""
    _load_all()
    path = _THEMES_DIR / f"{name}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(theme_dict, f, indent=4, ensure_ascii=False)
        _cache[name] = theme_dict
        _file_mtimes[str(path)] = os.path.getmtime(path)
        logger.info(f"Theme '{name}' saved to {path}")
    except Exception as e:
        logger.error(f"Failed to save theme '{name}': {e}")
        raise


def create_theme(name: str, label: str, source_name: str = "default") -> dict:
    """Create a new theme by cloning an existing one. Returns the new theme dict."""
    _load_all()
    source = _cache.get(source_name, _cache.get("default", {}))
    import copy
    new_theme = copy.deepcopy(source)
    new_theme["name"] = name
    new_theme["label"] = label
    new_theme.pop("description", None)
    new_theme.pop("author", None)
    save_theme(name, new_theme)
    return new_theme
