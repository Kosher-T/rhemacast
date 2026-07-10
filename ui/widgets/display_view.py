"""
ui/widgets/display_view.py

QWebEngineView wrapper that renders verses using the same HTML/CSS/JS as OBS.
Live mode connects to WebSocket; Preview mode receives content via JS injection.
"""

import json
import logging

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

logger = logging.getLogger(__name__)

_DISPLAY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RhemaCast</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html {
    width: 1920px; height: 1080px; overflow: hidden;
    background: #000;
}
body {
    width: 1920px; height: 1080px; overflow: hidden;
    background: #000;
    font-family: 'Inter', sans-serif;
    display: flex; align-items: flex-end; justify-content: center;
    padding-bottom: 80px;
    transform-origin: 0 0;
}
#container {
    max-width: var(--rc-max-width, 80%);
    min-width: var(--rc-min-width, 60%);
    padding: var(--rc-padding, 40px);
    border-radius: var(--rc-border-radius, 24px);
    background: var(--rc-container-bg, rgba(15, 23, 42, 0.6));
    backdrop-filter: var(--rc-backdrop-filter, blur(16px));
    -webkit-backdrop-filter: var(--rc-backdrop-filter, blur(16px));
    border: var(--rc-container-border, 1px solid rgba(255, 255, 255, 0.1));
    box-shadow: var(--rc-container-shadow, 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.05) inset);
    transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    opacity: 1; transform: translateY(0) scale(1);
}
#container.hidden {
    opacity: 0; transform: translateY(40px) scale(0.98); pointer-events: none;
}
#verse-text {
    font-size: var(--rc-text-size, 2.5rem);
    font-weight: var(--rc-text-weight, 800);
    line-height: var(--rc-text-line-height, 1.4);
    color: var(--rc-text-color, #f8fafc);
    text-align: center;
    text-shadow: var(--rc-text-shadow, 0 4px 12px rgba(0, 0, 0, 0.4));
    margin-bottom: var(--rc-text-margin-bottom, 24px);
    letter-spacing: var(--rc-text-letter-spacing, -0.02em);
}
#verse-ref {
    font-size: var(--rc-ref-size, 1.5rem);
    font-weight: var(--rc-ref-weight, 600);
    color: var(--rc-ref-color, #94a3b8);
    text-align: center;
    text-transform: var(--rc-ref-text-transform, uppercase);
    letter-spacing: var(--rc-ref-letter-spacing, 0.1em);
}
#verse-ref-text { font-size: inherit; font-weight: inherit; color: inherit; }
#verse-ref-translation {
    font-size: inherit; font-weight: inherit;
    color: var(--rc-translation-color, #64748b);
    margin-left: var(--rc-translation-margin-left, 8px);
}
</style>
</head>
<body>
<div id="container" class="hidden">
    <div id="verse-content">
        <h1 id="verse-text"></h1>
        <p id="verse-ref">
            <span id="verse-ref-text"></span>
            <span id="verse-ref-translation"></span>
        </p>
    </div>
</div>
<script>
const container = document.getElementById("container");
const verseText = document.getElementById("verse-text");
const verseRefText = document.getElementById("verse-ref-text");
const verseRefTranslation = document.getElementById("verse-ref-translation");

let socket = null;
let isConnecting = false;

function connect() {
    if (isConnecting || (socket && socket.readyState === WebSocket.OPEN)) return;
    isConnecting = true;
    socket = new WebSocket("ws://127.0.0.1:8765");
    socket.onopen = () => { isConnecting = false; };
    socket.onmessage = (e) => {
        try { handlePayload(JSON.parse(e.data)); } catch(err) {}
    };
    socket.onclose = () => {
        isConnecting = false; socket = null;
        setTimeout(connect, 2000);
    };
    socket.onerror = () => { socket.close(); };
}

function applyTheme(theme) {
    if (!theme) return;
    const root = document.documentElement;
    const c = theme.container || {};
    const t = theme.text || {};
    const r = theme.reference || {};
    const tr = theme.translation || {};
    if (c.background)    root.style.setProperty("--rc-container-bg", c.background);
    if (c.border)        root.style.setProperty("--rc-container-border", c.border);
    if (c.border_radius) root.style.setProperty("--rc-border-radius", c.border_radius);
    if (c.box_shadow)    root.style.setProperty("--rc-container-shadow", c.box_shadow);
    if (c.backdrop_filter) root.style.setProperty("--rc-backdrop-filter", c.backdrop_filter);
    if (c.padding)       root.style.setProperty("--rc-padding", c.padding);
    if (c.max_width)     root.style.setProperty("--rc-max-width", c.max_width);
    if (c.min_width)     root.style.setProperty("--rc-min-width", c.min_width);
    if (t.color)         root.style.setProperty("--rc-text-color", t.color);
    if (t.size)          root.style.setProperty("--rc-text-size", t.size);
    if (t.weight)        root.style.setProperty("--rc-text-weight", t.weight);
    if (t.line_height)   root.style.setProperty("--rc-text-line-height", t.line_height);
    if (t.text_shadow)   root.style.setProperty("--rc-text-shadow", t.text_shadow);
    if (t.letter_spacing) root.style.setProperty("--rc-text-letter-spacing", t.letter_spacing);
    if (t.margin_bottom) root.style.setProperty("--rc-text-margin-bottom", t.margin_bottom);
    if (r.color)         root.style.setProperty("--rc-ref-color", r.color);
    if (r.size)          root.style.setProperty("--rc-ref-size", r.size);
    if (r.weight)        root.style.setProperty("--rc-ref-weight", r.weight);
    if (r.text_transform) root.style.setProperty("--rc-ref-text-transform", r.text_transform);
    if (r.letter_spacing) root.style.setProperty("--rc-ref-letter-spacing", r.letter_spacing);
    if (tr.color)        root.style.setProperty("--rc-translation-color", tr.color);
    if (tr.margin_left)  root.style.setProperty("--rc-translation-margin-left", tr.margin_left);
}

function handlePayload(data) {
    if (data.action === "clear") {
        container.classList.add("hidden");
        return;
    }
    if (data.action === "display") {
        if (data.text) verseText.innerHTML = data.text;
        if (data.reference) {
            verseRefText.innerHTML = data.reference;
        } else if (data.book && data.chapter && data.verse) {
            verseRefText.innerHTML = data.book + " " + data.chapter + ":" + data.verse;
        }
        if (data.translation) verseRefTranslation.innerHTML = data.translation;
        if (!data.reference && !data.translation && data.ref) {
            const m = data.ref.match(/^\[([^\]]+)\]\s*(.+)$/);
            if (m) { verseRefTranslation.innerHTML = m[1]; verseRefText.innerHTML = m[2]; }
            else { verseRefText.innerHTML = data.ref; }
        }
        if (data.theme_data) { applyTheme(data.theme_data); document.body.className = ""; }
        else if (data.theme) { document.body.className = "theme-" + data.theme; }
        container.classList.remove("hidden");
    }
}

// Scale 1920x1080 virtual canvas to fit actual widget size
const VIRTUAL_W = 1920, VIRTUAL_H = 1080;
function resizeCanvas() {
    const w = window.innerWidth, h = window.innerHeight;
    const scale = Math.min(w / VIRTUAL_W, h / VIRTUAL_H);
    document.body.style.transform = "scale(" + scale + ")";
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();
</script>
</body>
</html>"""


class DisplayView(QWebEngineView):
    """A web view that renders verses identically to the OBS display.

    live_mode=True:  connects to WebSocket (same data as OBS).
    live_mode=False: receives content via display_verse() / clear() calls.
    """

    def __init__(self, live_mode: bool = False, parent=None):
        super().__init__(parent)
        self._live_mode = live_mode

        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)

        self.setHtml(_DISPLAY_HTML, QUrl("http://localhost"))

        if live_mode:
            self.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool):
        if ok:
            self.page().runJavaScript("connect()")

    def display_verse(self, payload: dict):
        """Display a verse. payload matches the WS broadcast format:
        {action: "display", text, reference, translation, theme_data, ...}
        """
        self._run_payload(payload)

    def clear(self):
        """Hide the verse container with animation."""
        self._run_payload({"action": "clear"})

    def apply_theme(self, theme_data: dict):
        """Apply a theme without changing the displayed content."""
        js = "applyTheme(" + json.dumps(theme_data) + ")"
        self.page().runJavaScript(js)

    def _run_payload(self, payload: dict):
        """Execute handlePayload() with the given payload in the page."""
        js = "handlePayload(" + json.dumps(payload) + ")"
        self.page().runJavaScript(js)
