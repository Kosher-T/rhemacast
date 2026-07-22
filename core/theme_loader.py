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
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# themes/ directory is at project root
_THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"

# Cache: name -> theme dict
_cache: dict[str, dict] = {}
_loaded = False
_current_theme: str = "default"


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


def get_theme(name: str) -> Optional[dict]:
    """Get a theme by name. Returns None if not found."""
    _load_all()
    return _cache.get(name)


def get_all_themes() -> dict[str, dict]:
    """Return all loaded themes as {name: theme_dict}."""
    _load_all()
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
