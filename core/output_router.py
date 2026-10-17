"""Per-tab OBS fan-out + cross-set behavior (see core/outputs.py).

Both display tabs used to carry copy-pasted WebSocket fan-out blocks;
they now build their per-output themed payloads (theme namespaces differ
per tab) and hand the finished map here. The router owns everything
after that: sending to the tab's own outputs, clearing a tab's outputs,
and — in prioritized mode only — cloaking the other tabs' sets.

No-ops (never raises): server loop down, empty maps, unknown tabs.
Callers keep their return contracts via the booleans.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def _run(coro) -> bool:
    """Run one WS coroutine on the server loop. False when down/closed."""
    try:
        from core.websocket_server import _server_loop
    except Exception:
        return False
    if _server_loop is None or _server_loop.is_closed():
        return False
    try:
        asyncio.run_coroutine_threadsafe(coro, _server_loop)
        return True
    except Exception as e:
        logger.warning(f"Output fan-out failed: {e}")
        return False


def fan_out(themed_outputs: dict | None) -> bool:
    """Send already-built per-output payloads. True if any send started."""
    if not themed_outputs:
        return False
    from core.websocket_server import broadcast_display
    sent = False
    for output_id, payload in themed_outputs.items():
        if _run(broadcast_display(payload, target=str(output_id))):
            sent = True
    return sent


def clear_tab_outputs(tab_key: str) -> bool:
    """Blank a tab's OWN active output set (never touches other tabs' sets —
    in simultaneous mode a tab clear must not blank the other tab)."""
    from core.websocket_server import broadcast_display
    from core.outputs import active_outputs
    sent = False
    for output_id in active_outputs(tab_key):
        if _run(broadcast_display({"action": "clear"}, target=str(output_id))):
            sent = True
    return sent


def clear_output(output_id: str) -> bool:
    """Blank ONE output id.

    Used when the operator deletes an output: an OBS scene that is still
    connected would otherwise stay frozen on the last frame forever,
    because nothing writes to that id any more.
    """
    from core.websocket_server import broadcast_display
    from core.outputs import is_valid_output
    if not is_valid_output(output_id):
        return False
    return _run(broadcast_display({"action": "clear"}, target=str(output_id)))


def cloak_other_tabs(tab_key: str) -> bool:
    """Prioritized mode: blank every other tab's ACTIVE output sets so
    exactly one set is on air. Also drops their stored per-output
    snapshots from the shared state, so restore paths cannot resurrect a
    cloaked set. No-op in simultaneous mode (and when the mode is
    unreadable)."""
    from core.outputs import (TAB_OUTPUTS, active_outputs, get_output_mode,
                              MODE_PRIORITIZED)
    try:
        if get_output_mode() != MODE_PRIORITIZED:
            return False
    except Exception:
        return False
    from core.websocket_server import broadcast_display
    from core.display_state import display_state
    did = False
    for other in TAB_OUTPUTS:
        if other == tab_key:
            continue
        for output_id in active_outputs(other):
            if _run(broadcast_display({"action": "clear"},
                                       target=str(output_id))):
                did = True
            try:
                display_state.live_output_payloads.pop(str(output_id), None)
            except Exception:
                pass
    return did


def broadcast_tab_payload(tab_key: str, themed_outputs: dict | None) -> bool:
    """One tab gesture, fully routed: cloak the other sets first (a no-op
    unless prioritized), then fan out to this tab's own outputs."""
    cloak_other_tabs(tab_key)
    return fan_out(themed_outputs)
