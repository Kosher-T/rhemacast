"""
core/websocket_server.py

WebSocket server for broadcasting display events to OBS Browser Sources.
Supports multiple outputs (up to 3), each identified by ?output=N URL param.
Each output receives its own theme via targeted broadcast.
"""

import asyncio
import html
import json
import logging
import os
from typing import Set, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

import websockets
from websockets.server import WebSocketServerProtocol
from aiohttp import web

from .constants import (
    WS_CLOSE_TIMEOUT_S, WS_PING_INTERVAL_S, WS_PING_TIMEOUT_S,
)
from .queues import queue_a, queue_b, db_write_queue, operator_queue

logger = logging.getLogger(__name__)

# Server event loop — set when start_servers() runs; used by broadcast_display
_server_loop: Optional[asyncio.AbstractEventLoop] = None

# True once both listeners are accepting connections. The UI uses this to
# tell "no browser has connected yet" (idle) from "the display server could
# not start" (caution) — both have a client count of zero.
_server_ready = False

# Counts every accepted client, including one that connects and drops between
# UI polls. Lets the connection monitor tell "nothing has ever connected"
# apart from "the display link was lost".
_clients_seen = 0

# Per-output state: {oid: {websocket, ...}} — built from the output
# registry (core/outputs.py), so new display tabs only extend the map.
from core.outputs import ALL_OUTPUTS, is_valid_output

connected_clients: Dict[str, Set[WebSocketServerProtocol]] = {
    oid: set() for oid in ALL_OUTPUTS
}

# Per-output last display state (for hydrating new clients)
current_display_state: Dict[str, Dict[str, Any]] = {
    oid: {"action": "clear"} for oid in ALL_OUTPUTS
}

# Display directory path
DISPLAY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "display")


def get_connected_client_count() -> int:
    """Expose telemetry to UI thread — total across all outputs."""
    return sum(len(clients) for clients in connected_clients.values())


def get_output_client_counts() -> Dict[str, int]:
    """Per-output client counts."""
    return {oid: len(clients) for oid, clients in connected_clients.items()}


def is_server_ready() -> bool:
    """True once the WebSocket and HTTP servers are accepting connections."""
    return _server_ready


def has_seen_client() -> bool:
    """True once any browser display client has connected this run."""
    return _clients_seen > 0


def _ws_server_options() -> Dict[str, Any]:
    """websockets.serve options, kept in one place for the keepalive test.

    The short ping interval is what makes a silently dropped connection
    (pulled cable, Wi-Fi loss) visible within seconds instead of the
    library's 20 s / 20 s defaults. ``close_timeout`` caps the second wait:
    after a ping timeout the server still asks the dead peer to acknowledge
    the Close frame, and the handler (which removes the client from
    ``connected_clients``) doesn't return until that wait ends.
    """
    return {
        "max_size": 1024,
        "ping_interval": WS_PING_INTERVAL_S,
        "ping_timeout": WS_PING_TIMEOUT_S,
        "close_timeout": WS_CLOSE_TIMEOUT_S,
    }


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize all string fields to prevent XSS."""
    sanitized = {}
    for k, v in payload.items():
        if isinstance(v, str):
            sanitized[k] = html.escape(v)
        else:
            sanitized[k] = v
    return sanitized


async def broadcast_display(payload: Dict[str, Any], target: Optional[str] = None):
    """
    Broadcast a sanitized payload to connected clients.

    Args:
        payload: The display payload dict.
        target: Output ID to send to. If None, broadcasts to ALL outputs.
    """
    sanitized = sanitize_payload(payload)

    if target:
        # Single output
        outputs = [target]
    else:
        # All outputs
        outputs = list(connected_clients.keys())

    for oid in outputs:
        if oid not in connected_clients:
            continue
        current_display_state[oid] = sanitized
        clients = connected_clients[oid]
        if clients:
            message = json.dumps(sanitized)
            await asyncio.gather(
                *[client.send(message) for client in clients],
                return_exceptions=True
            )


async def ws_handler(websocket):
    """Handles new WebSocket connections. Parses ?output=N from URL."""
    global _clients_seen

    # Parse output ID from request path (e.g., /?output=1)
    output_id = "1"
    try:
        path = websocket.request.path
        if "?" in path:
            qs = parse_qs(urlparse(path).query)
            if "output" in qs:
                output_id = qs["output"][0]
    except Exception:
        pass

    # Clamp to a registered output (unknown ids fall back to 1).
    if not is_valid_output(output_id):
        output_id = "1"

    connected_clients[output_id].add(websocket)
    _clients_seen += 1
    total = get_connected_client_count()
    logger.info(f"WS client connected to output {output_id}. Total: {total}")

    try:
        # Push current state for this output on connect
        await websocket.send(json.dumps(current_display_state[output_id]))

        # Keep connection open
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients[output_id].discard(websocket)
        total = get_connected_client_count()
        logger.info(f"WS client disconnected from output {output_id}. Total: {total}")


async def health_handler(request: web.Request) -> web.Response:
    """HTTP GET endpoint returning queue depths and per-output client counts."""
    status = {
        "status": "ok",
        "clients": get_connected_client_count(),
        "output_clients": get_output_client_counts(),
        "queue_depths": {
            "queue_a": queue_a.qsize(),
            "queue_b": queue_b.qsize(),
            "db_write_queue": db_write_queue.qsize(),
            "operator_queue": operator_queue.qsize(),
        }
    }
    return web.json_response(status)


@web.middleware
async def _no_cache_middleware(request: web.Request, handler) -> web.StreamResponse:
    """Display assets must never be cached: a stale display.js/themes.css
    in OBS would silently run pre-fix renderer logic. Contract §
    Per-machine state — caches are inputs, never preconditions."""
    resp = await handler(request)
    if request.path.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


async def start_servers():
    """Starts both the WebSocket and HTTP Health servers."""
    global _server_loop, _server_ready
    _server_loop = asyncio.get_running_loop()

    ws_host = "0.0.0.0"
    ws_port = 8765

    http_host = "0.0.0.0"
    http_port = 8766

    logger.info(f"Starting WebSocket server on ws://{ws_host}:{ws_port}")
    ws_server = await websockets.serve(
        ws_handler, ws_host, ws_port, **_ws_server_options())

    logger.info(f"Starting Health HTTP server on http://{http_host}:{http_port}/health")
    app = web.Application(middlewares=[_no_cache_middleware])
    app.router.add_get('/health', health_handler)
    app.router.add_static('/', DISPLAY_DIR, show_index=True)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, http_host, http_port)
    await site.start()

    logger.info(f"Serving display files from {DISPLAY_DIR} on http://{http_host}:{http_port}/")

    _server_ready = True
    await asyncio.Future()


def run_server_thread():
    """Entry point for the thread running the asyncio event loop."""
    global _server_ready
    try:
        asyncio.run(start_servers())
    finally:
        _server_ready = False


def clear_display():
    """Broadcast a clear action to all connected clients and reset state."""
    if _server_loop is None:
        return

    for oid in connected_clients:
        current_display_state[oid] = {"action": "clear"}

    payload = json.dumps({"action": "clear"})
    for oid, clients in connected_clients.items():
        if clients:
            asyncio.run_coroutine_threadsafe(
                asyncio.gather(*[c.send(payload) for c in clients], return_exceptions=True),
                _server_loop,
            )
