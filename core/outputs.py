"""Output registry: which display outputs belong to which display tab.

Scriptures owns Displays 1-3, Decks owns 4-6 (each with localhost + LAN
variants via ?output=N — see ThemesPanel). Media (7-8) and Presentation
(9-10) ids are reserved for future tabs; the router and WS layer accept
them today so those tabs slot in without re-architecting.

Output mode (Settings → Display & Broadcast → Display Output):
- simultaneous: every tab broadcasts through its own set at the same time;
  shared display state is OFF (each tab keeps its own Preview/Live).
- prioritized: one set at a time; a broadcast cloaks the other sets.
  Shared display state is ON (today's behavior).
"""

SCRIPTURE_OUTPUTS = ("1", "2", "3")
DECK_OUTPUTS = ("4", "5", "6")
MEDIA_OUTPUTS = ("7", "8")
PRESENTATION_OUTPUTS = ("9", "10")

# Internal tab keys (match main_window._tabs) -> output ids.
TAB_OUTPUTS = {
    "SCRIPTURE": SCRIPTURE_OUTPUTS,
    "SLIDES": DECK_OUTPUTS,
    "MEDIA": MEDIA_OUTPUTS,
    "PRESENTATION": PRESENTATION_OUTPUTS,
}

ALL_OUTPUTS: tuple = tuple(
    oid for oids in TAB_OUTPUTS.values() for oid in oids
)

MODE_SIMULTANEOUS = "simultaneous"
MODE_PRIORITIZED = "prioritized"
OUTPUT_MODE_KEY = "display.output_mode"
DEFAULT_MODE = MODE_PRIORITIZED

# Per-tab active output list, e.g. display.active_outputs_SLIDES="4,6".
ACTIVE_OUTPUTS_KEY_PREFIX = "display.active_outputs_"


def outputs_for_tab(tab_key: str) -> tuple:
    """Output ids a display tab CAN use (empty for unknown/core tabs).

    The pool. What a tab actually uses right now is active_outputs() —
    the operator can add/remove outputs in the tab's Outputs page, but
    never an id outside its own pool.
    """
    return TAB_OUTPUTS.get(tab_key, ())


def _active_key(tab_key: str) -> str:
    return f"{ACTIVE_OUTPUTS_KEY_PREFIX}{tab_key}"


def active_outputs(tab_key: str) -> tuple:
    """Output ids a tab is currently using, in order.

    Stored as an explicit list so any output can be deleted (leaving the
    survivors' ids and themes untouched — a hole is fine, renumbering is
    not: the operator's OBS scenes point at these ids). Falls back to the
    whole pool when unset/unreadable, and to a single output when the
    stored list is empty or corrupt.
    """
    pool = outputs_for_tab(tab_key)
    if not pool:
        return ()
    try:
        from core.database import get_setting
        raw = get_setting(_active_key(tab_key), "") or ""
    except Exception:
        return tuple(pool)
    if not raw.strip():
        return tuple(pool)  # never configured: the whole pool is in use
    stored = [oid.strip() for oid in raw.split(",") if oid.strip() in pool]
    # De-duplicate, keep order, drop anything outside the pool.
    seen: list[str] = []
    for oid in stored:
        if oid not in seen:
            seen.append(oid)
    if not seen:
        return (pool[0],)
    return tuple(seen)


def set_active_outputs(tab_key: str, output_ids) -> tuple:
    """Persist a tab's active output list. Returns what was stored.

    Always at least one output (an operator cannot end up with no
    output at all) and never an id outside the tab's own pool. Unknown
    tabs and all-rejected lists leave the stored list untouched.
    """
    pool = outputs_for_tab(tab_key)
    if not pool:
        return active_outputs(tab_key)
    wanted = [str(oid).strip() for oid in (output_ids or [])]
    kept: list[str] = []
    for oid in wanted:
        if oid in pool and oid not in kept:
            kept.append(oid)
    if not kept:
        return active_outputs(tab_key)
    try:
        from core.database import set_setting
        if not set_setting(_active_key(tab_key), ",".join(kept)):
            return active_outputs(tab_key)
    except Exception:
        return active_outputs(tab_key)
    return tuple(kept)


def add_active_output(tab_key: str) -> tuple:
    """Append the lowest unused pool id. No-op at the pool's size."""
    pool = outputs_for_tab(tab_key)
    current = active_outputs(tab_key)
    for oid in pool:
        if oid not in current:
            return set_active_outputs(tab_key, list(current) + [oid])
    return current


def remove_active_output(tab_key: str, output_id: str) -> tuple:
    """Drop one output id. The last remaining output stays (a tab must
    always have one), so this is a no-op at a count of one."""
    current = active_outputs(tab_key)
    if len(current) <= 1 or str(output_id) not in current:
        return current
    return set_active_outputs(
        tab_key, [oid for oid in current if oid != str(output_id)])


def main_output_for_tab(tab_key: str) -> str | None:
    """The tab's main output — its first active id (None for core tabs)."""
    current = active_outputs(tab_key)
    return current[0] if current else None


def can_add_output(tab_key: str) -> bool:
    """Whether an unused pool id remains for this tab."""
    pool = outputs_for_tab(tab_key)
    current = active_outputs(tab_key)
    return len(current) < len(pool)


def tab_for_output(output_id: str) -> str | None:
    """Owning tab key for an output id (None if unassigned)."""
    for tab_key, oids in TAB_OUTPUTS.items():
        if str(output_id) in oids:
            return tab_key
    return None


def is_valid_output(output_id) -> bool:
    """Whether an output id may carry clients and state."""
    return str(output_id) in ALL_OUTPUTS


def get_output_mode() -> str:
    """Configured output mode, defaulting to prioritized. Never raises."""
    try:
        from core.database import get_setting
        mode = (get_setting(OUTPUT_MODE_KEY, DEFAULT_MODE) or "").strip()
        if mode in (MODE_SIMULTANEOUS, MODE_PRIORITIZED):
            return mode
    except Exception:
        pass
    return DEFAULT_MODE


def set_output_mode(mode: str) -> bool:
    """Persist the output mode. Returns False (and writes nothing) for
    unknown modes."""
    if mode not in (MODE_SIMULTANEOUS, MODE_PRIORITIZED):
        return False
    try:
        from core.database import set_setting
        return bool(set_setting(OUTPUT_MODE_KEY, mode))
    except Exception:
        return False


def shared_display_enabled(mode: str | None = None) -> bool:
    """Whether tabs share one Preview/Live state. Derived from the mode:
    simultaneous -> each tab keeps its own; prioritized -> shared, since
    only one set is ever on air at a time."""
    if mode is None:
        mode = get_output_mode()
    return mode == MODE_PRIORITIZED
