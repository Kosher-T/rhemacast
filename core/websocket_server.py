"""
core/websocket_server.py

WebSocket server for broadcasting display events to OBS Browser Sources
and an optional HTTP health endpoint.
"""

import asyncio
import html
import json
import logging
from typing import Set, Dict, Any

import websockets
from websockets.server import WebSocketServerProtocol
from aiohttp import web

from .queues import queue_a, queue_b, db_write_queue, operator_queue

logger = logging.getLogger(__name__)

# State
connected_clients: Set[WebSocketServerProtocol] = set()
current_display_state: Dict[str, Any] = {"action": "clear"}

def get_connected_client_count() -> int:
    """Expose telemetry to UI thread."""
    return len(connected_clients)

def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Security: Sanitize all string fields in the payload to prevent XSS
    if the frontend renders them as HTML.
    """
    sanitized = {}
    for k, v in payload.items():
        if isinstance(v, str):
            # Escape HTML characters to prevent XSS injections
            sanitized[k] = html.escape(v)
        else:
            sanitized[k] = v
    return sanitized

async def broadcast_display(payload: Dict[str, Any]):
    """
    Broadcasts a sanitized payload to all connected WebSocket clients
    and updates the current display state.
    """
    global current_display_state
    
    sanitized = sanitize_payload(payload)
    current_display_state = sanitized
    
    if connected_clients:
        message = json.dumps(sanitized)
        # Use asyncio.gather to send concurrently to all connected clients
        await asyncio.gather(
            *[client.send(message) for client in connected_clients],
            return_exceptions=True
        )

async def ws_handler(websocket, path="/"):
    """Handles new WebSocket connections."""
    connected_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(connected_clients)}")
    
    try:
        # Instantly push current state on connect
        await websocket.send(json.dumps(current_display_state))
        
        # Keep connection open and wait for it to close
        async for _ in websocket:
            pass  # We don't expect or process messages from the client
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(connected_clients)}")

async def health_handler(request: web.Request) -> web.Response:
    """HTTP GET endpoint returning queue depths for remote monitoring."""
    status = {
        "status": "ok",
        "clients": len(connected_clients),
        "queue_depths": {
            "queue_a": queue_a.qsize(),
            "queue_b": queue_b.qsize(),
            "db_write_queue": db_write_queue.qsize(),
            "operator_queue": operator_queue.qsize(),
        }
    }
    return web.json_response(status)

async def start_servers():
    """Starts both the WebSocket and HTTP Health servers."""
    # SECURITY: Bind strictly to localhost (127.0.0.1) to reject remote connections
    ws_host = "127.0.0.1"
    ws_port = 8765
    
    http_host = "127.0.0.1"
    http_port = 8766

    logger.info(f"Starting WebSocket server on ws://{ws_host}:{ws_port}")
    # Setting max_size to prevent large payloads if a client somehow sends one
    ws_server = await websockets.serve(ws_handler, ws_host, ws_port, max_size=1024)

    logger.info(f"Starting Health HTTP server on http://{http_host}:{http_port}/health")
    app = web.Application()
    app.router.add_get('/health', health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, http_host, http_port)
    await site.start()
    
    # Run forever
    await asyncio.Future()

def run_server_thread():
    """Entry point for the thread running the asyncio event loop."""
    asyncio.run(start_servers())
