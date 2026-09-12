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
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html {
    width: 1920px; height: 1080px; overflow: hidden;
    background: #000;
}
body {
    width: 1920px; height: 1080px; overflow: hidden;
    background: #000;
    font-family: var(--rc-text-font-family, 'Nunito'), sans-serif;
    display: flex;
    align-items: var(--rc-vertical-align, flex-end);
    justify-content: center;
    padding-bottom: var(--rc-padding-bottom, 80px);
    transform-origin: 0 0;
}
#container {
    max-width: var(--rc-max-width, 80%);
    min-width: var(--rc-min-width, 60%);
    width: var(--rc-width, auto);
    height: var(--rc-height, auto);
    padding: var(--rc-padding, 40px);
    border-radius: var(--rc-border-radius, 24px);
    background: var(--rc-container-bg, rgba(15, 23, 42, 0.6));
    backdrop-filter: var(--rc-backdrop-filter, blur(16px));
    -webkit-backdrop-filter: var(--rc-backdrop-filter, blur(16px));
    border: var(--rc-container-border, 1px solid rgba(255, 255, 255, 0.1));
    box-shadow: var(--rc-container-shadow, 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.05) inset);

    display: var(--rc-container-display, block);
    flex-direction: var(--rc-container-flex-direction, column);
    justify-content: var(--rc-container-justify-content, flex-start);
    align-items: var(--rc-container-align-items, stretch);

    transition: none;
    opacity: 1; transform: translateY(0) scale(1);
}
#container.hidden {
    opacity: 0; transform: translateY(40px) scale(0.98); pointer-events: none;
}
#verse-text {
    font-family: var(--rc-text-font-family, 'Nunito'), sans-serif;
    font-size: var(--rc-text-size, 2.5rem);
    font-weight: var(--rc-text-weight, 700);
    font-style: var(--rc-text-font-style, normal);
    line-height: var(--rc-text-line-height, 1.2);
    color: var(--rc-text-color, #f8fafc);
    text-align: var(--rc-text-align, center);
    text-transform: var(--rc-text-transform, none);
    text-decoration: var(--rc-text-decoration, none);
    direction: var(--rc-text-direction, ltr);
    -webkit-text-stroke: var(--rc-text-outline, 0 transparent);
    text-shadow: var(--rc-text-shadow, 0 4px 12px rgba(0, 0, 0, 0.4));
    margin-bottom: var(--rc-text-margin-bottom, 24px);
    letter-spacing: var(--rc-text-letter-spacing, -0.01em);
    min-font-size: var(--rc-text-min-size, 4px);
    max-font-size: var(--rc-text-max-size, 300px);
}
.verse-num {
    font-family: var(--rc-verse-num-font-family, inherit);
    color: var(--rc-verse-num-color, inherit);
    font-size: 0.6em;
    font-weight: 700;
    opacity: 0.7;
    vertical-align: top;
    margin-right: 0.15em;
    line-height: 1;
}
#verse-ref {
    font-family: var(--rc-ref-font-family, 'DM Sans'), sans-serif;
    font-size: var(--rc-ref-size, 1.5rem);
    font-weight: var(--rc-ref-weight, 500);
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
const verseRef = document.getElementById("verse-ref");
const verseRefText = document.getElementById("verse-ref-text");
const verseRefTranslation = document.getElementById("verse-ref-translation");
let _fontsReady = false;
document.fonts.load("700 16px Nunito").then(() => { _fontsReady = true; });

// Inline run markup: [words (k=v; k=v)] → <span>. Payloads arrive
// HTML-escaped by sanitize_payload(); conversion happens here at render
// time (same contract as display/display.js — keep the two in sync).
const _INLINE_TRUE = new Set(["true", "1", "yes"]);
const _INLINE_FALSE = new Set(["false", "0", "no"]);
const _INLINE_KEYS = new Set(["size", "bold", "color", "italics", "case",
    "underline", "strike", "align", "spacing", "super", "sub",
    "outline", "dir", "hr", "font"]);

function _parseInlineColor(value) {
    const m = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec((value || "").trim());
    if (!m) return null;
    let c = m[1];
    if (c.length === 3) c = c.split("").map(ch => ch + ch).join("");
    return "#" + c.toLowerCase();
}

function parseInlineParams(raw) {
    const params = {};
    let found = false;
    for (const seg of (raw || "").split(";")) {
        const s = seg.trim();
        if (!s) continue;
        const eq = s.indexOf("=");
        if (eq < 0) continue;
        const key = s.slice(0, eq).trim().toLowerCase();
        const value = s.slice(eq + 1);
        if (!_INLINE_KEYS.has(key)) continue;
        if (key === "size") {
            const n = parseInt(value, 10);
            if (!isNaN(n)) { params.size_nominal = n; found = true; }
        } else if (key === "bold" || key === "italics") {
            const v = value.trim().toLowerCase();
            if (_INLINE_TRUE.has(v)) { params[key] = true; found = true; }
            else if (_INLINE_FALSE.has(v)) { params[key] = false; found = true; }
        } else if (key === "color") {
            const c = _parseInlineColor(value);
            if (c) { params.color = c; found = true; }
        } else if (key === "case") {
            const v = value.trim().toLowerCase();
            if (v === "upper" || v === "lower" || v === "origin") {
                params.case = v; found = true;
            }
        } else if (key === "underline" || key === "strike" || key === "super" || key === "sub" || key === "hr") {
            const v = value.trim().toLowerCase();
            if (_INLINE_TRUE.has(v)) { params[key] = true; found = true; }
            else if (_INLINE_FALSE.has(v)) { params[key] = false; found = true; }
        } else if (key === "align") {
            const v = value.trim().toLowerCase();
            if (v === "left" || v === "center" || v === "right" || v === "justify") { params.align = v; found = true; }
        } else if (key === "dir") {
            const v = value.trim().toLowerCase();
            if (v === "rtl" || v === "ltr") { params.dir = v; found = true; }
        } else if (key === "spacing") {
            const n = parseFloat(value);
            if (!isNaN(n) && n >= 0.5 && n <= 3.0) { params.spacing = n; found = true; }
        } else if (key === "outline") {
            const c = _parseInlineColor(value);
            if (c) { params.outline = c; found = true; }
        } else if (key === "font") {
            const v = (value || "").replace(/[;()\[\]"']/g, "").trim();
            if (v && v.length <= 60) { params.font = v; found = true; }
        }
    }
    return found ? params : null;
}

function spanStyle(p) {
    const styles = [];
    if (p.color) styles.push("color:" + p.color);
    if (p.size_nominal != null) styles.push("font-size:" + p.size_nominal + "px");
    if (p.bold === true) styles.push("font-weight:700");
    else if (p.bold === false) styles.push("font-weight:400");
    if (p.italics === true) styles.push("font-style:italic");
    else if (p.italics === false) styles.push("font-style:normal");
    if (p.case === "upper") styles.push("text-transform:uppercase");
    else if (p.case === "lower") styles.push("text-transform:lowercase");
    else if (p.case === "origin") styles.push("text-transform:none");
    const deco = [];
    if (p.underline === true) deco.push("underline");
    if (p.strike === true) deco.push("line-through");
    if (deco.length) styles.push("text-decoration:" + deco.join(" "));
    else if (p.underline === false || p.strike === false) styles.push("text-decoration:none");
    if (p.align) styles.push("display:inline-block;width:100%;text-align:" + p.align);
    if (p.spacing != null) styles.push("line-height:" + p.spacing);
    if (p.outline) styles.push("-webkit-text-stroke:1px " + p.outline);
    if (p.dir) styles.push("direction:" + p.dir + ";unicode-bidi:embed");
    if (p.font) styles.push("font-family:'" + String(p.font).replace(/'/g, "") + "'");
    return styles.join(";");
}

function renderInlineColors(text) {
    const raw = text || "";
    const runRe = /\[([^\[\]]+?)(?:\s*\(([^()]*)\))?\]/g;
    let out = "", last = 0, m;
    while ((m = runRe.exec(raw)) !== null) {
        // Bare \n markers outside brackets convert straight to breaks.
        out += raw.slice(last, m.index).replace(/\\n/g, "<br/>");
        const runText = m[1], runParams = m[2];
        if (runParams === undefined) {
            if (runText.trim() === "\\n") {
                out += '<span style=""><br/></span>';  // bare [\n] gap
            } else {
                out += m[0];  // literal — keep brackets as typed
            }
        } else {
            const parsed = parseInlineParams(runParams);
            if (parsed) {
                if (parsed.hr === true) {
                    out += '<div style="border-top:2px solid currentColor;margin:8px 0"></div>';
                } else {
                    const disp = runText.trim();
                    let inner = disp;
                    if (parsed.super === true) inner = "<sup>" + disp + "</sup>";
                    else if (parsed.sub === true) inner = "<sub>" + disp + "</sub>";
                    if (disp === "" || disp === "\\n") {
                        out += '<span style="' + spanStyle(parsed) + '"><br/></span>';
                    } else {
                        out += '<span style="' + spanStyle(parsed) + '">' + inner + '</span>';
                    }
                }
            } else {
                const legacyText = /^(.*):\s*$/.exec(runText);
                const legacyHex = _parseInlineColor(runParams);
                if (legacyText && legacyHex) {
                    out += '<span style="color:' + legacyHex + '">' + legacyText[1] + '</span>';
                } else {
                    out += m[0];
                }
            }
        }
        last = m.index + m[0].length;
    }
    out += raw.slice(last).replace(/\\n/g, "<br/>");
    return out.replace(/\r?\n/g, "<br/>");
}

function resetTheme() {
    const root = document.documentElement;
    const props = [
        "--rc-container-bg", "--rc-container-border", "--rc-border-radius",
        "--rc-container-shadow", "--rc-backdrop-filter", "--rc-padding",
        "--rc-max-width", "--rc-min-width", "--rc-width", "--rc-height",
        "--rc-container-display", "--rc-container-flex-direction",
        "--rc-container-justify-content", "--rc-container-align-items",
        "--rc-vertical-align", "--rc-padding-bottom",
        "--rc-text-color", "--rc-text-size", "--rc-text-weight",
        "--rc-text-line-height", "--rc-text-shadow", "--rc-text-letter-spacing",
        "--rc-text-margin-bottom", "--rc-text-min-size", "--rc-text-max-size",
        "--rc-text-font-family", "--rc-text-transform", "--rc-text-align",
        "--rc-text-font-style", "--rc-text-decoration", "--rc-text-direction",
        "--rc-text-outline",
        "--rc-ref-color", "--rc-ref-size", "--rc-ref-weight",
        "--rc-ref-text-transform", "--rc-ref-letter-spacing",
        "--rc-ref-font-family",
        "--rc-translation-color", "--rc-translation-margin-left",
        "--rc-verse-num-color", "--rc-verse-num-font-family"
    ];
    props.forEach(p => root.style.removeProperty(p));
}

function applyTheme(theme, slideFormat) {
    if (!theme) return;
    resetTheme();
    const root = document.documentElement;
    const c = theme.container || {};
    const t = theme.text || {};
    const r = theme.reference || {};
    const tr = theme.translation || {};
    const b = theme.body || {};

    if (c.background)    root.style.setProperty("--rc-container-bg", c.background);
    if (c.border)        root.style.setProperty("--rc-container-border", c.border);
    if (c.border_radius) root.style.setProperty("--rc-border-radius", c.border_radius);
    if (c.box_shadow)    root.style.setProperty("--rc-container-shadow", c.box_shadow);
    if (c.backdrop_filter) root.style.setProperty("--rc-backdrop-filter", c.backdrop_filter);
    if (c.padding)       root.style.setProperty("--rc-padding", c.padding);
    if (c.max_width)     root.style.setProperty("--rc-max-width", c.max_width);
    if (c.min_width)     root.style.setProperty("--rc-min-width", c.min_width);
    if (c.width)         root.style.setProperty("--rc-width", c.width);
    if (c.height)        root.style.setProperty("--rc-height", c.height);
    if (c.display)       root.style.setProperty("--rc-container-display", c.display);
    if (c.flex_direction) root.style.setProperty("--rc-container-flex-direction", c.flex_direction);
    if (c.justify_content) root.style.setProperty("--rc-container-justify-content", c.justify_content);
    if (c.align_items)   root.style.setProperty("--rc-container-align-items", c.align_items);

    if (b.vertical_align) root.style.setProperty("--rc-vertical-align", b.vertical_align);
    if (b.padding_bottom) root.style.setProperty("--rc-padding-bottom", b.padding_bottom);

    if (t.color)         root.style.setProperty("--rc-text-color", t.color);
    if (t.size)          root.style.setProperty("--rc-text-size", t.size);
    if (t.weight)        root.style.setProperty("--rc-text-weight", t.weight);
    if (t.line_height)   root.style.setProperty("--rc-text-line-height", t.line_height);
    if (t.text_shadow)   root.style.setProperty("--rc-text-shadow", t.text_shadow);
    if (t.letter_spacing) root.style.setProperty("--rc-text-letter-spacing", t.letter_spacing);
    if (t.margin_bottom) root.style.setProperty("--rc-text-margin-bottom", t.margin_bottom);
    if (t.min_size)      root.style.setProperty("--rc-text-min-size", t.min_size);
    if (t.max_size)      root.style.setProperty("--rc-text-max-size", t.max_size);
    if (t.font_family)   root.style.setProperty("--rc-text-font-family", t.font_family);
    if (t.text_transform) root.style.setProperty("--rc-text-transform", t.text_transform);
    if (t.text_align)   root.style.setProperty("--rc-text-align", t.text_align);

    // Deck-level slide format overrides theme text (cascade: theme < deck).
    const f = slideFormat || {};
    if (f.color) root.style.setProperty("--rc-text-color", f.color);
    if (f.size_nominal != null) root.style.setProperty("--rc-text-size", f.size_nominal + "px");
    if (f.size_min != null) root.style.setProperty("--rc-text-min-size", f.size_min + "px");
    if (f.size_max != null) root.style.setProperty("--rc-text-max-size", f.size_max + "px");
    if (f.bold === true) root.style.setProperty("--rc-text-weight", "800");
    else if (f.bold === false) root.style.setProperty("--rc-text-weight", "400");
    if (f.italics === true) root.style.setProperty("--rc-text-font-style", "italic");
    else if (f.italics === false) root.style.setProperty("--rc-text-font-style", "normal");
    if (f.case === "upper") root.style.setProperty("--rc-text-transform", "uppercase");
    else if (f.case === "lower") root.style.setProperty("--rc-text-transform", "lowercase");
    else if (f.case === "origin") root.style.setProperty("--rc-text-transform", "none");
    const fdeco = [];
    if (f.underline === true) fdeco.push("underline");
    if (f.strike === true) fdeco.push("line-through");
    if (fdeco.length) root.style.setProperty("--rc-text-decoration", fdeco.join(" "));
    else if (f.underline === false || f.strike === false) root.style.setProperty("--rc-text-decoration", "none");
    if (f.align) root.style.setProperty("--rc-text-align", f.align);
    if (f.spacing != null) root.style.setProperty("--rc-text-line-height", String(f.spacing));
    if (f.dir) root.style.setProperty("--rc-text-direction", f.dir);
    if (f.outline) root.style.setProperty("--rc-text-outline", "1px " + f.outline);
    else root.style.removeProperty("--rc-text-outline");
    if (f.font) root.style.setProperty("--rc-text-font-family", "'" + String(f.font).replace(/'/g, "") + "'");

    if (r.color)         root.style.setProperty("--rc-ref-color", r.color);
    if (r.size)          root.style.setProperty("--rc-ref-size", r.size);
    if (r.weight)        root.style.setProperty("--rc-ref-weight", r.weight);
    if (r.text_transform) root.style.setProperty("--rc-ref-text-transform", r.text_transform);
    if (r.letter_spacing) root.style.setProperty("--rc-ref-letter-spacing", r.letter_spacing);
    if (r.font_family)   root.style.setProperty("--rc-ref-font-family", r.font_family);

    if (tr.color)        root.style.setProperty("--rc-translation-color", tr.color);
    if (tr.margin_left)  root.style.setProperty("--rc-translation-margin-left", tr.margin_left);

    const vn = theme.verse_num || {};
    if (vn.color)        root.style.setProperty("--rc-verse-num-color", vn.color);
    if (vn.font_family)  root.style.setProperty("--rc-verse-num-font-family", vn.font_family);

    autoFitText();
}

function autoFitText() {
    const rootStyle = getComputedStyle(document.documentElement);
    const containerH = parseInt(rootStyle.getPropertyValue('--rc-height'));

    if (!containerH || isNaN(containerH)) {
        verseText.style.fontSize = '';
        return;
    }

    if (!verseText.textContent.trim()) return;

    // Get min/max font size from theme
    const minFontSize = parseInt(rootStyle.getPropertyValue('--rc-text-min-size')) || 4;
    const maxFontSize = parseInt(rootStyle.getPropertyValue('--rc-text-max-size')) || 300;

    let lo = minFontSize, hi = maxFontSize;
    while (hi - lo > 0.5) {
        const mid = (lo + hi) / 2;
        verseText.style.fontSize = mid + 'px';

        const margin = parseInt(getComputedStyle(verseText).marginBottom) || 0;
        const totalH = verseText.offsetHeight + margin + verseRef.offsetHeight;

        if (totalH <= containerH) { lo = mid; } else { hi = mid; }
    }

    verseText.style.fontSize = Math.floor(lo) + 'px';
}

function extractVerseNumber(reference) {
    // Empty/blank references (e.g. slides with show_title off) carry no number
    if (!reference) return null;
    const match = reference.match(/(\d+:\d+)$/);
    if (match) {
        return match[1].split(':').pop(); // Get just the verse number
    }
    return null;
}

function handlePayload(data) {
    if (data.action === "clear") {
        container.classList.add("hidden");
        return;
    }
    if (data.action === "display") {
        // Update scripture text (inline [words: (#hex)] colors rendered here)
        if (data.text) {
            let verseTextContent = renderInlineColors(data.text);
            // Prepend verse number if reference is available
            const refText = data.reference || (data.book && data.chapter && data.verse 
                ? data.book + " " + data.chapter + ":" + data.verse 
                : null);
            const verseNum = extractVerseNumber(refText);
            if (verseNum) {
                verseTextContent = '<span class="verse-num">' + verseNum + '</span> ' + verseTextContent;
            }
            verseText.innerHTML = verseTextContent;
        }
        
        // Update reference and translation as separate elements.
        // Blank fields CLEAR the line: a slide with show_title off must not
        // leave the previous verse's reference stale on screen.
        if (data.reference) {
            verseRefText.innerHTML = data.reference;
        } else if (data.book && data.chapter && data.verse) {
            verseRefText.innerHTML = data.book + " " + data.chapter + ":" + data.verse;
        } else if (data.ref) {
            // Legacy: if only ref is provided (no reference/translation), parse it
            const m = data.ref.match(/^\[([^\]]+)\]\s*(.+)$/);
            if (m) { verseRefTranslation.innerHTML = m[1]; verseRefText.innerHTML = m[2]; }
            else { verseRefText.innerHTML = data.ref; }
        } else {
            verseRefText.innerHTML = "";
        }

        if (data.translation) {
            verseRefTranslation.innerHTML = data.translation;
        } else if (!data.ref) {
            verseRefTranslation.innerHTML = "";
        }
        
        if (data.theme_data) { applyTheme(data.theme_data, data.slide_format); document.body.className = ""; }
        else if (data.theme) { document.body.className = "theme-" + data.theme; }
        function _showContainer() {
            container.classList.remove("hidden");
            autoFitText();
        }
        if (_fontsReady) { _showContainer(); }
        else { document.fonts.ready.then(_showContainer); }
    }
}

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
        self._page_ready = False
        self._pending_payload = None

        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)

        self.setHtml(_DISPLAY_HTML, QUrl("http://localhost"))
        self.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool):
        self._page_ready = ok
        if ok and self._live_mode:
            self.page().runJavaScript("connect()")
        if ok and self._pending_payload is not None:
            payload = self._pending_payload
            self._pending_payload = None
            self._run_payload(payload)

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
        if not self._page_ready:
            return
        js = "applyTheme(" + json.dumps(theme_data) + ")"
        self.page().runJavaScript(js)

    def _run_payload(self, payload: dict):
        """Execute handlePayload() with the given payload in the page."""
        if not self._page_ready:
            self._pending_payload = payload
            return
        js = "handlePayload(" + json.dumps(payload) + ")"
        self.page().runJavaScript(js)
