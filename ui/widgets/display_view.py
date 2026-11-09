import json
import logging
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

logger = logging.getLogger(__name__)

_DISPLAY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RhemaCast</title>
<script>window.__RC_PREVIEW = true;</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
/* Local Nunito (offline-first): variable weight 200-1000, bundled in
   display/fonts/. The Google Fonts <link> in display.html stays as a
   fallback for subsets not bundled here. */
@font-face {
    font-family: 'Nunito';
    font-style: normal;
    font-weight: 200 1000;
    font-display: swap;
    src: url('./fonts/nunito-latin.woff2') format('woff2'),
         url('./fonts/nunito-latin-ext.woff2') format('woff2');
}

/* Base Reset & Transparency for OBS */
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body, html {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: transparent !important; /* MUST be transparent for OBS overlay */
    font-family: var(--rc-text-font-family, 'Nunito'), sans-serif;
    display: flex;
    align-items: var(--rc-vertical-align, flex-end); /* Align to bottom for lower-thirds, center for reference */
    justify-content: center;
    padding-bottom: var(--rc-padding-bottom, 80px);
}

#stage {
    position: absolute;
    top: 0;
    left: 0;
    width: 1920px;
    height: 1080px;
    overflow: hidden;
    transform-origin: 0 0;
}

/* Glassmorphism Container — defaults, overridden by theme via JS */
#container, .rc-container {
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
    opacity: 1;
    transform: translateY(0) scale(1);
}

#container.hidden, .rc-container.hidden {
    opacity: 0 !important;
    visibility: hidden;
    transform: none;
    pointer-events: none;
}

/* Typography — defaults, overridden by theme via JS */
/* True outward outline.
   -webkit-text-stroke straddles the glyph outline, so half of it grows
   INWARD and eats the letterform (at 25px the word is unreadable). Painting
   a stroke-only copy BEHIND an opaque fill leaves only the outward half
   visible, and because fills always paint over the copies, a letter's
   outline ends up behind its neighbours' fills instead of over them.
   isolation:isolate keeps the copy from falling behind the page background
   (a bare z-index:-1 would paint it under the ancestor's background). */
.rc-oc {
    position: relative;
    isolation: isolate;
}
.rc-oc::before {
    content: attr(data-rc-oc);
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    color: transparent;
    -webkit-text-fill-color: transparent;
    /* The fill layer carries the shadow; this transparent stroke copy
       inherits text-shadow otherwise and would cast a second, darker one. */
    text-shadow: none;
    /* --rc-oc-stroke carries its own units ("0.65em #000"). A single
       self-describing value means a JS/CSS version mix can only ever show
       NO stroke, never a mis-scaled blob. */
    -webkit-text-stroke: var(--rc-oc-stroke, 0 transparent);
    z-index: -1;
    white-space: pre-wrap;
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

#verse-ref-text {
    font-size: inherit;
    font-weight: inherit;
    color: inherit;
}

#verse-ref-translation {
    font-size: inherit;
    font-weight: inherit;
    color: var(--rc-translation-color, #64748b);
    margin-left: var(--rc-translation-margin-left, 8px);
}

.rc-cursor {
    display: inline-block;
    vertical-align: baseline;
    font-family: inherit;
    font-size: inherit;
    line-height: 1;
    margin-left: 0.05em;
    animation: rc-blink 1s step-start infinite;
}

@keyframes rc-blink {
    50% { opacity: 0; }
}

</style>
</head>
<body>
<div id="stage">
    <div id="container" class="hidden" aria-live="polite" aria-atomic="true" role="status">
        <div id="verse-content">
            <h1 id="verse-text" aria-label="Verse text"></h1>
            <p id="verse-ref">
                <span id="verse-ref-text" aria-label="Verse reference"></span>
                <span id="verse-ref-translation" aria-label="Translation"></span>
            </p>
        </div>
        <div id="ct-text" class="rc-container" data-element="text" style="display:none;">
            <h1 id="verse-text-abs" aria-label="Verse text"></h1>
        </div>
        <div id="ct-reference" class="rc-container" data-element="reference" style="display:none;">
            <span id="verse-ref-text-abs" aria-label="Verse reference"></span>
        </div>
        <div id="ct-translation" class="rc-container" data-element="translation" style="display:none;">
            <span id="verse-ref-translation-abs" aria-label="Translation"></span>
        </div>
    </div>
</div>
<script>
let _fontsReady = false;
if (document.fonts && document.fonts.load) {
    document.fonts.load("700 16px Nunito").then(() => { _fontsReady = true; });
}
const WS_HOST = window.location.hostname || "127.0.0.1";
const OUTPUT_ID = new URLSearchParams(window.location.search).get("output") || "1";
const WS_URL = `ws://${WS_HOST}:8765?output=${OUTPUT_ID}`;
const RECONNECT_DELAY = 2000;

let socket = null;
let isConnecting = false;
let _prevPayload = null;
let _animStyleEl = null;

const stage = document.getElementById("stage");
const container = document.getElementById("container");
const verseText = document.getElementById("verse-text");
const verseRef = document.getElementById("verse-ref");
const verseRefText = document.getElementById("verse-ref-text");
const verseRefTranslation = document.getElementById("verse-ref-translation");

function connect() {
    if (isConnecting || (socket && socket.readyState === WebSocket.OPEN)) return;
    
    isConnecting = true;
    console.log("Attempting WebSocket connection...");
    
    socket = new WebSocket(WS_URL);
    
    socket.onopen = () => {
        console.log("WebSocket connected.");
        isConnecting = false;
    };
    
    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handlePayload(data);
        } catch (e) {
            console.error("Failed to parse WebSocket message:", e);
        }
    };
    
    socket.onclose = () => {
        console.log("WebSocket disconnected. Reconnecting in 2 seconds...");
        isConnecting = false;
        socket = null;
        setTimeout(connect, RECONNECT_DELAY);
    };
    
    socket.onerror = (err) => {
        console.error("WebSocket error observed:", err);
        socket.close();
    };
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
        "--rc-text-outline", "--rc-text-outline-value",
        "--rc-oc-stroke",
        "--rc-ref-color", "--rc-ref-size", "--rc-ref-weight",
        "--rc-ref-text-transform", "--rc-ref-letter-spacing",
        "--rc-ref-font-family",
        "--rc-translation-color", "--rc-translation-margin-left",
        "--rc-verse-num-color", "--rc-verse-num-font-family"
    ];
    props.forEach(p => root.style.removeProperty(p));
    // The outline layer is DOM state, not just variables: drop it too.
    if (typeof applyOutlineLayers === "function") applyOutlineLayers();
    if (container) {
        container.style.position = "";
        container.style.left = "";
        container.style.top = "";
        container.style.width = "";
        container.style.height = "";
        container.style.minWidth = "";
        container.style.maxWidth = "";
        container.style.minHeight = "";
        container.style.maxHeight = "";
        container.style.zIndex = "";
        container.style.opacity = "";
        container.style.overflow = "";
        container.style.gap = "";
        container.style.display = "";
        container.style.background = "";
        container.style.border = "";
        container.style.borderRadius = "";
        container.style.boxShadow = "";
        container.style.backdropFilter = "";
        ["Top", "Right", "Bottom", "Left"].forEach(side => {
            container.style["border" + side + "Width"] = "";
            container.style["border" + side + "Style"] = "";
            container.style["border" + side + "Color"] = "";
        });
    }
    const verseContent = document.getElementById("verse-content");
    if (verseContent && verseRef && verseText) {
        verseContent.appendChild(verseRef);
    }
    if (verseRef && verseRefTranslation && verseRefText) {
        verseRef.style.display = "";
        verseRef.style.flexDirection = "";
        verseRef.style.alignItems = "";
        verseRef.appendChild(verseRefTranslation);
    }
    if (verseText) verseText.style.display = "";
    if (verseRefText) verseRefText.style.display = "";
    if (verseRefTranslation) verseRefTranslation.style.display = "";
    if (typeof document !== "undefined" && document.querySelectorAll) {
        document.querySelectorAll(".rc-dynamic-container").forEach(el => el.remove());
    }
}

function _resolveLength(val, canvasExtent) {
    if (val == null || val === "auto" || val === "none") return null;
    if (typeof val === "number") return val;
    const s = String(val).trim();
    if (s.endsWith("%")) {
        const num = parseFloat(s);
        return isNaN(num) ? null : (num / 100) * canvasExtent;
    }
    if (s.endsWith("px")) {
        const num = parseFloat(s);
        return isNaN(num) ? null : num;
    }
    const num = parseFloat(s);
    return isNaN(num) ? null : num;
}

function _applyBorder(el, border) {
    // §4.2.1: the base border is one shorthand and each authored side
    // overrides it. Re-setting the shorthand every time also clears any
    // longhands a previous theme wrote, so nothing leaks between containers.
    if (!el || !el.style || border == null) return;
    if (border === "none") {
        el.style.border = "none";
        return;
    }
    if (typeof border === "string") {
        el.style.border = border;
        return;
    }
    if (typeof border !== "object") return;
    const baseWidth = border.width != null ? border.width : 1;
    const baseStyle = border.style || "solid";
    const baseColor = border.color != null ? border.color : "#ffffff";
    el.style.border = baseWidth + "px " + baseStyle + " " + baseColor;
    const sides = border.sides;
    if (!sides || typeof sides !== "object") return;
    ["Top", "Right", "Bottom", "Left"].forEach(side => {
        const spec = sides[side.toLowerCase()];
        if (!spec || typeof spec !== "object") return;
        const width = spec.width != null ? spec.width : baseWidth;
        const style = spec.style || baseStyle;
        const color = spec.color != null ? spec.color : baseColor;
        el.style["border" + side + "Width"] = width + "px";
        el.style["border" + side + "Style"] = style;
        el.style["border" + side + "Color"] = color;
    });
}

function _computePosition(pos, width, height, canvasW, canvasH) {
    pos = pos || {};
    let anchor = pos.anchor || "center";
    if (!pos.anchor) {
        if (pos.top_left) anchor = "top_left";
        else if (pos.top_right) anchor = "top_right";
        else if (pos.bottom_left) anchor = "bottom_left";
        else if (pos.bottom_right) anchor = "bottom_right";
    }
    const hasX = pos.x != null;
    const hasY = pos.y != null;
    const x = _resolveLength(pos.x != null ? pos.x : 0, canvasW);
    const y = _resolveLength(pos.y != null ? pos.y : 0, canvasH);
    const centeredX = (canvasW - width) / 2;
    const centeredY = (canvasH - height) / 2;

    if (anchor === "top_left") return { left: x, top: y };
    if (anchor === "top_right") return { left: canvasW - width - x, top: y };
    if (anchor === "bottom_left") return { left: x, top: canvasH - height - y };
    if (anchor === "bottom_right") return { left: canvasW - width - x, top: canvasH - height - y };
    if (anchor === "center") return { left: centeredX + x, top: centeredY + y };
    if (anchor === "top") return { left: hasX ? x : centeredX, top: y };
    if (anchor === "bottom") return { left: hasX ? x : centeredX, top: canvasH - height - y };
    if (anchor === "left") return { left: x, top: hasY ? y : centeredY };
    if (anchor === "right") return { left: canvasW - width - x, top: hasY ? y : centeredY };
    if (anchor === "fill") return { left: 0, top: 0, width: canvasW, height: canvasH };
    return { left: centeredX + x, top: centeredY + y };
}

function _isNewContainers(ct) {
    if (!ct || typeof ct !== "object") return false;
    if (Array.isArray(ct)) {
        return ct.some(v => v && typeof v === "object" &&
            (v.blocks || typeof v.text === "object" || typeof v.body === "object"));
    }
    return Object.values(ct).some(v => v && typeof v === "object" &&
        (v.blocks || typeof v.text === "object" || typeof v.body === "object"));
}

function themeContainer(theme, name) {
    const ct = theme && theme.containers;
    if (Array.isArray(ct)) {
        if (!ct.length) return {};
        if (name) {
            const found = ct.find(c => c && c.id === name);
            if (found) return found;
            console.warn("Container '" + name + "' not found — using first.");
        }
        return ct[0] || {};
    }
    if (!_isNewContainers(ct)) return {};
    const keys = Object.keys(ct);
    if (name && ct[name] && typeof ct[name] === "object") return ct[name];
    if (name) console.warn("Container '" + name + "' not found — using first.");
    return (keys.length && typeof ct[keys[0]] === "object") ? ct[keys[0]] : {};
}

function _getContainerBlocks(c) {
    if (!c || typeof c !== "object") return {};
    const blocks = (c.blocks && typeof c.blocks === "object") ? c.blocks : {};
    return {
        body: blocks.body || c.body || {},
        text: blocks.text || c.text || {},
        reference: blocks.reference || blocks.title || c.reference || c.title || {},
        translation: blocks.translation || c.translation || {},
        verse_num: blocks.verse_num || c.verse_num || {},
    };
}

function _authoredBlock(c, name) {
    // Absence is meaningful once a theme splits into containers: a citation
    // panel that declares only `reference` must not inherit the verse.
    // `_getContainerBlocks` fills every key with `{}`, so presence has to be
    // read from the raw container rather than from the normalized map.
    if (!c || typeof c !== "object") return null;
    const blocks = (c.blocks && typeof c.blocks === "object") ? c.blocks : null;
    let b = blocks ? blocks[name] : null;
    if (b == null) b = c[name];
    if (b == null && name === "reference") {
        b = (blocks && blocks.title) || c.title;
    }
    return (b && typeof b === "object") ? b : null;
}

let _currentTheme = null;
let _currentContainers = [];

function applyCanvasFit(canvas) {
    const stg = document.getElementById("stage");
    if (!stg) return;
    const cw = (canvas && canvas.width) || 1920;
    const ch = (canvas && canvas.height) || 1080;
    // The in-app preview always fits the panel: it is a viewport, not the
    // OBS output surface, and v1 themes keep canvas.fit:"none" so OBS never
    // rescales them. The preview sets window.__RC_PREVIEW before load.
    const preview = typeof window !== "undefined" && window.__RC_PREVIEW === true;
    const fit = preview ? "contain" : ((canvas && canvas.fit) || "contain");
    const bg = (canvas && canvas.background) || "transparent";
    stg.style.width = cw + "px";
    stg.style.height = ch + "px";
    stg.style.background = bg;

    if (fit === "contain" && typeof window !== "undefined" && window.innerWidth && window.innerHeight) {
        const scale = Math.min(window.innerWidth / cw, window.innerHeight / ch);
        const left = (window.innerWidth - cw * scale) / 2;
        const top = (window.innerHeight - ch * scale) / 2;
        stg.style.transformOrigin = "0 0";
        stg.style.transform = "translate(" + left + "px, " + top + "px) scale(" + scale + ")";
    } else {
        stg.style.transform = "";
        stg.style.left = "0";
        stg.style.top = "0";
    }
}

if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("resize", function () {
        if (_currentTheme && _currentTheme.canvas) {
            applyCanvasFit(_currentTheme.canvas);
        }
    });
}

let _deckTextSize = null;

function applyTheme(theme, slideFormat) {
    if (!theme) return;
    _currentTheme = theme;
    resetTheme();
    const root = document.documentElement;

    if (theme.canvas) {
        applyCanvasFit(theme.canvas);
    }

    let containers = [];
    if (Array.isArray(theme.containers)) {
        containers = theme.containers.filter(c => c && typeof c === "object" && c.visible !== false)
                                     .sort((a, b) => (a.layer || 0) - (b.layer || 0));
    } else if (theme.containers && typeof theme.containers === "object" && _isNewContainers(theme.containers)) {
        containers = Object.values(theme.containers).filter(c => c && typeof c === "object" && c.visible !== false);
    }
    _currentContainers = containers;

    const cont = themeContainer(theme);
    const blocks = _getContainerBlocks(cont);
    const isCont = cont && (cont.blocks || cont.position || cont.id || typeof cont.text === "object" || typeof cont.body === "object");
    const c = isCont ? cont : (theme.container || {});
    const t = (blocks.text && Object.keys(blocks.text).length > 0) ? blocks.text : (theme.text || {});
    const r = (blocks.reference && Object.keys(blocks.reference).length > 0) ? blocks.reference : (theme.reference || {});
    const tr = (blocks.translation && Object.keys(blocks.translation).length > 0) ? blocks.translation : (theme.translation || {});
    const b = (blocks.body && Object.keys(blocks.body).length > 0) ? blocks.body : (theme.body || {});

    const canvasW = (theme.canvas && theme.canvas.width) || 1920;
    const canvasH = (theme.canvas && theme.canvas.height) || 1080;

    // Container
    if (c.background)        root.style.setProperty("--rc-container-bg", c.background);
    if (c.border) {
        let bVal = c.border;
        if (typeof bVal === "object" && bVal) {
            const bw = bVal.width != null ? bVal.width : 1;
            bVal = bw + "px " + (bVal.style || "solid") + " " + (bVal.color || "#ffffff");
        }
        // "none" is a real value: leaving the variable unset would fall back
        // to the stylesheet's 1px glass border.
        if (bVal) root.style.setProperty("--rc-container-border", bVal);
    }
    // Per-side declarations cannot ride a single border custom property.
    _applyBorder(container, c.border);
    if (c.border_radius != null) {
        const br = _resolveLength(c.border_radius, canvasW);
        root.style.setProperty("--rc-border-radius", br != null ? (br + "px") : String(c.border_radius));
    } else if (typeof c.border === "object" && c.border && c.border.radius != null) {
        root.style.setProperty("--rc-border-radius", c.border.radius + "px");
    }
    if (c.box_shadow) {
        let bsVal = c.box_shadow;
        if (typeof bsVal === "object" && bsVal) {
            bsVal = (bsVal.inset ? "inset " : "") + (bsVal.x || 0) + "px " + (bsVal.y || 0) + "px " + (bsVal.blur || 0) + "px " + (bsVal.spread || 0) + "px " + (bsVal.color || "rgba(0,0,0,0.5)");
        }
        root.style.setProperty("--rc-container-shadow", bsVal);
    }
    if (c.backdrop_filter)   root.style.setProperty("--rc-backdrop-filter", c.backdrop_filter);
    if (c.padding)           root.style.setProperty("--rc-padding", c.padding);
    if (c.max_width != null) root.style.setProperty("--rc-max-width", typeof c.max_width === "number" ? (c.max_width + "px") : c.max_width);
    if (c.min_width != null) root.style.setProperty("--rc-min-width", typeof c.min_width === "number" ? (c.min_width + "px") : c.min_width);
    if (c.width != null)     root.style.setProperty("--rc-width", typeof c.width === "number" ? (c.width + "px") : c.width);
    if (c.height != null)    root.style.setProperty("--rc-height", typeof c.height === "number" ? (c.height + "px") : c.height);
    if (c.display)           root.style.setProperty("--rc-container-display", c.display);
    if (c.flex_direction)    root.style.setProperty("--rc-container-flex-direction", c.flex_direction);
    if (c.justify_content)   root.style.setProperty("--rc-container-justify-content", c.justify_content);
    if (c.align_items)       root.style.setProperty("--rc-container-align-items", c.align_items);

    container.style.position = "";
    container.style.left = "";
    container.style.top = "";
    if (c.position || (typeof c.x === "number" && typeof c.y === "number")) {
        let w = _resolveLength(c.width, canvasW);
        let h = _resolveLength(c.height, canvasH);
        if (w == null && c.min_width != null) w = _resolveLength(c.min_width, canvasW);
        if (h == null && c.min_height != null) h = _resolveLength(c.min_height, canvasH);
        if (w == null) w = canvasW;
        if (h == null) h = canvasH;

        if (c.position) {
            const p = _computePosition(c.position, w, h, canvasW, canvasH);
            container.style.position = "absolute";
            container.style.left = p.left + "px";
            container.style.top = p.top + "px";
            if (p.width) container.style.width = p.width + "px";
            if (p.height) container.style.height = p.height + "px";
        } else if (typeof c.x === "number" && typeof c.y === "number") {
            container.style.position = "absolute";
            container.style.left = c.x + "px";
            container.style.top = c.y + "px";
        }
    }
    if (c.layer != null) container.style.zIndex = c.layer;
    if (c.opacity != null) container.style.opacity = c.opacity;
    if (c.overflow) container.style.overflow = c.overflow;
    // Resolved v2 panels encode their height in min_height/max_height while
    // `height` stays "auto" (spec §4.2). The stylesheet only reads
    // --rc-width/--rc-height, so without these inline writes the panel
    // collapses to its content height (360px instead of the authored 860px).
    if (c.min_height != null) {
        const mh = _resolveLength(c.min_height, canvasH);
        container.style.minHeight = mh != null ? (mh + "px") : "";
    } else {
        container.style.minHeight = "";
    }
    if (c.max_height != null) {
        const mxh = _resolveLength(c.max_height, canvasH);
        container.style.maxHeight = mxh != null ? (mxh + "px") : "";
    } else {
        container.style.maxHeight = "";
    }

    // Body
    const valign = b.valign || (b.vertical_align ? (b.vertical_align.includes("start") ? "top" : b.vertical_align.includes("end") ? "bottom" : "center") : null);
    const jc = valign === "top" ? "flex-start" : valign === "bottom" ? "flex-end" : "center";
    if (valign) {
        root.style.setProperty("--rc-container-justify-content", jc);
        root.style.setProperty("--rc-vertical-align", jc);
    } else if (b.vertical_align) {
        root.style.setProperty("--rc-vertical-align", b.vertical_align);
    }
    if (b.gap != null) container.style.gap = b.gap + "px";
    if (b.padding_top != null || b.padding_bottom != null || b.padding_left != null || b.padding_right != null || b.padding != null) {
        const pt = (b.padding_top != null ? b.padding_top : b.padding) || 0;
        const pr = (b.padding_right != null ? b.padding_right : b.padding) || 0;
        const pb = (b.padding_bottom != null ? b.padding_bottom : b.padding) || 0;
        const pl = (b.padding_left != null ? b.padding_left : b.padding) || 0;
        root.style.setProperty("--rc-padding", `${pt}px ${pr}px ${pb}px ${pl}px`);
        root.style.setProperty("--rc-padding-bottom", `${pb}px`);
    } else if (b.padding_bottom) {
        root.style.setProperty("--rc-padding-bottom", b.padding_bottom);
    }

    // Resolved v2 themes carry no `container.display`/flex keys (those were
    // v1-only): the content stack is the flex box (spec §4.4). Without this
    // the container falls back to `display:block`, body.valign does nothing,
    // and every migrated theme loses its vertical centering.
    const isV2 = theme.schema_version === 2
        || (Array.isArray(theme.containers) && theme.containers.some(
            c2 => c2 && typeof c2 === "object"
                && (c2.blocks || typeof c2.body === "object")));
    const verseContentEl = document.getElementById("verse-content");
    if (isV2) {
        container.style.display = "flex";
        container.style.flexDirection = "column";
        container.style.justifyContent = jc;
        container.style.alignItems = "stretch";
        if (verseContentEl) {
            verseContentEl.style.display = "flex";
            verseContentEl.style.flexDirection = "column";
            verseContentEl.style.alignItems = "stretch";
            if (b.gap != null) verseContentEl.style.gap = b.gap + "px";
        }
    }

    // Text
    if (t.color)        root.style.setProperty("--rc-text-color", t.color);
    if (t.size != null) root.style.setProperty("--rc-text-size", typeof t.size === "number" ? (t.size + "px") : t.size);
    if (t.weight != null) root.style.setProperty("--rc-text-weight", String(t.weight));
    if (t.line_height != null) root.style.setProperty("--rc-text-line-height", String(t.line_height));
    const tOutline = _themeOutline(t);
    if (tOutline) root.style.setProperty("--rc-text-outline", tOutline);
    const tShadowRaw = String(t.text_shadow || "").trim();
    const shadowIsOutline = !!tOutline
        && _themeOutline({ text_shadow: tShadowRaw }) === tOutline;
    if (!shadowIsOutline) {
        if (tShadowRaw) {
            root.style.setProperty("--rc-text-shadow",
                _shadowIsNone(tShadowRaw) ? "none" : tShadowRaw);
        }
    }
    try { invalidateOutlines(); } catch (e) {}
    if (typeof applyOutlineLayers === "function") applyOutlineLayers();
    if (t.letter_spacing != null) root.style.setProperty("--rc-text-letter-spacing", typeof t.letter_spacing === "number" ? (t.letter_spacing + "px") : t.letter_spacing);
    if (t.margin_bottom != null) root.style.setProperty("--rc-text-margin-bottom", typeof t.margin_bottom === "number" ? (t.margin_bottom + "px") : t.margin_bottom);
    if (t.min_size != null)     root.style.setProperty("--rc-text-min-size", typeof t.min_size === "number" ? (t.min_size + "px") : t.min_size);
    if (t.max_size != null)     root.style.setProperty("--rc-text-max-size", typeof t.max_size === "number" ? (t.max_size + "px") : t.max_size);
    if (t.font_family)  root.style.setProperty("--rc-text-font-family", t.font_family);
    if (t.font_style)   root.style.setProperty("--rc-text-font-style", t.font_style);
    if (t.text_decoration) root.style.setProperty("--rc-text-decoration", t.text_decoration);
    if (t.text_transform) root.style.setProperty("--rc-text-transform", t.text_transform);
    if (t.text_align)   root.style.setProperty("--rc-text-align", t.text_align);
    if (t.visible === false && verseText) {
        verseText.style.display = "none";
    }

    // Deck-level slide format overrides (cascade: theme < deck).
    const f = slideFormat || {};
    if (slideFormat !== undefined) {
        _deckTextSize = (f.size_nominal != null) ? f.size_nominal : null;
    }
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
    const deckOutline = (f.outline && f.outline !== "none") ? f.outline
                        : (f.outline === "none" ? "none" : null);
    if (deckOutline) root.style.setProperty("--rc-text-outline-value", deckOutline);
    else root.style.removeProperty("--rc-text-outline-value");
    if (f.shadow === "none" || f.shadow === "off") {
        root.style.setProperty("--rc-text-shadow", "none");
    } else if (f.shadow) {
        const ds = _parseShadow(f.shadow);
        if (ds && ds !== "none") root.style.setProperty("--rc-text-shadow", _shadowRing(ds));
    }
    if (f.font) root.style.setProperty("--rc-text-font-family", "'" + String(f.font).replace(/'/g, "") + "'");

    // Reference
    if (r.color)        root.style.setProperty("--rc-ref-color", r.color);
    if (r.size != null) root.style.setProperty("--rc-ref-size", typeof r.size === "number" ? (r.size + "px") : r.size);
    if (r.weight != null) root.style.setProperty("--rc-ref-weight", String(r.weight));
    if (r.text_transform) root.style.setProperty("--rc-ref-text-transform", r.text_transform);
    if (r.letter_spacing != null) root.style.setProperty("--rc-ref-letter-spacing", typeof r.letter_spacing === "number" ? (r.letter_spacing + "px") : r.letter_spacing);
    if (r.font_family)  root.style.setProperty("--rc-ref-font-family", r.font_family);
    if (r.visible === false && verseRefText) {
        verseRefText.style.display = "none";
    }

    // Translation
    if (tr.color)       root.style.setProperty("--rc-translation-color", tr.color);
    if (tr.margin_left != null) root.style.setProperty("--rc-translation-margin-left", typeof tr.margin_left === "number" ? (tr.margin_left + "px") : tr.margin_left);
    if (tr.visible === false && verseRefTranslation) {
        verseRefTranslation.style.display = "none";
    }

    // Placement
    const verseContent = document.getElementById("verse-content");
    if (verseContent && verseRef && verseText) {
        if (r.position === "above_verse" && typeof verseContent.insertBefore === "function") {
            verseContent.insertBefore(verseRef, verseText);
        } else if (typeof verseContent.appendChild === "function") {
            verseContent.appendChild(verseRef);
        }
    }
    if (verseRef && verseRefTranslation && verseRefText) {
        if (tr.position === "left_of_reference" && typeof verseRef.insertBefore === "function") {
            verseRef.insertBefore(verseRefTranslation, verseRefText);
        } else if (tr.position === "above_reference") {
            verseRef.style.display = "flex";
            verseRef.style.flexDirection = "column-reverse";
            verseRef.style.alignItems = "center";
            if (typeof verseRef.appendChild === "function") verseRef.appendChild(verseRefTranslation);
        } else if (tr.position === "below_reference") {
            verseRef.style.display = "flex";
            verseRef.style.flexDirection = "column";
            verseRef.style.alignItems = "center";
            if (typeof verseRef.appendChild === "function") verseRef.appendChild(verseRefTranslation);
        } else {
            verseRef.style.display = "";
            verseRef.style.flexDirection = "";
            verseRef.style.alignItems = "";
            if (typeof verseRef.appendChild === "function") verseRef.appendChild(verseRefTranslation);
        }
    }

    // Verse number
    const vn = blocks.verse_num || theme.verse_num || {};
    if (vn.color)        root.style.setProperty("--rc-verse-num-color", vn.color);
    if (vn.font_family)  root.style.setProperty("--rc-verse-num-font-family", vn.font_family);

    autoFitText();
    _applyContainers(theme);
    // The first fit can run before the auto-height panel has its final box.
    // Refit once for v2 min_height panels so a long verse cannot grow the
    // frame off-stage.
    if (typeof requestAnimationFrame === "function" && _minHeightFitTarget()) {
        requestAnimationFrame(function () {
            if (_currentTheme === theme) autoFitText();
        });
    }
}

function extractVerseNumber(reference) {
    if (!reference) return null;
    const match = reference.match(/(\d+:\d+)$/);
    if (match) {
        return match[1].split(':').pop();
    }
    return null;
}

function fitOutlineLayers(containerH, minFontSize) {
    for (let i = 0; i < 8; i++) {
        const margin = parseInt(getComputedStyle(verseText).marginBottom) || 0;
        const refH = (typeof verseRef !== "undefined" && verseRef)
            ? verseRef.offsetHeight : 0;
        const totalH = verseText.offsetHeight + margin + refH;
        if (totalH <= containerH) return;
        const cur = parseFloat(verseText.style.fontSize) || minFontSize;
        const next = Math.max(minFontSize, Math.floor(cur * 0.9));
        if (next >= cur) return;
        verseText.style.fontSize = next + 'px';
        invalidateOutlines();
        applyOutlineLayers();
    }
}

function _minHeightFitTarget() {
    // §4.2 panels size themselves with min_height + height:auto. Reading the
    // rendered box here is circular: an overflowing verse grows the auto-height
    // panel, so the text always "fits" while the panel itself spills off-stage
    // (the clipped-verse bug). The authored limit is the fit target, minus the
    // panel's own padding and border, which are not available to the text.
    // v1 and migrated themes keep min_height 0 and never enter this branch.
    const theme = _currentTheme;
    if (!theme || theme.schema_version !== 2 || !container) return null;
    const c = themeContainer(theme);
    if (!c) return null;
    const canvasH = (theme.canvas && theme.canvas.height) || 1080;
    let limit = null;
    if (c.max_height != null) limit = _resolveLength(c.max_height, canvasH);
    if ((limit == null || limit <= 0) && c.min_height != null) {
        limit = _resolveLength(c.min_height, canvasH);
    }
    if (!limit || limit <= 0) return null;
    const cs = getComputedStyle(container);
    const pad = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0)
        + (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0);
    return Math.max(1, limit - pad);
}

function autoFitText() {
    const rootStyle = getComputedStyle(document.documentElement);
    let containerH = parseInt(rootStyle.getPropertyValue('--rc-height'));
    if (!containerH || isNaN(containerH)) {
        containerH = _minHeightFitTarget();
    } else if (_currentTheme && _currentTheme.schema_version === 2) {
        // A fixed-height v2 panel's text lives inside its padding; the fit
        // target is the content box, not the border box.
        const ccs = getComputedStyle(container);
        containerH = Math.max(1, containerH
            - (parseFloat(ccs.paddingTop) || 0)
            - (parseFloat(ccs.paddingBottom) || 0));
    }

    invalidateOutlines();
    if (!containerH || isNaN(containerH)) {
        verseText.style.fontSize = '';
        applyOutlineLayers();
        return;
    }

    if (!verseText.textContent.trim()) return;

    const minFontSize = parseInt(rootStyle.getPropertyValue('--rc-text-min-size')) || 4;
    let maxFontSize = parseInt(rootStyle.getPropertyValue('--rc-text-max-size')) || 300;
    if (_deckTextSize != null && _deckTextSize > 0) {
        maxFontSize = _deckTextSize;
    }
    let lo = minFontSize, hi = maxFontSize;
    if (_deckTextSize != null && _deckTextSize > 0) {
        verseText.style.fontSize = _deckTextSize + 'px';
        const margin = parseInt(getComputedStyle(verseText).marginBottom) || 0;
        const totalH = verseText.offsetHeight + margin + verseRef.offsetHeight;
        if (totalH <= containerH) {
            lo = hi = _deckTextSize;
        } else {
            hi = _deckTextSize;
            lo = Math.min(minFontSize, hi);
        }
    }
    while (hi - lo > 0.5) {
        const mid = (lo + hi) / 2;
        verseText.style.fontSize = mid + 'px';

        const margin = parseInt(getComputedStyle(verseText).marginBottom) || 0;
        const totalH = verseText.offsetHeight + margin + verseRef.offsetHeight;

        if (totalH <= containerH) { lo = mid; } else { hi = mid; }
    }

    verseText.style.fontSize = Math.floor(lo) + 'px';
    applyOutlineLayers();
}

let _activeContainers = null;

function _applyContainers(theme) {
    const ct = theme.containers;
    if (ct && typeof ct === "object" && (function () {
        if (Array.isArray(ct)) return true;
        for (const k of Object.keys(ct)) {
            const v = ct[k];
            if (v && typeof v === "object"
                && (v.blocks || typeof v.text === "object" || typeof v.body === "object")) return true;
        }
        return false;
    })()) return;
    const verseContent = document.getElementById("verse-content");
    const ctText = document.getElementById("ct-text");
    const ctRef = document.getElementById("ct-reference");
    const ctTrans = document.getElementById("ct-translation");
    if (!ctText || !ctRef || !ctTrans) return;

    if (!ct) {
        _activeContainers = null;
        if (verseContent) verseContent.style.display = "";
        ctText.style.display = "none";
        ctRef.style.display = "none";
        ctTrans.style.display = "none";
        container.style.position = "";
        container.style.width = "";
        container.style.height = "";
        container.style.left = "";
        container.style.top = "";
        return;
    }

    _activeContainers = ct;
    if (verseContent) verseContent.style.display = "none";

    container.style.position = "absolute";
    container.style.width = "1920px";
    container.style.height = "1080px";
    container.style.left = "0";
    container.style.top = "0";

    const t = theme.text || {};
    const r = theme.reference || {};
    const tr = theme.translation || {};

    _positionContainer(ctText, ct.text, t, "text");
    _positionContainer(ctRef, ct.reference, r, "reference");
    _positionContainer(ctTrans, ct.translation, tr, "translation");
}

function _positionContainer(el, pos, style, type) {
    if (!pos || pos.follows || pos.visible === false) {
        el.style.display = "none";
        return;
    }
    el.style.display = "block";
    el.style.position = "absolute";
    el.style.left = (pos.x - pos.width / 2) + "px";
    el.style.top = (pos.y - pos.height / 2) + "px";
    el.style.width = pos.width + "px";
    el.style.height = pos.height + "px";
    el.style.overflow = "hidden";

    const inner = el.firstElementChild;
    if (!inner) return;
    inner.style.width = "100%";
    inner.style.height = "100%";
    inner.style.display = "flex";
    inner.style.flexDirection = "column";
    inner.style.justifyContent = "center";
    inner.style.alignItems = "center";
    inner.style.textAlign = "center";

    if (type === "text") {
        inner.style.color = style.color || "#ffffff";
        inner.style.fontFamily = style.font_family || "'Nunito', sans-serif";
        inner.style.fontWeight = style.weight || 700;
        inner.style.lineHeight = style.line_height || "1.08";
        inner.style.letterSpacing = style.letter_spacing || "-0.02em";
        inner.style.textShadow = style.text_shadow || "";
        inner.style.padding = "20px";
    } else if (type === "reference") {
        inner.style.color = style.color || "#cccccc";
        inner.style.fontFamily = style.font_family || "'DM Sans', sans-serif";
        inner.style.fontWeight = style.weight || 500;
        inner.style.textTransform = style.text_transform || "uppercase";
        inner.style.letterSpacing = style.letter_spacing || "0.1em";
        inner.style.fontSize = style.size || "34px";
    } else if (type === "translation") {
        inner.style.color = style.color || "#999999";
        inner.style.fontSize = "16px";
    }
}

function _populateContainers(data) {
    if (!_activeContainers) return;
    const refText = data.reference || (data.book && data.chapter && data.verse
        ? data.book + " " + data.chapter + ":" + data.verse : "");
    const verseNum = extractVerseNumber(refText);

    const ctTextInner = document.querySelector("#ct-text > *");
    if (ctTextInner) {
        let html = renderInlineColors(data.text);
        if (verseNum) html = '<span class="verse-num">' + verseNum + '</span> ' + html;
        ctTextInner.innerHTML = html;
    }

    const ctRefInner = document.querySelector("#ct-reference > *");
    if (ctRefInner) ctRefInner.innerHTML = refText;

    const ctTransInner = document.querySelector("#ct-translation > *");
    if (ctTransInner) ctTransInner.innerHTML = data.translation || "";
}

function _panelFitTarget(el) {
    const cs = getComputedStyle(el);
    const pad = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
    return Math.max(1, el.clientHeight - pad);
}

function _fitPanelText(el, c) {
    // §4.2: every panel owns its own autosize. Without this the text renders
    // at the authored size and overflow hides it (a 76px verse measured 1067px
    // in a 780px panel and clipped on both edges).
    const t = _authoredBlock(c, "text");
    if (!t || t.autosize === false) return;
    const h1 = el.querySelector(".verse-text");
    if (!h1 || !h1.textContent.trim()) return;
    const canvasH = (_currentTheme && _currentTheme.canvas
        && _currentTheme.canvas.height) || 1080;
    const minPx = _resolveLength(t.min_size, canvasH) || 4;
    let maxPx = _resolveLength(t.max_size, canvasH) || 300;
    if (_deckTextSize != null && _deckTextSize > 0) maxPx = _deckTextSize;
    // A clamped block (max_lines) cannot spend more room by growing: the
    // clamp reports the same height at any size. Cap growth at the authored
    // size so autosize never turns a 2-line clamp into two giant lines.
    if (t.max_lines != null) {
        const authoredPx = _resolveLength(t.size, canvasH);
        if (authoredPx) maxPx = Math.min(maxPx, authoredPx);
    }
    const target = _panelFitTarget(el);
    if (!target || target <= 0) return;
    const ref = el.querySelector(".verse-ref");
    const gap = parseFloat(getComputedStyle(el).rowGap) || 0;
    const measure = function () {
        const margin = parseInt(getComputedStyle(h1).marginBottom) || 0;
        return h1.offsetHeight + margin + (ref ? ref.offsetHeight : 0)
            + (ref ? gap : 0);
    };
    let lo = Math.min(minPx, maxPx), hi = Math.max(minPx, maxPx);
    while (hi - lo > 0.5) {
        const mid = (lo + hi) / 2;
        h1.style.fontSize = mid + "px";
        if (measure() <= target) lo = mid; else hi = mid;
    }
    h1.style.fontSize = Math.floor(lo) + "px";
}

function _invalidatePanelOutlines() {
    if (!_currentContainers || !_currentContainers.length) return;
    _currentContainers.forEach(function (c) {
        const root = document.getElementById("rc-cont-" + c.id);
        const h1 = (root && typeof root.querySelector === "function")
            ? root.querySelector(".verse-text") : null;
        if (h1 && h1.dataset && h1.dataset.rcOcSrc !== undefined) {
            h1.innerHTML = h1.dataset.rcOcSrc;
            if (h1.dataset.rcOcW0) {
                h1.classList.add("rc-oc");
                h1.setAttribute("data-rc-oc-w", h1.dataset.rcOcW0);
                h1.setAttribute("data-rc-oc-c", h1.dataset.rcOcC0 || "#000");
            }
            delete h1.dataset.rcOcDone;
        }
    });
}

const _SPLIT_MAX_UNITS = 160;
const _SPLIT_MAX_DELAY = 5000;

function _splitConfig(owner) {
    // Accept either a block (`.animation`) or a bare assignment.
    const anim = owner && (owner.animation || owner);
    const split = anim && anim.split;
    if (!split || (split.by !== "line" && split.by !== "word")) return null;
    return split;
}

function _splitAssignment(base, split, index) {
    const extra = index === 0 ? split.first : split.rest;
    const out = Object.assign({}, base, extra || {});
    // `transition` is itself a phase map: merging it shallowly would let a
    // unit that overrides only `out` lose the parent's `in`, contradicting
    // "omitted phases inherit from the parent assignment".
    if (base.transition || (extra && extra.transition)) {
        out.transition = Object.assign({}, base.transition || {},
                                       (extra && extra.transition) || {});
    }
    delete out.split;
    return out;
}

function _splitLook(split, index) {
    const look = split.look || {};
    return index === 0 ? (look.first || null) : (look.rest || null);
}

function _applySplitLook(unit, split, index) {
    const look = _splitLook(split, index);
    if (!look) return;
    const nodes = [unit];
    if (unit.querySelectorAll) {
        unit.querySelectorAll(".rc-split-word").forEach(function (w) {
            nodes.push(w);
        });
    }
    nodes.forEach(function (node) {
        if (look.color) node.style.color = look.color;
        if (look.weight != null) node.style.fontWeight = String(look.weight);
        if (look.font_style) node.style.fontStyle = look.font_style;
        if (look.text_decoration) {
            node.style.textDecoration = look.text_decoration;
        }
        // Opacity multiplies down the tree: setting the line's look on its
        // words as well would paint 0.7 twice (0.49). The unit owns it.
        if (look.opacity != null && node === unit) {
            node.style.opacity = String(look.opacity);
        }
        if (look.letter_spacing != null) {
            node.style.letterSpacing = typeof look.letter_spacing === "number"
                ? look.letter_spacing + "px" : look.letter_spacing;
        }
    });
}

function _unitStyle(node) {
    const cs = getComputedStyle(node.nodeType === 1 ? node : node.parentNode);
    return {
        color: cs.color, fontFamily: cs.fontFamily, fontSize: cs.fontSize,
        fontWeight: cs.fontWeight, fontStyle: cs.fontStyle,
        letterSpacing: cs.letterSpacing,
        textDecoration: cs.textDecorationLine, textShadow: cs.textShadow,
        textTransform: cs.textTransform,
    };
}

function _applyUnitStyle(span, style) {
    span.style.color = style.color;
    span.style.fontFamily = style.fontFamily;
    span.style.fontSize = style.fontSize;
    span.style.fontWeight = style.fontWeight;
    span.style.fontStyle = style.fontStyle;
    span.style.letterSpacing = style.letterSpacing;
    if (style.textDecoration && style.textDecoration !== "none") {
        span.style.textDecoration = style.textDecoration;
    }
    if (style.textShadow && style.textShadow !== "none") {
        span.style.textShadow = style.textShadow;
    }
    if (style.textTransform && style.textTransform !== "none") {
        span.style.textTransform = style.textTransform;
    }
}

function _wrapSplitWords(el) {
    // Flatten the inline run styles onto each word: measured line groups are
    // moved out of their original colour spans, so inheritance must travel
    // with the unit or a two-colour verse would lose its second colour.
    const nodes = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    const words = [];
    nodes.forEach(function (node) {
        if (node.parentElement
            && node.parentElement.closest && node.parentElement.closest(".verse-num")) {
            return;
        }
        const text = node.nodeValue || "";
        if (!text.trim()) return;
        const style = _unitStyle(node);
        const parts = text.split(/(\s+)/);
        const frag = document.createDocumentFragment();
        parts.forEach(function (part) {
            if (!part) return;
            if (/^\s+$/.test(part)) {
                frag.appendChild(document.createTextNode(part));
                return;
            }
            const span = document.createElement("span");
            span.className = "rc-split-word";
            span.textContent = part;
            span.style.display = "inline-block";
            _applyUnitStyle(span, style);
            frag.appendChild(span);
            words.push(span);
        });
        node.parentNode.replaceChild(frag, node);
    });
    return words;
}

function _splitLines(el, words) {
    // Group by the browser's own line boxes: autofit and wrapping have
    // already run, so this is the only line count that matches the render.
    const groups = [];
    let group = [];
    let top = null;
    words.forEach(function (w) {
        const t = w.getBoundingClientRect().top;
        if (top === null || Math.abs(t - top) <= 1) {
            group.push(w);
        } else {
            groups.push(group);
            group = [w];
        }
        top = t;
    });
    if (group.length) groups.push(group);

    const verseNum = el.querySelector(".verse-num");
    if (verseNum && verseNum.parentNode) verseNum.parentNode.removeChild(verseNum);
    const lines = groups.map(function (items) {
        const line = document.createElement("span");
        line.className = "rc-split-line";
        line.style.display = "block";
        line.style.textAlign = getComputedStyle(el).textAlign;
        line.setAttribute("data-rc-unit", "1");
        items.forEach(function (w, i) {
            if (i) line.appendChild(document.createTextNode(" "));
            line.appendChild(w);
        });
        return line;
    });
    el.innerHTML = "";
    lines.forEach(function (line) { el.appendChild(line); });
    if (verseNum && lines.length) {
        const first = lines[0];
        first.insertBefore(document.createTextNode(" "), first.firstChild);
        first.insertBefore(verseNum, first.firstChild);
    }
    return lines;
}

function _splitBlocked(el, anim) {
    if (!el || !anim) return true;
    // Outlines rebuild the text as SVG; a line clamp pins the box; <br>,
    // <sup> and <sub> cannot be represented as uniform word boxes.
    if (el.dataset && (el.dataset.rcOcSrc !== undefined
        || el.dataset.rcOcDone)) return true;
    if (el.style && el.style.webkitLineClamp) return true;
    if (el.querySelector && el.querySelector("br, sup, sub")) return true;
    const anims = (_currentTheme && _currentTheme.animations) || {};
    const split = anim.split;
    const slots = [anim.entry, anim.transition && anim.transition.in];
    if (split) {
        [split.first, split.rest].forEach(function (part) {
            if (!part) return;
            slots.push(part.entry, part.transition && part.transition.in);
        });
    }
    return slots.some(function (slot) {
        const def = _resolveSlotDef(slot, anims, "in");
        return !!(def && def.type === "typewriter");
    });
}

function _unsplitAll() {
    if (typeof document === "undefined" || !document.querySelectorAll) return;
    document.querySelectorAll("[data-rc-split]").forEach(function (el) {
        // The webfont refit must not tear down units that are mid-animation:
        // a new payload already clears these markers and re-lays out.
        if (el.dataset && el.dataset.rcSplitAnimated) return;
        if (el.dataset && el.dataset.rcSplitSrc !== undefined) {
            el.innerHTML = el.dataset.rcSplitSrc;
        }
        if (el.dataset) {
            delete el.dataset.rcSplit;
            delete el.dataset.rcSplitSrc;
            delete el.dataset.rcSplitUnits;
        }
    });
}

function _layoutSplitUnits(theme) {
    if (!theme || theme.schema_version !== 2) return;
    _animationTargets(theme).forEach(function (t) {
        const split = _splitConfig(t.anim);
        if (!split || !t.el) return;
        if (t.kind !== "text" && t.kind !== "reference"
            && t.kind !== "translation") return;
        const el = t.el;
        if (el.dataset && el.dataset.rcSplitAnimated) return;
        if (el.dataset && el.dataset.rcSplit
            && el.dataset.rcSplitSrc !== undefined) {
            el.innerHTML = el.dataset.rcSplitSrc;
        }
        if (el.dataset) {
            delete el.dataset.rcSplit;
            delete el.dataset.rcSplitUnits;
        }
        if (_splitBlocked(el, t.anim)) return;
        if (!(el.textContent || "").trim()) return;
        el.dataset.rcSplitSrc = el.innerHTML;
        const words = _wrapSplitWords(el);
        if (!words.length) return;
        if (words.length > _SPLIT_MAX_UNITS) {
            el.innerHTML = el.dataset.rcSplitSrc;
            delete el.dataset.rcSplitSrc;
            return;
        }
        let units = words;
        if (split.by === "line") {
            units = _splitLines(el, words);
        } else {
            units.forEach(function (w) { w.setAttribute("data-rc-unit", "1"); });
        }
        units.forEach(function (unit, index) {
            _applySplitLook(unit, split, index);
        });
        el.dataset.rcSplit = split.by;
        el.dataset.rcSplitUnits = String(units.length);
    });
}

function _runSplitAnimation(el, anim, phase, anims) {
    const split = _splitConfig(anim);
    if (!split) return false;
    const units = Array.from(el.querySelectorAll('[data-rc-unit="1"]'));
    if (!units.length) return false;
    el.dataset.rcSplitAnimated = "1";
    const stagger = split.stagger_ms != null ? split.stagger_ms : 70;
    units.forEach(function (unit, index) {
        const assignment = _splitAssignment(anim, split, index);
        const slot = phase === "entry"
            ? assignment.entry
            : (assignment.transition && assignment.transition.in);
        if (!slot) return;
        const def = _resolveSlotDef(slot, anims, "in");
        if (!def) return;
        const delay = (def.delay_ms || 0)
            + Math.min(index * stagger, _SPLIT_MAX_DELAY);
        _playElementAnimation(unit, def, {
            kind: "text", phase: phase, delay_ms: delay,
        });
    });
    return true;
}

function _autoFitPanels() {
    if (!_currentContainers || _currentContainers.length < 2) return;
    _invalidatePanelOutlines();
    _currentContainers.forEach(function (c) {
        const el = document.getElementById("rc-cont-" + c.id);
        if (el) _fitPanelText(el, c);
    });
    _applyMultiBlockOutlines();
}

function _renderMultiContainers(data) {
    const stg = document.getElementById("stage") || document.body;
    if (container) container.style.display = "none";
    const refText = data.reference || (data.book && data.chapter && data.verse
        ? data.book + " " + data.chapter + ":" + data.verse : "");
    const canvasW = (_currentTheme && _currentTheme.canvas && _currentTheme.canvas.width) || 1920;
    const canvasH = (_currentTheme && _currentTheme.canvas && _currentTheme.canvas.height) || 1080;

    _currentContainers.forEach(c => {
        let el = document.getElementById("rc-cont-" + c.id);
        if (!el || !el.parentElement) {
            if (!el) el = document.createElement("div");
            el.id = "rc-cont-" + c.id;
            el.className = "rc-dynamic-container rc-container";
            stg.appendChild(el);
        }
        // Clear is a cloak, not a one-way trip: a container hidden by a
        // previous clear must come back when content renders again.
        el.classList.remove("hidden");
        let w = _resolveLength(c.width, canvasW);
        let h = _resolveLength(c.height, canvasH);
        if (w == null && c.min_width != null) w = _resolveLength(c.min_width, canvasW);
        if (h == null && c.min_height != null) h = _resolveLength(c.min_height, canvasH);
        if (w == null) w = canvasW;
        if (h == null) h = canvasH;

        const pos = _computePosition(c.position, w, h, canvasW, canvasH);
        el.style.position = "absolute";
        el.style.left = pos.left + "px";
        el.style.top = pos.top + "px";
        el.style.width = (pos.width || w) + "px";
        el.style.height = (pos.height || h) + "px";
        if (c.min_width != null) el.style.minWidth = _resolveLength(c.min_width, canvasW) + "px";
        if (c.max_width != null) el.style.maxWidth = _resolveLength(c.max_width, canvasW) + "px";
        if (c.min_height != null) el.style.minHeight = _resolveLength(c.min_height, canvasH) + "px";
        if (c.max_height != null) el.style.maxHeight = _resolveLength(c.max_height, canvasH) + "px";
        if (c.layer != null) el.style.zIndex = c.layer;
        if (c.opacity != null) el.style.opacity = c.opacity;
        if (c.overflow) el.style.overflow = c.overflow;
        if (c.background) el.style.background = c.background;
        else el.style.background = "";
        _applyBorder(el, c.border);
        if (c.border_radius != null) {
            el.style.borderRadius = _resolveLength(c.border_radius, canvasW) + "px";
        } else if (typeof c.border === "object" && c.border && c.border.radius != null) {
            el.style.borderRadius = c.border.radius + "px";
        } else {
            el.style.borderRadius = "";
        }
        if (c.box_shadow && c.box_shadow !== "none") {
            let bs = c.box_shadow;
            if (typeof bs === "object" && bs) {
                bs = (bs.inset ? "inset " : "") + (bs.x || 0) + "px " + (bs.y || 0) + "px " + (bs.blur || 0) + "px " + (bs.spread || 0) + "px " + (bs.color || "rgba(0,0,0,0.5)");
            }
            el.style.boxShadow = bs;
        } else {
            el.style.boxShadow = "none";
        }
        if (c.backdrop_filter && c.backdrop_filter !== "none") el.style.backdropFilter = c.backdrop_filter;
        else el.style.backdropFilter = "";

        const blocks = _getContainerBlocks(c);
        const b = blocks.body;
        el.style.display = "flex";
        el.style.flexDirection = "column";
        const valign = b.valign || "center";
        el.style.justifyContent = valign === "top" ? "flex-start" : valign === "bottom" ? "flex-end" : "center";
        if (b.gap != null) el.style.gap = b.gap + "px";
        const pt = (b.padding_top != null ? b.padding_top : b.padding) || 0;
        const pr = (b.padding_right != null ? b.padding_right : b.padding) || 0;
        const pb = (b.padding_bottom != null ? b.padding_bottom : b.padding) || 0;
        const pl = (b.padding_left != null ? b.padding_left : b.padding) || 0;
        el.style.padding = `${pt}px ${pr}px ${pb}px ${pl}px`;

        el.innerHTML = "";
        const t = _authoredBlock(c, "text");
        const r = _authoredBlock(c, "reference");
        const tr = _authoredBlock(c, "translation");
        const vn = _authoredBlock(c, "verse_num");

        const textHasContent = !!(data.text && t && t.visible !== false);
        const refHasContent = !!(refText && r && r.visible !== false);
        const transHasContent = !!(data.translation && tr && tr.visible !== false);

        function makeTextEl() {
            const h1 = document.createElement("h1");
            h1.className = "verse-text";
            let html = renderInlineColors(data.text);
            const vnNum = extractVerseNumber(refText);
            if (vnNum && vn && vn.visible !== false && (vn.mode || "inline") === "inline") {
                html = '<span class="verse-num" style="color:' + (vn.color || "#cccccc") + '">' + vnNum + '</span> ' + html;
            }
            h1.innerHTML = html;
            if (t.color) h1.style.color = t.color;
            if (t.size != null) h1.style.fontSize = typeof t.size === "number" ? (t.size + "px") : t.size;
            if (t.weight != null) h1.style.fontWeight = String(t.weight);
            if (t.font_family) h1.style.fontFamily = t.font_family;
            if (t.line_height != null) h1.style.lineHeight = String(t.line_height);
            if (t.letter_spacing != null) h1.style.letterSpacing = typeof t.letter_spacing === "number" ? (t.letter_spacing + "px") : t.letter_spacing;
            if (t.text_align) h1.style.textAlign = t.text_align;
            if (t.text_transform) h1.style.textTransform = t.text_transform;
            if (t.text_shadow && t.text_shadow !== "none") h1.style.textShadow = t.text_shadow;
            if (t.word_spacing != null) h1.style.wordSpacing = typeof t.word_spacing === "number" ? (t.word_spacing + "px") : t.word_spacing;
            if (t.font_style) h1.style.fontStyle = t.font_style;
            if (t.text_decoration && t.text_decoration !== "none") h1.style.textDecoration = t.text_decoration;
            if (t.direction) {
                h1.style.direction = t.direction;
                if (t.direction === "rtl") h1.style.unicodeBidi = "embed";
            }
            if (t.max_lines != null) {
                // §4.3: clamp rendered lines. -webkit-box is the only
                // cross-Chromium line clamp and is OBS's renderer anyway.
                h1.style.display = "-webkit-box";
                h1.style.webkitBoxOrient = "vertical";
                h1.style.webkitLineClamp = String(t.max_lines);
                h1.style.overflow = "hidden";
            }
            return h1;
        }

        function makeRefEl() {
            const p = document.createElement("p");
            p.className = "verse-ref";
            const sRef = document.createElement("span");
            sRef.className = "verse-ref-text";
            sRef.textContent = refText;
            if (r.color) sRef.style.color = r.color;
            if (r.size != null) sRef.style.fontSize = typeof r.size === "number" ? (r.size + "px") : r.size;
            if (r.weight != null) sRef.style.fontWeight = String(r.weight);
            if (r.font_family) sRef.style.fontFamily = r.font_family;
            if (r.text_transform) sRef.style.textTransform = r.text_transform;
            if (r.letter_spacing != null) sRef.style.letterSpacing = typeof r.letter_spacing === "number" ? (r.letter_spacing + "px") : r.letter_spacing;
            p.appendChild(sRef);

            if (transHasContent) {
                const sTr = document.createElement("span");
                sTr.className = "verse-ref-translation";
                sTr.textContent = data.translation;
                if (tr.color) sTr.style.color = tr.color;
                if (tr.size != null) sTr.style.fontSize = typeof tr.size === "number" ? (tr.size + "px") : tr.size;
                if (tr.weight != null) sTr.style.fontWeight = String(tr.weight);
                if (tr.font_family) sTr.style.fontFamily = tr.font_family;
                if (tr.letter_spacing != null) sTr.style.letterSpacing = typeof tr.letter_spacing === "number" ? (tr.letter_spacing + "px") : tr.letter_spacing;
                if (tr.line_height != null) sTr.style.lineHeight = String(tr.line_height);
                if (tr.text_transform) sTr.style.textTransform = tr.text_transform;
                if (tr.margin_left != null) sTr.style.marginLeft = typeof tr.margin_left === "number" ? (tr.margin_left + "px") : tr.margin_left;
                if (tr.position === "left_of_reference" && typeof p.insertBefore === "function") {
                    p.insertBefore(sTr, sRef);
                } else if (tr.position === "above_reference") {
                    p.style.display = "flex";
                    p.style.flexDirection = "column-reverse";
                    p.style.alignItems = "center";
                    if (typeof p.appendChild === "function") p.appendChild(sTr);
                } else if (tr.position === "below_reference") {
                    p.style.display = "flex";
                    p.style.flexDirection = "column";
                    p.style.alignItems = "center";
                    if (typeof p.appendChild === "function") p.appendChild(sTr);
                } else {
                    if (typeof p.appendChild === "function") p.appendChild(sTr);
                }
            }
            return p;
        }

        if (textHasContent && refHasContent) {
            if (r.position === "above_verse") {
                el.appendChild(makeRefEl());
                el.appendChild(makeTextEl());
            } else {
                el.appendChild(makeTextEl());
                el.appendChild(makeRefEl());
            }
        } else if (textHasContent) {
            el.appendChild(makeTextEl());
        } else if (refHasContent) {
            el.appendChild(makeRefEl());
        } else if (transHasContent) {
            const p = document.createElement("p");
            const sTr = document.createElement("span");
            sTr.textContent = data.translation;
            if (tr.color) sTr.style.color = tr.color;
            if (tr.size != null) sTr.style.fontSize = typeof tr.size === "number" ? (tr.size + "px") : tr.size;
            if (tr.weight != null) sTr.style.fontWeight = String(tr.weight);
            if (tr.font_family) sTr.style.fontFamily = tr.font_family;
            if (tr.letter_spacing != null) sTr.style.letterSpacing = typeof tr.letter_spacing === "number" ? (tr.letter_spacing + "px") : tr.letter_spacing;
            if (tr.line_height != null) sTr.style.lineHeight = String(tr.line_height);
            if (tr.text_transform) sTr.style.textTransform = tr.text_transform;
            sTr.style.marginLeft = "8px";
            p.appendChild(sTr);
            el.appendChild(p);
        }
    });
    _autoFitPanels();
}

function _applyMultiBlockOutlines() {
    // Block-level text_outline in a split theme. applyOutlineLayers() only
    // owns #verse-text, which is display:none once panels render, so each
    // panel converts its own h1. Failure leaves readable plain text.
    _currentContainers.forEach(c => {
        const t = _authoredBlock(c, "text");
        const outline = t ? _themeOutline(t) : "";
        const root = document.getElementById("rc-cont-" + c.id);
        const h1 = (root && typeof root.querySelector === "function")
            ? root.querySelector(".verse-text") : null;
        if (!h1) return;
        const oc = outline ? _outlineParts(outline) : null;
        if (oc && oc.width > 0) convertOutlineScope(h1, oc.width, oc.color);
    });
}

// ─── Animation engine (schema v2 §4.9) ──────────────────────────────
// Python has already validated and resolved every definition: presets carry
// their keyframes, `typewriter` carries its reveal/cursor fields, and slots
// are either `{ "use": name, ...overrides }` or an inline definition. This
// engine only plays them. `"base"` is resolved here from the element's
// resting computed style, after any in-flight animation is cancelled.
//
// The @keyframes table below is a v1 raw-payload fallback only: a resolved
// v2 theme never reaches it, and v2 never injects CSS.

const ANIM_KEYFRAMES = {
    fade_up:      { from: "opacity:0;transform:translateY(20px)",     to: "opacity:1;transform:translateY(0)" },
    fade_in:      { from: "opacity:0",                                to: "opacity:1" },
    fade_down:    { from: "opacity:1;transform:translateY(0)",        to: "opacity:0;transform:translateY(20px)" },
    fade_out:     { from: "opacity:1",                                to: "opacity:0" },
    scale_up:     { from: "opacity:0;transform:scale(0.85)",         to: "opacity:1;transform:scale(1)" },
    scale_down:   { from: "opacity:1;transform:scale(1)",            to: "opacity:0;transform:scale(0.85)" },
    slide_up:     { from: "transform:translateY(100%)",              to: "transform:translateY(0)" },
    slide_down:   { from: "transform:translateY(0)",                 to: "transform:translateY(100%)" },
};

const ANIM_PRESET_TYPES = ["fade_in", "fade_out", "fade_up", "fade_down",
    "scale_up", "scale_down", "slide_up", "slide_down"];

const ANIM_EASINGS = {
    "ease-out":     "cubic-bezier(0.16, 1, 0.3, 1)",
    "ease-in":      "cubic-bezier(0.55, 0.085, 0.68, 0.53)",
    "ease-in-out":  "cubic-bezier(0.65, 0, 0.35, 1)",
    "linear":       "linear",
    "spring":       "cubic-bezier(0.34, 1.56, 0.64, 1)",
    "smooth":       "cubic-bezier(0.25, 0.1, 0.25, 1)",
};

const _activeAnims = new WeakMap();
const _animatedEls = new Set();
const _activeTypewriters = new Set();
let _phaseTimer = null;
let _phaseToken = 0;

function _reducedMotion() {
    try {
        return typeof matchMedia === "function"
            && matchMedia("(prefers-reduced-motion: reduce)").matches === true;
    } catch (e) {
        return false;
    }
}

function _injectAnimStyle() {
    if (_animStyleEl) return;
    _animStyleEl = document.createElement("style");
    _animStyleEl.id = "rc-animations";
    let css = "";
    for (const [name, kf] of Object.entries(ANIM_KEYFRAMES)) {
        css += `@keyframes rc-${name} { from { ${kf.from}; } to { ${kf.to}; } }\n`;
    }
    _animStyleEl.textContent = css;
    document.head.appendChild(_animStyleEl);
}

function _applyAnimation(el, type, durationMs, easing) {
    if (!type || type === "none" || !el || _reducedMotion()) return;
    const kfName = `rc-${type}`;
    const dur = (durationMs || 600) + "ms";
    const ease = ANIM_EASINGS[easing] || ANIM_EASINGS["ease-out"] || "ease-out";
    el.style.animation = `${kfName} ${dur} ${ease} forwards`;
    el.addEventListener("animationend", () => { el.style.animation = ""; }, { once: true });
}

function _cancelAnimations(el) {
    if (!el) return;
    const anim = _activeAnims.get(el);
    if (anim) {
        try { anim.cancel(); } catch (e) {}
        _activeAnims.delete(el);
    }
    _animatedEls.delete(el);
}

function _cancelAllAnimations() {
    if (_phaseTimer) {
        clearTimeout(_phaseTimer);
        _phaseTimer = null;
    }
    _phaseToken++;
    Array.from(_activeTypewriters).forEach(tw => {
        try { tw.cancel(); } catch (e) {}
    });
    _activeTypewriters.clear();
    Array.from(_animatedEls).forEach(el => _cancelAnimations(el));
    _animatedEls.clear();
}

function _restingOpacity(el) {
    try {
        const v = parseFloat(getComputedStyle(el).opacity);
        return isNaN(v) ? 1 : v;
    } catch (e) {
        return 1;
    }
}

function _restingBlur(el) {
    try {
        const f = String(getComputedStyle(el).filter || "");
        const m = f.match(/blur\(([\d.]+)px\)/);
        return m ? parseFloat(m[1]) : 0;
    } catch (e) {
        return 0;
    }
}

function _lengthValue(v, fallback) {
    if (v == null) return fallback || "0px";
    if (typeof v === "number") return v + "px";
    const s = String(v).trim();
    if (!s) return fallback || "0px";
    if (/^-?[\d.]+(px|%|em|rem)$/.test(s)) return s;
    if (/^-?[\d.]+$/.test(s)) return s + "px";
    return fallback || "0px";
}

function _resolveSlotDef(slot, registry, phase) {
    const fallback = phase === "out" ? "fade_out" : "fade_in";
    const preset = (name) => ({ type: name, duration_ms: 600, easing: "ease-out" });
    if (!slot || slot === "none") return null;
    if (typeof slot === "string") {
        if (registry && registry[slot]) return registry[slot];
        if (ANIM_PRESET_TYPES.indexOf(slot) !== -1) return preset(slot);
        return preset(fallback);
    }
    if (typeof slot === "object") {
        if (slot.use) {
            const base = (registry && registry[slot.use])
                || (ANIM_PRESET_TYPES.indexOf(slot.use) !== -1
                    ? preset(slot.use) : preset(fallback));
            const merged = Object.assign({}, base, slot);
            delete merged.use;
            return merged;
        }
        if (slot.type) return slot;
    }
    return null;
}

// Python emits one normalized keyframe list for every non-typewriter
// definition (presets included), so the renderer never keeps its own copy.
// Preset frames are the fallback for raw definitions that omitted them.
function _presetFrames(type, el) {
    const base = _restingOpacity(el);
    if (type === "fade_in") return [{ opacity: 0 }, { opacity: base }];
    if (type === "fade_out") return [{ opacity: base }, { opacity: 0 }];
    if (type === "fade_up") return [{ opacity: 0, transform: "translateY(20px)" },
                                    { opacity: base, transform: "translateY(0)" }];
    if (type === "fade_down") return [{ opacity: base, transform: "translateY(0)" },
                                      { opacity: 0, transform: "translateY(20px)" }];
    if (type === "scale_up") return [{ opacity: 0, transform: "scale(0.85)" },
                                     { opacity: base, transform: "scale(1)" }];
    if (type === "scale_down") return [{ opacity: base, transform: "scale(1)" },
                                       { opacity: 0, transform: "scale(0.85)" }];
    if (type === "slide_up") return [{ transform: "translateY(100%)" },
                                     { transform: "translateY(0)" }];
    if (type === "slide_down") return [{ transform: "translateY(0)" },
                                       { transform: "translateY(100%)" }];
    return null;
}

function _keyframeFrames(def, el) {
    if (!Array.isArray(def.keyframes)) return null;
    return def.keyframes.map(k => {
        const at = parseFloat(k.at);
        const f = { offset: Math.max(0, Math.min(1, isNaN(at) ? 0 : at / 100)) };
        if (k.opacity != null) {
            f.opacity = k.opacity === "base" ? _restingOpacity(el) : k.opacity;
        }
        const tr = [];
        if (k.translate_x != null || k.translate_y != null) {
            tr.push("translate(" + _lengthValue(k.translate_x) + ", "
                + _lengthValue(k.translate_y) + ")");
        }
        if (k.rotate != null) tr.push("rotate(" + k.rotate + "deg)");
        if (k.scale != null) tr.push("scale(" + k.scale + ")");
        if (tr.length) f.transform = tr.join(" ");
        if (k.blur != null) {
            const blur = k.blur === "base" ? _restingBlur(el) : parseFloat(_lengthValue(k.blur));
            f.filter = "blur(" + (isNaN(blur) ? 0 : blur) + "px)";
        }
        return f;
    });
}

function _framesForDefinition(def, el) {
    return _keyframeFrames(def, el) || _presetFrames(def.type, el);
}

function _trackAnimation(el, anim, hold) {
    _animatedEls.add(el);
    _activeAnims.set(el, anim);
    const done = () => {
        if (!hold) {
            try { anim.cancel(); } catch (e) {}
            if (_activeAnims.get(el) === anim) {
                _activeAnims.delete(el);
                _animatedEls.delete(el);
            }
        }
        // `out` keeps its filled end state until the caller hides the element
        // or the next render cancels it; cancelling here would flash the old
        // content back for one frame.
    };
    try {
        if (anim.finished && typeof anim.finished.then === "function") {
            anim.finished.then(done, done);
        } else if (typeof anim.addEventListener === "function") {
            anim.addEventListener("finish", done, { once: true });
        }
    } catch (e) {
        done();
    }
}

function _graphemes(text) {
    try {
        if (typeof Intl !== "undefined" && Intl.Segmenter) {
            const seg = new Intl.Segmenter(undefined, { granularity: "grapheme" });
            return Array.from(seg.segment(text), s => s.segment);
        }
    } catch (e) {}
    return Array.from(text);
}

function _typewriterSegments(text, reveal) {
    const raw = String(text == null ? "" : text);
    if (!raw) return [];
    if (reveal === "word") {
        return raw.match(/\s*\S+\s*|\s+/g) || [];
    }
    const out = [];
    _graphemes(raw).forEach(g => {
        // Whitespace reveals with the preceding segment, so a line break
        // appears at the moment the last word on the line does.
        if (out.length && /^\s+$/.test(g)) out[out.length - 1] += g;
        else out.push(g);
    });
    return out;
}

function _outlineConflict(el) {
    try {
        if (el && typeof el.querySelector === "function" && el.querySelector(".rc-oc")) {
            return true;
        }
        if (el && el.dataset && el.dataset.rcOcDone) return true;
    } catch (e) {}
    return false;
}

// Splits every text node under `el` into per-segment spans that reserve their
// layout while hidden. Each original node is replaced by one wrapper span so
// `restore()` can put the exact same node back — no innerHTML round-trip and
// no loss of inline run markup.
function _splitTypewriter(el, reveal) {
    if (!el || typeof document.createTreeWalker !== "function"
        || typeof document.createTextNode !== "function") return null;
    let walker;
    try {
        walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    } catch (e) {
        return null;
    }
    if (!walker || typeof walker.nextNode !== "function") return null;
    const nodes = [];
    let node = walker.nextNode();
    while (node) {
        if (node.nodeValue) nodes.push(node);
        node = walker.nextNode();
    }
    if (!nodes.length) return null;

    const records = [];
    const spans = [];
    nodes.forEach(textNode => {
        const parent = textNode.parentNode;
        if (!parent || typeof parent.replaceChild !== "function") return;
        const segments = _typewriterSegments(textNode.nodeValue, reveal);
        if (!segments.length) return;
        const wrap = document.createElement("span");
        wrap.setAttribute("data-rc-tw", "1");
        wrap.style.display = "inline";
        segments.forEach(seg => {
            const span = document.createElement("span");
            span.textContent = seg;
            span.style.visibility = "hidden";
            wrap.appendChild(span);
            spans.push(span);
        });
        parent.replaceChild(wrap, textNode);
        records.push({ parent: parent, wrap: wrap, node: textNode });
    });

    if (!spans.length) {
        records.forEach(r => {
            try {
                if (r.wrap.parentNode) r.wrap.parentNode.replaceChild(r.node, r.wrap);
            } catch (e) {}
        });
        return null;
    }
    return {
        spans: spans,
        restore: function () {
            records.forEach(r => {
                try {
                    if (r.wrap.parentNode) r.wrap.parentNode.replaceChild(r.node, r.wrap);
                } catch (e) {}
            });
        },
    };
}

function _typewriterCursor(cfg) {
    if (!cfg || cfg === "none") return null;
    const span = document.createElement("span");
    span.className = "rc-tw-cursor";
    span.textContent = cfg.char || "\u258c";
    // Zero-width so moving it along the reveal never reflows the line; the
    // glyph overflows at the insertion point instead.
    span.style.display = "inline-block";
    span.style.width = "0";
    span.style.overflow = "visible";
    span.style.whiteSpace = "pre";
    if (cfg.color && cfg.color !== "currentColor") span.style.color = cfg.color;
    return span;
}

function _playTypewriter(el, def) {
    if (!el || _reducedMotion()) return null;
    const split = _splitTypewriter(el, def.reveal === "word" ? "word" : "char");
    if (!split) {
        if (typeof el.animate !== "function") return null;
        return _playElementAnimation(el, Object.assign({}, def, { type: "fade_in" }),
            { kind: "text", phase: "in" });
    }

    const spans = split.spans;
    const cfg = def.cursor && def.cursor !== "none" ? def.cursor : null;
    const cursor = _typewriterCursor(cfg);
    const total = Math.max(0, def.duration_ms != null ? def.duration_ms : 900);
    const delay = Math.max(0, def.delay_ms || 0);
    let revealed = 0;
    let rafId = null;
    let timer = null;
    let interval = null;
    let cursorTimer = null;
    let finishTimer = null;
    let done = false;

    const now = () => (typeof performance !== "undefined" && performance.now)
        ? performance.now() : Date.now();

    function placeCursor(index) {
        if (!cursor) return;
        const ref = spans[Math.max(0, Math.min(spans.length - 1, index))];
        const parent = ref && ref.parentNode;
        if (!parent) return;
        parent.insertBefore(cursor, ref.nextSibling);
    }

    function cleanup() {
        if (rafId != null && typeof cancelAnimationFrame === "function") {
            cancelAnimationFrame(rafId);
        }
        if (timer != null) clearTimeout(timer);
        if (interval != null) clearInterval(interval);
        if (cursorTimer != null) clearTimeout(cursorTimer);
        if (finishTimer != null) clearTimeout(finishTimer);
        rafId = timer = interval = cursorTimer = finishTimer = null;
        if (cursor && cursor.parentNode) cursor.parentNode.removeChild(cursor);
        split.restore();
        _activeTypewriters.delete(handle);
    }

    function show(count) {
        while (revealed < count && revealed < spans.length) {
            spans[revealed].style.visibility = "visible";
            revealed++;
        }
        placeCursor(revealed - 1);
    }

    function finish() {
        if (done) return;
        done = true;
        show(spans.length);
        if (interval != null) {
            clearInterval(interval);
            interval = null;
        }
        // Keep the cursor long enough to read, then unwrap back to plain text.
        const hide = Math.max(0, cfg && cfg.hide_after_ms != null ? cfg.hide_after_ms : 600);
        cursorTimer = setTimeout(cleanup, hide);
    }

    function tick(at) {
        if (done) return;
        const nowMs = typeof at === "number" ? at : now();
        const elapsed = Math.max(0, nowMs - started - delay);
        if (total <= 0 || elapsed >= total) {
            finish();
            return;
        }
        show(Math.max(1, Math.ceil((elapsed / total) * spans.length)));
        rafId = requestAnimationFrame(tick);
    }

    if (cursor) {
        placeCursor(0);
        const blink = Math.max(0, cfg && cfg.blink_ms != null ? cfg.blink_ms : 500);
        if (blink > 0) {
            let visible = true;
            interval = setInterval(() => {
                if (!cursor.parentNode) {
                    clearInterval(interval);
                    interval = null;
                    return;
                }
                visible = !visible;
                cursor.style.visibility = visible ? "visible" : "hidden";
            }, blink);
        }
    }

    const handle = {
        finished: Promise.resolve(),
        cancel: function () {
            if (done) return;
            done = true;
            cleanup();
        },
    };
    const started = now();
    _activeTypewriters.add(handle);

    // rAF drives the smooth reveal, but an occluded or throttled page may
    // starve it entirely (headless proves this). The hard finish timer keeps
    // the animation decoration-only: the text is complete by its deadline
    // even if no frame ever runs.
    if (total > 0) {
        finishTimer = setTimeout(finish, delay + total + 50);
    }

    if (total <= 0) {
        finish();
    } else if (delay > 0) {
        timer = setTimeout(() => {
            timer = null;
            rafId = requestAnimationFrame(tick);
        }, delay);
    } else {
        rafId = requestAnimationFrame(tick);
    }

    return handle;
}

function _playElementAnimation(el, def, opts) {
    opts = opts || {};
    if (!el || !def || def.type === "none" || _reducedMotion()) return null;
    const kind = opts.kind || "text";
    const phase = opts.phase || "in";
    let type = def.type;

    if (type === "typewriter") {
        // §4.9.5: legal only on text-bearing blocks, never as an exit, and
        // never when the block's text has been rebuilt as outlined SVG.
        if (phase === "out") {
            type = "fade_out";
        } else if (kind !== "text" && kind !== "reference" && kind !== "translation") {
            type = "fade_in";
        } else if (_outlineConflict(el)) {
            type = "fade_in";
        } else {
            return _playTypewriter(el, def);
        }
    }

    const duration = def.duration_ms != null ? def.duration_ms : 600;
    const delay = Math.max(0, opts.delay_ms != null
        ? opts.delay_ms : (def.delay_ms || 0));
    _cancelAnimations(el);
    if (duration <= 0 || typeof el.animate !== "function") return null;

    const frames = _framesForDefinition(Object.assign({}, def, { type: type }), el);
    if (!frames) return null;
    let anim;
    try {
        anim = el.animate(frames, {
            duration: duration,
            delay: delay,
            easing: ANIM_EASINGS[def.easing] || def.easing || "ease-out",
            fill: "forwards",
        });
    } catch (e) {
        return null;
    }
    if (def.origin) el.style.transformOrigin = def.origin;
    _trackAnimation(el, anim, phase === "out");
    return anim;
}

function _phaseDuration(def) {
    return Math.max(0, def.delay_ms || 0)
        + Math.max(0, def.duration_ms != null ? def.duration_ms : 600);
}

function _containerElement(c) {
    if (!c) return container;
    return document.getElementById("rc-cont-" + c.id) || container;
}

function _bodyElement(el) {
    if (el === container) {
        return document.getElementById("verse-content") || el;
    }
    return el;
}

function _blockElement(rootEl, name) {
    if (!rootEl) return null;
    if (rootEl === container || rootEl.id === "container") {
        if (name === "text") return document.getElementById("verse-text");
        if (name === "reference") {
            return document.getElementById("verse-ref-text")
                || document.getElementById("verse-ref");
        }
        if (name === "translation") {
            return document.getElementById("verse-ref-translation");
        }
        return null;
    }
    if (typeof rootEl.querySelector !== "function") return null;
    if (name === "text") return rootEl.querySelector(".verse-text");
    if (name === "reference") {
        return rootEl.querySelector(".verse-ref-text")
            || rootEl.querySelector(".verse-ref");
    }
    if (name === "translation") {
        return rootEl.querySelector(".verse-ref-translation")
            || rootEl.querySelector(".verse-ref");
    }
    return null;
}

function _animationTargets(theme) {
    const out = [];
    if (!theme) return out;
    const containers = Array.isArray(theme.containers)
        ? theme.containers
        : (_currentContainers.length ? _currentContainers : [themeContainer(theme)]);
    containers.forEach(c => {
        if (!c || typeof c !== "object" || c.visible === false) return;
        const el = _containerElement(c);
        if (!el) return;
        if (c.animation) out.push({ el: el, kind: "container", anim: c.animation });
        const blocks = _getContainerBlocks(c);
        if (blocks.body && blocks.body.animation) {
            out.push({ el: _bodyElement(el), kind: "body", anim: blocks.body.animation });
        }
        ["text", "reference", "translation"].forEach(name => {
            const b = blocks[name];
            if (!b || !b.animation) return;
            const bEl = _blockElement(el, name);
            if (bEl) out.push({ el: bEl, kind: name, anim: b.animation });
        });
    });
    return out;
}

function _collectTransitionOut(theme, changed) {
    const plan = [];
    if (_reducedMotion()) return plan;
    if (!theme || !changed || !changed.any) return plan;
    const anims = theme.animations || {};
    _animationTargets(theme).forEach(t => {
        const trans = t.anim && t.anim.transition;
        if (!trans || !trans.out) return;
        const relevant = (t.kind === "container" || t.kind === "body")
            ? changed.any : !!changed[t.kind];
        if (!relevant) return;
        const def = _resolveSlotDef(trans.out, anims, "out");
        if (def) plan.push({ el: t.el, def: def, kind: t.kind });
    });
    return plan;
}

function _collectExit(theme) {
    const plan = [];
    if (!theme) return plan;
    const anims = theme.animations || {};
    if (theme.schema_version !== 2 && !Array.isArray(theme.containers)
        && anims.display_exit && anims.display_exit.type) {
        plan.push({ el: container, def: anims.display_exit, kind: "container" });
        return plan;
    }
    _animationTargets(theme).forEach(t => {
        if (!t.anim || !t.anim.out) return;
        const def = _resolveSlotDef(t.anim.out, anims, "out");
        if (def) plan.push({ el: t.el, def: def, kind: t.kind });
    });
    return plan;
}

function _runAnimation(phase, changed) {
    if (_reducedMotion()) return;
    const theme = _currentTheme;
    if (!theme) return;
    const anims = theme.animations || {};

    // Raw v1 payload that bypassed Python: keep the legacy phase names.
    if (theme.schema_version !== 2 && !Array.isArray(theme.containers)) {
        if (phase === "entry" && anims.display_enter) {
            _injectAnimStyle();
            _applyAnimation(container, anims.display_enter.type,
                anims.display_enter.duration_ms, anims.display_enter.easing);
        } else if (phase === "in" && anims.between_slides) {
            _injectAnimStyle();
            _applyAnimation(container, anims.between_slides.in_type,
                anims.between_slides.duration_ms, anims.between_slides.easing);
        }
        return;
    }

    _animationTargets(theme).forEach(t => {
        let slot = null;
        if (phase === "entry") {
            slot = t.anim.entry;
        } else if (phase === "in") {
            const relevant = (t.kind === "container" || t.kind === "body")
                ? changed.any : !!changed[t.kind];
            if (!relevant) return;
            slot = t.anim.transition && t.anim.transition.in;
        }
        if (!slot) return;
        if (phase !== "out" && _splitConfig(t.anim)
            && _runSplitAnimation(t.el, t.anim, phase, anims)) return;
        const def = _resolveSlotDef(slot, anims, "in");
        if (def) _playElementAnimation(t.el, def, { kind: t.kind, phase: phase });
    });
}

function _runExitAnimation(callback) {
    if (_reducedMotion()) {
        callback();
        return;
    }
    // The exit reads the CURRENTLY applied theme: cloak after a theme-only
    // restyle must play the new theme's `out`, not the payload's old one.
    const theme = _currentTheme || (_prevPayload && _prevPayload.theme_data);
    const plan = _collectExit(theme);
    if (!plan.length) {
        callback();
        return;
    }
    let total = 0;
    plan.forEach(p => {
        _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "out" });
        total = Math.max(total, _phaseDuration(p.def));
    });
    if (total <= 0) {
        callback();
        return;
    }
    _phaseTimer = setTimeout(() => {
        _phaseTimer = null;
        callback();
    }, total);
}

// ─── Inline run markup ───────────────────────────────────────────────
// Slide text may carry [words (k=v; k=v)] runs (legacy [words: (#hex)]
// still parses as color-only). The payload arrives HTML-escaped by
// sanitize_payload(); this converts runs to <span> elements and single
// newlines to <br/> at render time — the single conversion point; never
// pre-convert server-side or spans double-escape into text.
// A bracket whose final (...) group holds no valid params stays literal.
const _INLINE_TRUE = new Set(["true", "1", "yes"]);
const _INLINE_FALSE = new Set(["false", "0", "no"]);
const _INLINE_KEYS = new Set(["size", "bold", "color", "italics", "case",
    "underline", "strike", "align", "spacing", "super", "sub",
    "outline", "shadow", "dir", "hr", "font"]);


function _attrEscape(text) {
    return String(text == null ? "" : text)
        .replace(/&/g, "&amp;").replace(/"/g, "&quot;")
        .replace(/</g, "&lt;").replace(/>/g, "&gt;");
}


// One inline run with a true outward outline: a stroke-only copy behind the
// opaque glyphs. `inner` is the already-escaped run content (may hold <sup>,
// <sub>); `plain` is the text the copy repeats.
function _outlineRun(inner, plain, outline) {
    const oc = _outlineParts(outline);
    if (!oc) return inner;
    // Width/color ride as data attributes (no cross-file contract); the real
    // stroke value is computed in applyOutlineLayers() once the font size is
    // known, so a JS/CSS version mix degrades to no stroke, never a blob.
    return '<span class="rc-oc" data-rc-oc="' + plain + '"'
        + ' data-rc-oc-w="' + oc.width + '" data-rc-oc-c="' + oc.color + '">'
        + inner + "</span>";
}
// True outline, second half: per-line inline SVG.
//
// -webkit-text-stroke straddles the glyph path (half grows inward, miter
// joins spike at acute angles), and Chromium ignores stroke-linejoin for
// HTML text. SVG text with paint-order="stroke fill" + stroke-linejoin="round"
// is a genuine outward outline that follows every glyph. SVG text cannot wrap,
// so after layout each outlined scope is rebuilt as one inline <svg> per
// rendered line, measured from the browser's own line boxes. The original
// HTML stays as the fallback: without layout (tests, print) scopes are left
// untouched and no outline paints.
const _OC_SVG_NS = "http://www.w3.org/2000/svg";
let _ocCanvas = null;

function _ocMeasure(text, style) {
    // Advance + ink metrics for one fragment. letterSpacing is added by hand
    // (not via ctx.letterSpacing) so canvas and SVG use identical arithmetic.
    // Negative letter-spacing collapses spaces outright in SVG text, so the
    // attribute is NEVER set there: spacing rides explicit x positions, one
    // tspan per word (spaces become pure advances, never painted glyphs).
    try {
        if (!_ocCanvas) {
            _ocCanvas = document.createElement("canvas").getContext("2d");
        }
        _ocCanvas.font = style.fontStyle + " " + style.weight + " "
            + style.size + "px " + style.family;
        const m = _ocCanvas.measureText(text);
        const gaps = Math.max(0, text.length - 1);
        return {
            width: Math.max(0, m.width + style.letterSpacing * gaps),
            ascent: m.actualBoundingBoxAscent || 0,
            descent: m.actualBoundingBoxDescent || 0,
        };
    } catch (e) {
        return null;
    }
}

// One fragment -> word tokens with explicit advances. A word keeps its
// natural shaping (kerning, ligatures); spacing between words rides x.
// letterSpacing: with ls == 0 the word measures as one shaped unit; with
// ls != 0 layout breaks shaping (no ligatures, no kerning), so the word is
// summed per character to match exactly.
function _ocTokens(text, style) {
    const out = [];
    const parts = String(text).split(/(\s+)/);
    for (const part of parts) {
        if (!part) continue;
        if (/^\s+$/.test(part)) {
            let w = 0;
            try {
                w = _ocCanvas.measureText(" ").width;
            } catch (e) { w = style.size * 0.25; }
            out.push({ text: "", advance: w + (style.wordSpacing + style.letterSpacing) * part.length });
            continue;
        }
        let w;
        if (style.letterSpacing) {
            w = 0;
            for (const ch of part) {
                try { w += _ocCanvas.measureText(ch).width; }
                catch (e) { w += style.size * 0.5; }
            }
            w += style.letterSpacing * part.length;
        } else {
            try { w = _ocCanvas.measureText(part).width; }
            catch (e) { w = style.size * 0.5 * part.length; }
        }
        out.push({ text: part, advance: w });
    }
    return out;
}

function _ocSnapshot(node) {
    // The style that actually shaped this text node, as plain data.
    const cs = getComputedStyle(node.parentElement);
    const size = parseFloat(cs.fontSize) || 16;
    const ls = cs.letterSpacing === "normal" ? 0 : parseFloat(cs.letterSpacing) || 0;
    // Decoration: SVG text cannot do text-decoration, so underline and
    // strike ride along as data and are redrawn as <line> elements.
    let deco = "none";
    try {
        const td = String(cs.textDecorationLine || "");
        if (/\bunderline\b/.test(td)) deco = "underline";
        else if (/\bline-through\b/.test(td)) deco = "line-through";
    } catch (e) {}
    // Inline shadow: the conversion destroys the span carrying it, so it
    // must be re-applied per tspan on the fill layer ("none" inherits).
    let shadow = "none";
    try { shadow = cs.textShadow || "none"; } catch (e) {}
    // Nested run outline: innermost wins over the block conversion, so an
    // explicit run outline keeps rendering under a theme outline instead
    // of being silently swallowed by it.
    let ouW = 0, ouC = "";
    try {
        const pe = node.parentElement;
        const oc = (pe && typeof pe.closest === "function")
            ? pe.closest(".rc-oc") : null;
        if (oc) {
            ouW = parseFloat(oc.getAttribute("data-rc-oc-w")) || 0;
            ouC = oc.getAttribute("data-rc-oc-c") || "";
        }
    } catch (e) {}
    // Explicit offs (data-rc-no markers): the conversion replaces the
    // markup carrying text-shadow:none, so the opt-out must ride along
    // as data — otherwise a none-run inherits the block's stroke and
    // shadow inside the SVG.
    let noOutline = false, noShadow = false;
    try {
        const pe = node.parentElement;
        const tagged = (pe && typeof pe.closest === "function")
            ? pe.closest("[data-rc-no]") : null;
        if (tagged) {
            const flags = String(tagged.getAttribute("data-rc-no") || "").split(/\s+/);
            noOutline = flags.indexOf("outline") !== -1;
            noShadow = flags.indexOf("shadow") !== -1;
        }
    } catch (e) {}
    return {
        color: cs.color || "#fff",
        family: cs.fontFamily || "sans-serif",
        size: size,
        weight: String(cs.fontWeight || "400"),
        fontStyle: cs.fontStyle || "normal",
        letterSpacing: ls,
        wordSpacing: parseFloat(cs.wordSpacing) || 0,
        transform: cs.textTransform || "none",
        pre: /pre/.test(cs.whiteSpace || ""),
        deco: deco,
        shadow: shadow,
        ouW: ouW,
        ouC: ouC,
        noOutline: noOutline,
        noShadow: noShadow,
    };
}

function _ocApplyTransform(text, transform) {
    if (transform === "uppercase") return text.toUpperCase();
    if (transform === "lowercase") return text.toLowerCase();
    if (transform === "capitalize") {
        return text.replace(/(?:^|\s)\S/g, (c) => c.toUpperCase());
    }
    return text;
}

// The preview scales its whole DOM to fit the panel (body scale()),
// so getBoundingClientRect returns *scaled* px while canvas and computed
// styles speak unscaled px. Mixing them mis-measures everything (and trips
// the fidelity guard permanently). Normalize rects by the measured scale;
// 1.0 when nothing is transformed (the OBS display).
function _ocScale(el) {
    try {
        // Default to the static verse block, but multi-container themes
        // convert their own panel text while #verse-text is display:none —
        // measuring the hidden node would yield a zero scale and abort.
        const node = el || (typeof verseText !== "undefined" ? verseText : null);
        if (!node) return 0;
        const r = node.getBoundingClientRect();
        const w = node.offsetWidth || 0;
        if (r && r.width > 0 && w > 0) {
            const s = r.width / w;
            if (isFinite(s) && s > 0.05 && s < 20) return s;
        }
    } catch (e) {}
    return 0;
}

function convertOutlineScope(el, width, color) {
    // Rebuild one outlined scope (.rc-oc run, or #verse-text for a block
    // outline) as per-line inline SVGs. True when converted OR when the
    // cached conversion is still current; false leaves the HTML untouched.
    if (!el || typeof document.createTreeWalker !== "function"
        || typeof document.createElementNS !== "function"
        || typeof document.createRange !== "function"
        || typeof NodeFilter !== "undefined" && !NodeFilter.SHOW_TEXT) return false;
    const fontSize = parseFloat(getComputedStyle(el).fontSize) || 0;
    const key = width + "|" + color + "|" + el.textContent + "|"
        + (el.offsetWidth || 0) + "|" + fontSize;
    if (el.dataset.rcOcDone === key) return true;
    // Pristine source: conversion destroys markup, so keep the original to
    // allow re-conversion (theme-only changes carry no fresh HTML).
    if (el.dataset.rcOcSrc === undefined) {
        el.dataset.rcOcSrc = el.innerHTML;
        el.dataset.rcOcW0 = el.getAttribute("data-rc-oc-w") || "";
        el.dataset.rcOcC0 = el.getAttribute("data-rc-oc-c") || "";
    }
    if (el.querySelector("sup, sub")) return false;   // flattening would drop the raise
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    const chars = [];   // {ch, style, rect|null} + {br:true}
    let node, exotic = false;
    while ((node = walker.nextNode())) {
        if (node.nodeType !== 3) {
            const tag = (node.tagName || "").toLowerCase();
            if (tag === "br") chars.push({ br: true });
            else {
                const d = getComputedStyle(node).display;
                if (d && d !== "inline") exotic = true;
            }
            continue;
        }
        const style = _ocSnapshot(node);
        const text = node.nodeValue || "";
        const range = document.createRange();
        for (let i = 0; i < text.length; i++) {
            range.setStart(node, i);
            range.setEnd(node, i + 1);
            let rect = null;
            try {
                const r = range.getBoundingClientRect();
                if (r && (r.width > 0 || r.height > 0)) rect = r;
            } catch (e) { /* detached mid-rebuild: treat as collapsed */ }
            chars.push({ ch: text[i], style: style, rect: rect });
        }
    }
    if (exotic || !chars.length) return false;
    // Group chars into rendered lines (1px tolerance for subpixel jitter).
    const lines = [];
    let line = null;
    for (const c of chars) {
        if (c.br) { line = null; continue; }
        if (c.rect && (!line || Math.abs(line.top - c.rect.top) > 1)) {
            line = { top: c.rect.top, bottom: c.rect.bottom, chars: [] };
            lines.push(line);
        }
        if (!line) {
            line = { top: 0, bottom: 0, chars: [] };
            lines.push(line);
        }
        if (c.rect) {
            line.top = Math.min(line.top, c.rect.top);
            line.bottom = Math.max(line.bottom, c.rect.bottom);
        }
        line.chars.push(c);
    }
    // Whitespace-only lines are collapsed gaps: no ink, no SVG.
    const ink = lines.filter((l) => l.chars.some((c) => c.rect && /\S/.test(c.ch || "")));
    if (!ink.length) return false;
    // Unscale rects to CSS px (see _ocScale): everything downstream meets
    // canvas metrics and computed styles in the same coordinate space.
    const scale = _ocScale(el);
    if (!scale) return false;
    if (scale !== 1) {
        for (const c of chars) {
            if (!c.rect) continue;
            c.rect = { left: c.rect.left / scale, right: c.rect.right / scale,
                       top: c.rect.top / scale, bottom: c.rect.bottom / scale,
                       width: c.rect.width / scale, height: c.rect.height / scale };
        }
    }

    // Plan every line first, validate, then build: conversion must never
    // render worse than plain text, so a line whose rebuilt advance wildly
    // disagrees with its laid-out ink aborts the whole scope (readable HTML
    // stays). Block scopes are full-width while ink is not, hence per-line.
    const plan = [];
    for (let li = 0; li < ink.length; li++) {
        const ln = ink[li];
        let seq = ln.chars.slice();
        while (seq.length && !seq[0].rect) seq.shift();
        while (seq.length && !seq[seq.length - 1].rect) seq.pop();
        while (seq.length && /\s/.test(seq[0].ch)) seq.shift();
        while (seq.length && /\s/.test(seq[seq.length - 1].ch)) seq.pop();
        if (!seq.length) continue;
        const runs = [];
        for (const c of seq) {
            const k = JSON.stringify(c.style);
            const last = runs[runs.length - 1];
            if (last && last.key === k) last.chars.push(c);
            else runs.push({ key: k, style: c.style, chars: [c] });
        }
        const lineH = Math.max(1, ln.bottom - ln.top);
        let ascent = 0, descent = 0;
        const measured = [];
        let failed = false;
        for (const r of runs) {
            let text = r.chars.map((c) => c.ch).join("");
            if (!r.style.pre) text = text.replace(/\s+/g, " ");
            if (!text) continue;
            // Bake the case transform into the SVG text itself: the
            // converted markup inherits the CSS transform, but advances
            // are measured here — measuring untransformed text while the
            // browser renders transformed text drifts every word apart.
            text = _ocApplyTransform(text, r.style.transform);
            // Whitespace-only runs carry no ink: canvas reports a zero
            // ascent for spaces in some fonts, which must never abort the
            // scope — their advances still lay out via tokens below, and
            // the line's ascent/descent come from the inked runs.
            if (!/\S/.test(text)) {
                measured.push({ style: r.style, tokens: _ocTokens(text, r.style) });
                continue;
            }
            const m = _ocMeasure(text, r.style);
            if (!m || !(m.ascent > 0)) { failed = true; break; }
            ascent = Math.max(ascent, m.ascent);
            descent = Math.max(descent, m.descent);
            measured.push({ style: r.style, tokens: _ocTokens(text, r.style) });
        }
        if (failed || !measured.length) return false;   // never drop text
        let inkL = Infinity, inkR = -Infinity;
        for (const c of seq) {
            if (!c.rect) continue;
            if (c.rect.left < inkL) inkL = c.rect.left;
            if (c.rect.right > inkR) inkR = c.rect.right;
        }
        plan.push({ lineH: lineH, ascent: ascent, descent: descent,
                    measured: measured, runs: runs,
                    inkW: (inkR > inkL) ? (inkR - inkL) : 0,
                    builtW: measured.reduce(
                        (a, m) => a + m.tokens.reduce((b, k) => b + k.advance, 0), 0) });
    }
    if (!plan.length) return false;
    for (const p of plan) {
        if (p.inkW > 0 && p.builtW > 0
            && (p.builtW < p.inkW * 0.5 || p.builtW > p.inkW * 1.8)) {
            try { console.warn("outline: metric disagreement, leaving plain text"); }
            catch (e) {}
            return false;
        }
    }
    const frag = document.createDocumentFragment();
    for (let li = 0; li < plan.length; li++) {
        const lineH = plan[li].lineH, ascent = plan[li].ascent,
              descent = plan[li].descent, measured = plan[li].measured,
              runs = plan[li].runs;
        // Tight ink box: exactly as tall as the ink, dropped by the descent
        // so the drawn baseline lands on the parent baseline. A positive
        // vertical-align would RAISE the box and grow every line; this keeps
        // the original line rhythm (and the strut still owns the line box).
        const inkH = ascent + descent;
        const boxH = Math.max(1, Math.ceil(inkH));
        const totalW = plan[li].builtW !== undefined ? plan[li].builtW : 0;
        // The stroke reaches `width` px past the ink on every side, so the
        // viewport is padded by the full outline width: without it the SVG
        // clips the outline into a sharp box. Padding grows the line rhythm
        // (autoFit measures the padded box, so the outline stays inside the
        // container); ink stays exactly where layout put it. A nested run
        // with a WIDER outline than the block pads for itself.
        let pad = width;
        for (const m of measured) {
            if (m.style.ouW > pad) pad = m.style.ouW;
        }
        const svg = document.createElementNS(_OC_SVG_NS, "svg");
        svg.setAttribute("width", String(Math.max(1, Math.ceil(totalW + 2 * pad))));
        svg.setAttribute("height", String(boxH + 2 * pad));
        // Belt and braces: the viewport sizes layout, but must never clip
        // paint. A few px of raster reality (hinting, rounding, font-metric
        // gaps) can exceed the measured ink box; with overflow visible the
        // outline simply paints instead of slicing glyph tops.
        svg.style.overflow = "visible";
        svg.style.verticalAlign = String(-(descent + pad)) + "px";
        // Two <text> layers: ALL strokes first, then ALL fills. Chromium
        // applies paint-order per tspan, so a single text element would let
        // each later word's stroke bury earlier words' fills wherever the
        // stroke reaches (at 200px: everything). Document order here gives
        // true stroke-then-fill semantics at any width or word count.
        const mkText = function (forStroke) {
            const t = document.createElementNS(_OC_SVG_NS, "text");
            t.setAttribute("y", (boxH - descent + pad).toFixed(2));
            t.setAttribute("font-size", String(runs[0].style.size));
            if (forStroke) {
                t.setAttribute("fill", "none");
                t.setAttribute("stroke", color);
                t.setAttribute("stroke-width", String(2 * width));
                t.setAttribute("stroke-linejoin", "round");
                t.setAttribute("stroke-linecap", "round");
            } else {
                t.setAttribute("stroke", "none");
            }
            return t;
        };
        // The stroke layer is pure paint: hide it from assistive tech so
        // the words are read once, not twice (textContent still sees both;
        // that duplication is inherent to the two-layer technique).
        const strokeEl = mkText(true), fillEl = mkText(false);
        strokeEl.setAttribute("aria-hidden", "true");
        // Only the fill casts: the stroke copy is fatter than the glyphs
        // by the outline width, so its shadow would start further out and
        // land on top of the fill's own — the "shadow moved" double cast.
        strokeEl.style.textShadow = "none";
        let x = pad;
        const decos = [];
        const baseY = boxH - descent + pad;
        for (const m of measured) {
            // SVG text cannot do text-decoration: redraw underline and
            // strike as lines over the fill, positioned from the font
            // size the way browsers place them.
            const runX0 = x;
            for (const k of m.tokens) {
                if (k.text) {
                    const ouW = (m.style.ouW > 0) ? m.style.ouW : width;
                    const ouC = m.style.ouC || color;
                    for (const layer of [0, 1]) {
                        if (layer === 0 && m.style.noOutline) continue;
                        const ts = document.createElementNS(_OC_SVG_NS, "tspan");
                        ts.setAttribute("x", x.toFixed(2));
                        ts.setAttribute("font-family", m.style.family);
                        ts.setAttribute("font-weight", m.style.weight);
                        ts.setAttribute("font-style", m.style.fontStyle);
                        ts.textContent = k.text;
                        if (layer === 0) {
                            ts.setAttribute("fill", "none");
                            ts.setAttribute("stroke", ouC);
                            ts.setAttribute("stroke-width", String(2 * ouW));
                            ts.setAttribute("stroke-linejoin", "round");
                            ts.setAttribute("stroke-linecap", "round");
                            strokeEl.appendChild(ts);
                        } else {
                            ts.setAttribute("fill", m.style.color);
                            ts.setAttribute("stroke", "none");
                            if (m.style.shadow && m.style.shadow !== "none") {
                                ts.style.textShadow = m.style.shadow;
                            } else if (m.style.noShadow) {
                                ts.style.textShadow = "none";
                            }
                            fillEl.appendChild(ts);
                        }
                    }
                }
                x += k.advance;
            }
            if (m.style.deco === "underline" || m.style.deco === "line-through") {
                const size = m.style.size || 16;
                const dy = (m.style.deco === "underline") ? size * 0.10 : -size * 0.26;
                decos.push({ x0: runX0, x1: x, y: baseY + dy,
                             color: m.style.color,
                             w: Math.max(1.2, size * 0.055) });
            }
        }
        svg.appendChild(strokeEl);
        svg.appendChild(fillEl);
        for (const d of decos) {
            const ln = document.createElementNS(_OC_SVG_NS, "line");
            ln.setAttribute("x1", d.x0.toFixed(2));
            ln.setAttribute("x2", d.x1.toFixed(2));
            ln.setAttribute("y1", d.y.toFixed(2));
            ln.setAttribute("y2", d.y.toFixed(2));
            ln.setAttribute("stroke", d.color);
            ln.setAttribute("stroke-width", d.w.toFixed(2));
            ln.setAttribute("stroke-linecap", "round");
            svg.appendChild(ln);
        }
        frag.appendChild(svg);
        if (li < plan.length - 1) frag.appendChild(document.createElement("br"));
    }
    el.textContent = "";
    el.appendChild(frag);
    el.dataset.rcOcDone = key;
    return true;
}

// Restore pre-conversion markup so measuring and (re)conversion always
// start from pristine text. Per-payload innerHTML replacement already drops
// converted nodes, but auto-fit, theme-only changes and font arrival all
// re-enter conversion on the SAME nodes: without this they would measure
// padded SVGs (auto-fit over-shrinks) or find no markers left to convert.
function invalidateOutlines() {
    if (typeof verseText === "undefined" || !verseText) return;
    const restore = function (el) {
        el.innerHTML = el.dataset.rcOcSrc;
        if (el.dataset.rcOcW0) {
            el.classList.add("rc-oc");
            el.setAttribute("data-rc-oc-w", el.dataset.rcOcW0);
            el.setAttribute("data-rc-oc-c", el.dataset.rcOcC0 || "#000");
        }
        delete el.dataset.rcOcDone;
    };
    if (verseText.dataset.rcOcSrc !== undefined) {
        restore(verseText);
        return;
    }
    verseText.querySelectorAll("span").forEach(function (el) {
        if (el.dataset.rcOcSrc !== undefined) restore(el);
    });
}

function applyOutlineLayers() {
    const root = document.documentElement;
    const deck = (root.style.getPropertyValue("--rc-text-outline-value") || "").trim();
    const theme = (root.style.getPropertyValue("--rc-text-outline") || "").trim();
    if (!verseText) return;
    const block = _outlineParts(deck || theme);
    // Stale artifacts from older payloads must never survive: the block
    // element persists across payloads while its children do not.
    verseText.classList.remove("rc-oc");
    verseText.removeAttribute("data-rc-oc");
    verseText.style.removeProperty("--rc-oc-stroke");
    if (block && block !== "none") {
        // One conversion keeps every nested color, and the verseText stash
        // keeps nested run markers so a later invalidate can still restore
        // them. A nested run outline wins over the block for its own words
        // (innermost wins, like the cascade); the stroke layer carries it
        // per tspan. Runs marked data-rc-no opt out of the stroke and/or
        // the inherited shadow, so explicit offs survive the conversion.
        convertOutlineScope(verseText, block.width, block.color);
        return;
    }
    verseText.querySelectorAll(".rc-oc").forEach(function (el) {
        const w = parseFloat(el.getAttribute("data-rc-oc-w"));
        const c = el.getAttribute("data-rc-oc-c") || "#000";
        // Markers come off only on success, so a failed scope (exotic
        // content, no layout yet) is retried on the next pass.
        if (w > 0 && convertOutlineScope(el, w, c)) {
            el.classList.remove("rc-oc");
            el.removeAttribute("data-rc-oc");
            el.removeAttribute("data-rc-oc-w");
            el.removeAttribute("data-rc-oc-c");
        }
    });
}



function _outlineParts(value) {
    // A stored outline -> {width, color} for the layered outline, or null.
    const raw = String(value == null ? "" : value).trim();
    if (!raw || raw.toLowerCase() === "none" || raw.toLowerCase() === "off") return null;
    const m = /^(\d+(?:\.\d+)?)px\s+(#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?)$/i.exec(raw);
    const hex = (c) => { let d = String(c || "").replace("#", "");
                         if (d.length === 3) d = d.split("").map(x => x + x).join("");
                         return "#" + d.toLowerCase(); };
    // Bounds are OUTLINE_MIN_PX..OUTLINE_MAX_PX from core/constants.py (pinned by test_outline_width_bounds_match_core_constants).
    if (m) return { width: Math.max(1, Math.min(12, Math.round(parseFloat(m[1])))), color: hex(m[2]) };
    const c = _parseInlineColor(raw);
    return c ? { width: 1, color: c } : null;
}


function _colorA(color, alpha) {
    const d = color.replace("#", "");
    const r = parseInt(d.slice(0, 2), 16), g = parseInt(d.slice(2, 4), 16),
          b = parseInt(d.slice(4, 6), 16);
    return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
}

// "none"/"off"/blank, or every numeric knob at zero (offsets, blur,
// opacity, distance, angle — hex colors stripped first so #000000 does
// not read as knobs). An all-zero shadow paints nothing, so say so
// explicitly instead of emitting invalid CSS the browser drops.
function _shadowIsNone(value) {
    const v = String(value == null ? "" : value).trim();
    if (!v || /^(none|off)$/i.test(v)) return true;
    const nums = v.replace(/#[0-9a-fA-F]{3,6}/g, " ").match(/-?[\d.]+/g) || [];
    return nums.length > 0 && nums.every(n => parseFloat(n) === 0);
}

// "8px 40% 3px #000000" -> {size, opacity, distance, color} | null
function _parseShadow(value) {
    const v = String(value == null ? "" : value).trim();
    if (!v) return null;
    if (v.toLowerCase() === "none" || v.toLowerCase() === "off") return "none";
    const parts = v.split(/\s+/);
    // Trailing angle comes after the color ("... #hex 135"): a bare number
    // (or Ndeg) that is not a color. Defaults to 45 (down-right).
    let angle = 45;
    if (parts.length && parts[parts.length - 1].charAt(0) !== "#") {
        let tok = String(parts.pop()).toLowerCase();
        if (tok.endsWith("deg")) tok = tok.slice(0, -3);
        angle = Math.round(parseFloat(tok));
        if (isNaN(angle)) return null;
        angle = ((angle % 360) + 360) % 360;
    }
    let color = null;
    if (parts.length && parts[parts.length - 1].charAt(0) === "#") {
        color = _parseInlineColor(parts.pop());
        if (!color) return null;
    }
    const px = (tok) => {
        const s = String(tok).toLowerCase().endsWith("px")
            ? String(tok).slice(0, -2) : String(tok);
        const n = parseFloat(s);
        return isNaN(n) ? null : Math.round(n);
    };
    let size = null;
    if (parts.length) { size = px(parts.shift()); if (size === null) return null; }
    let opacity = 100;
    if (parts.length) {
        const tok = parts.shift();
        if (!/%$/.test(tok)) return null;
        opacity = Math.round(parseFloat(tok));
        if (isNaN(opacity)) return null;
    }
    let distance = 0;
    if (parts.length) { distance = px(parts.shift()); if (distance === null) return null; }
    if (parts.length) return null;                       // trailing junk
    if (!color || (size === null && opacity === 100 && distance === 0)) return null;
    if (size === null) size = 8;
    return {
        size: Math.max(1, Math.min(12, size)),
        opacity: Math.max(0, Math.min(100, opacity)),
        distance: Math.max(0, Math.min(12, distance)),
        color: color,
        angle: angle,
    };
}

// A hard text-shadow ring at a given thickness, opacity, distance and
// direction (degrees, 0 = east, 90 = south). distance 0 hugs the glyphs
// (an outline drawn in shadow).
function _shadowRing(sh) {
    // One blurred, offset shadow (classic text-shadow look). The old ring
    // stamped filled glyph copies, so stacked letter shapes showed instead
    // of a shadow. `size` is the blur radius here; distance/angle displace
    // the single copy (distance 0 reads as an outer glow).
    const alpha = Math.round(Math.max(0, Math.min(100, sh.opacity)) / 100 * 1000) / 1000;
    const rad = ((sh.angle === undefined ? 45 : sh.angle)) * Math.PI / 180;
    const dx = Math.round(sh.distance * Math.cos(rad));
    const dy = Math.round(sh.distance * Math.sin(rad));
    const blur = Math.max(0, sh.size);
    const paint = alpha >= 1 ? sh.color : _colorA(sh.color, alpha);
    return dx + "px " + dy + "px " + blur + "px " + paint;
}

function _shadowCss(value) {
    const sh = _parseShadow(value);
    if (!sh || sh === "none") return "";
    return "text-shadow:" + _shadowRing(sh);
}

function _themeOutline(t) {
    // A theme's outline is ONE property ("2px #000000"), the same knob a deck
    // run sets, so `outline=12` in the txt broadens it and `outline=none`
    // switches it off. Themes may declare `text_outline` directly, or keep
    // the legacy hard multi-direction `text_shadow`, which is an outline in
    // disguise (single color, zero blur) and is converted. Real drop shadows
    // (blur > 0, mixed colors) stay drop shadows.
    // Returns the canonical VALUE ("4px #000000"), never rendered CSS:
    // applyOutlineLayers() parses it with _outlineParts and builds the SVG.
    const explicit = String((t && t.text_outline) || "").trim();
    if (explicit) {
        // An explicit "none" is a decision, not an absence: outline off even
        // when a legacy hard text_shadow is present (it renders literally).
        if (explicit.toLowerCase() === "none" || explicit.toLowerCase() === "off") return "";
        const oc = _outlineParts(explicit);
        if (oc) return oc.width + "px " + oc.color;
    }
    const shadow = String((t && t.text_shadow) || "").trim();
    if (!shadow || shadow.toLowerCase() === "none") return "";
    let axis = 0, diagonal = 0;
    const colors = {};
    for (const part of shadow.split(",")) {
        const m = /^\s*(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(#[0-9a-fA-F]{3,6})\s*$/i.exec(part);
        if (!m || parseFloat(m[3]) !== 0) return "";   // blur: a drop shadow
        const dx = parseFloat(m[1]), dy = parseFloat(m[2]);
        const mag = Math.sqrt(dx * dx + dy * dy);
        if (dy === 0) axis = Math.max(axis, Math.abs(dx));
        else if (dx === 0) axis = Math.max(axis, Math.abs(dy));
        else diagonal = Math.max(diagonal, mag);
        const c = _parseInlineColor(m[4]);
        if (!c) return "";
        colors[c] = true;
    }
    const keys = Object.keys(colors);
    if (keys.length !== 1) return "";
    // An 8-direction outline spells its thickness out on the axes; only fall
    // back to the corner magnitude when there are no axis offsets.
    const thickness = axis || diagonal;
    if (!(thickness > 0)) return "";
    return Math.min(12, Math.max(1, Math.round(thickness))) + "px " + keys[0];
}

function _outlineRing(value) {
    // The outline is a ring of hard text shadows, NOT -webkit-text-stroke:
    // a stroke straddles the glyph outline so half of it grows inwards and
    // eats the letterform (at 25px the word stops being readable). Shadows
    // only sit outside the glyph, and every shadow is painted before any
    // glyph fill, so a letter's outline ends up behind its neighbours'
    // fills instead of smearing over them. The ring resolution scales with
    // the thickness so the outer contour stays smooth, capped at 48.
    const raw = String(value == null ? "" : value).trim();
    let px = 1, color = null;
    const m = /^(\d+(?:\.\d+)?)px\s+(#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?)$/i.exec(raw);
    // Normalize 3-digit hex exactly like the Python parser does, so the three
    // renderers cannot drift on the same stored value.
    const hex = (c) => { let d = String(c || "").replace("#", "");
                         if (d.length === 3) d = d.split("").map(x => x + x).join("");
                         return "#" + d.toLowerCase(); };
    if (m) { px = parseFloat(m[1]); color = hex(m[2]); }
    else { color = _parseInlineColor(raw); }
    if (!color) return "";
    const r = Math.max(1, Math.min(12, Math.round(px)));
    const STEPS = Math.min(48, Math.max(12, Math.round(r * 1.9)));
    const parts = [], seen = {};
    for (let i = 0; i < STEPS; i++) {
        const a = (Math.PI * 2 * i) / STEPS;
        const dx = Math.round(Math.cos(a) * r);
        const dy = Math.round(Math.sin(a) * r);
        if (!dx && !dy) continue;   // dead-centre shadow would be invisible
        const key = dx + "," + dy;
        if (seen[key]) continue;    // small radii round several angles together
        seen[key] = true;
        parts.push(dx + "px " + dy + "px 0 " + color);
    }
    return parts.join(",");
}

function _outlineCss(value) {
    // The theme's own soft drop shadow rides along so an outlined run does
    // not lose the depth the un-outlined runs keep.
    const ring = _outlineRing(value);
    if (!ring) return "";
    return "text-shadow:" + ring
        + ",var(--rc-text-shadow,0 4px 12px rgba(0,0,0,0.4))";
}

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
            // legacy color-only ("#ff0000"), explicit thickness+color
            // ("2px #ff0000"), or an explicit off ("none"/"off").
            const v = String(value || "").trim();
            const low = v.toLowerCase();
            if (low === "none" || low === "off") {
                // Explicit off: the deck overrides an inherited outline.
                params.outline = "none"; found = true;
            } else if (_outlineRing(v)) {
                params.outline = v; found = true;
            }
        } else if (key === "shadow") {
            // "<size>px [opacity%] [distance px] #hex"; opacity/distance are
            // optional, "none" is an explicit off.
            const sh = _parseShadow(value);
            if (sh === "none") { params.shadow = "none"; found = true; }
            else if (sh) { params.shadow = value; found = true; }
        } else if (key === "font") {
            const v = (value || "").replace(/[;()\[\]"']/g, "").trim();
            if (v && v.length <= 60) { params.font = v; found = true; }
        }
    }
    return found ? params : null;
}

function spanStyle(p) {
    // Shared contract with core/slide_parser._span_style — keep in sync.
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
    // An outline needs a duplicated stroke layer (see .rc-oc in the
    // stylesheet), so it is NOT emitted here; _outlineRun() builds it from
    // p.outline once the run element exists.
    if (p.outline === "none") {
        // Explicit off: drop any inherited outline and shadow for this run.
        styles.push("text-shadow:none");
    }
    if (p.shadow === "none") {
        styles.push("text-shadow:none");
    } else if (p.shadow) {
        const sc = _shadowCss(p.shadow);
        if (sc) styles.push(sc);
    }
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
                        // An outline becomes a duplicated stroke layer behind
                        // the glyphs; everything else rides the inline style.
                        // Explicit offs ride as data markers: the block SVG
                        // conversion destroys the inline text-shadow:none,
                        // so it must know which runs opted out of the
                        // stroke and of the inherited shadow.
                        const noAttrs = [];
                        if (parsed.outline === "none") noAttrs.push("outline");
                        if (parsed.shadow === "none") noAttrs.push("shadow");
                        const noStr = noAttrs.length
                            ? ' data-rc-no="' + noAttrs.join(" ") + '"' : "";
                        const body = (parsed.outline && parsed.outline !== "none")
                            ? _outlineRun(inner, _attrEscape(disp), parsed.outline)
                            : inner;
                        out += '<span' + noStr + ' style="' + spanStyle(parsed) + '">' + body + '</span>';
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

// Source fields compared per block for transition triggering. A re-broadcast
// with the same words (theme restyle, queue refresh) must stay silent.
function _payloadSources(payload) {
    const s = { text: "", reference: "", translation: "", title: "" };
    if (!payload || payload.action !== "display") return s;
    s.text = payload.text == null ? "" : String(payload.text);
    s.title = payload.title == null ? "" : String(payload.title);
    if (payload.reference != null) {
        s.reference = String(payload.reference);
    } else if (payload.book && payload.chapter && payload.verse) {
        s.reference = payload.book + " " + payload.chapter + ":" + payload.verse;
    } else if (payload.ref != null) {
        const m = String(payload.ref).match(/^\[([^\]]+)\]\s*(.+)$/);
        if (m) {
            s.reference = m[2];
            if (payload.translation == null) s.translation = m[1];
        } else {
            s.reference = String(payload.ref);
        }
    }
    if (payload.translation != null) s.translation = String(payload.translation);
    return s;
}

function _changedSources(previous, current) {
    const a = _payloadSources(previous);
    const b = _payloadSources(current);
    const changed = {
        text: a.text !== b.text,
        reference: a.reference !== b.reference,
        translation: a.translation !== b.translation,
        title: a.title !== b.title,
    };
    changed.any = changed.text || changed.reference
        || changed.translation || changed.title;
    return changed;
}

function _renderDisplay(data, silent, changed, phase) {
    _cancelAllAnimations();
    if (data.text) {
        let verseTextContent = renderInlineColors(data.text);
        const refText = data.reference || (data.book && data.chapter && data.verse
            ? data.book + " " + data.chapter + ":" + data.verse
            : null);
        const verseNum = extractVerseNumber(refText);
        if (verseNum) {
            verseTextContent = '<span class="verse-num">' + verseNum + '</span> ' + verseTextContent;
        }
        verseText.innerHTML = verseTextContent;
        delete verseText.dataset.rcOcSrc;
        delete verseText.dataset.rcOcDone;
        delete verseText.dataset.rcSplit;
        delete verseText.dataset.rcSplitSrc;
        delete verseText.dataset.rcSplitUnits;
        delete verseText.dataset.rcSplitAnimated;
    }

    if (data.reference) {
        verseRefText.innerHTML = data.reference;
    } else if (data.book && data.chapter && data.verse) {
        verseRefText.innerHTML = data.book + " " + data.chapter + ":" + data.verse;
    } else if (data.ref) {
        const m = data.ref.match(/^\[([^\]]+)\]\s*(.+)$/);
        if (m) {
            verseRefTranslation.innerHTML = m[1];
            verseRefText.innerHTML = m[2];
        } else {
            verseRefText.innerHTML = data.ref;
        }
    } else {
        verseRefText.innerHTML = "";
    }

    if (data.translation) {
        verseRefTranslation.innerHTML = data.translation;
    } else if (!data.ref) {
        verseRefTranslation.innerHTML = "";
    }

    const refEmpty = !verseRefText.textContent.trim()
        && !verseRefTranslation.textContent.trim();
    verseRef.style.display = refEmpty ? "none" : "";
    verseText.style.marginBottom = refEmpty ? "0px" : "";

    resetTheme();
    if (data.theme_data) {
        applyTheme(data.theme_data, data.slide_format);
        document.body.className = "";
    } else if (data.theme) {
        document.body.className = "theme-" + data.theme;
    }

    if (_currentContainers && _currentContainers.length > 1) {
        _renderMultiContainers(data);
    } else {
        container.classList.remove("hidden");
        autoFitText();
        _populateContainers(data);
    }

    _layoutSplitUnits(_currentTheme);

    if (!silent) {
        if (phase) _runAnimation(phase, changed);
        _prevPayload = data;
    }
}

function handlePayload(data, silent) {
    if (data.action === "clear") {
        _cancelAllAnimations();
        if (silent) {
            container.classList.add("hidden");
            container.style.animation = "";
            if (typeof document !== "undefined" && document.querySelectorAll) {
                document.querySelectorAll(".rc-dynamic-container").forEach(el => el.classList.add("hidden"));
            }
            _prevPayload = null;
            return;
        }
        _runExitAnimation(() => {
            container.classList.add("hidden");
            container.style.animation = "";
            if (typeof document !== "undefined" && document.querySelectorAll) {
                document.querySelectorAll(".rc-dynamic-container").forEach(el => el.classList.add("hidden"));
            }
            _cancelAllAnimations();
        });
        _prevPayload = null;
        return;
    }

    if (data.action !== "display") return;

    const previous = _prevPayload;
    const changed = _changedSources(previous, data);
    // entry: first content (or after a clear). in: content actually changed.
    // Same content re-broadcast (theme restyle, queue refresh) is silent.
    let phase = "entry";
    if (previous && previous.action === "display") {
        phase = changed.any ? "in" : null;
    }

    if (!silent) {
        _cancelAllAnimations();
        if (phase === "in") {
            // §4.9.3: play the old content out first, then swap and re-fit.
            const plan = _collectTransitionOut(_currentTheme, changed);
            if (plan.length) {
                let total = 0;
                plan.forEach(p => {
                    _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "out" });
                    total = Math.max(total, _phaseDuration(p.def));
                });
                if (total > 0) {
                    const token = _phaseToken;
                    _phaseTimer = setTimeout(() => {
                        _phaseTimer = null;
                        if (token === _phaseToken) {
                            _renderDisplay(data, silent, changed, phase);
                        }
                    }, total);
                    return;
                }
            }
        }
    }
    _renderDisplay(data, silent, changed, phase);
}

function refreshPayload(data) {
    return new Promise(function(resolve) {
        handlePayload(data, true);
        requestAnimationFrame(function() {
            requestAnimationFrame(function() { resolve(1); });
        });
    });
}

function refreshClear() {
    return new Promise(function(resolve) {
        handlePayload({action: "clear"}, true);
        requestAnimationFrame(function() {
            requestAnimationFrame(function() { resolve(1); });
        });
    });
}


if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
        try {
            // Split markup changes measured height; lay the text back out
            // before refitting, then re-split at the final metrics.
            _unsplitAll();
            invalidateOutlines();
            // Bundled faces land after the first fit; re-fit v2 min_height
            // panels so autosized text matches the final metrics.
            if (_currentTheme && _currentTheme.schema_version === 2) {
                autoFitText();
                if (_currentContainers && _currentContainers.length > 1) _autoFitPanels();
            }
            applyOutlineLayers();
            _layoutSplitUnits(_currentTheme);
        } catch (e) {}
    });
}

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
        self._pending_cb = None
        self._pending_js = None  # (js, callback) silent-refresh queued pre-load
        # Render-only surface: must never steal keyboard focus (page
        # loads/flushes otherwise yank focus out of the editors mid-flow).
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)

        # The preview is a black viewport. The page CSS is transparent for
        # OBS, so without an explicit page color QtWebEngine composites it
        # over white. The white-screen toggle paints over this on demand.
        self.page().setBackgroundColor(QColor("#000000"))

        self.setHtml(_DISPLAY_HTML, QUrl("http://localhost"))
        self.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool):
        self._page_ready = ok
        if ok and self._live_mode:
            self.page().runJavaScript("connect()")
        if ok and self._pending_payload is not None:
            payload = self._pending_payload
            cb = self._pending_cb
            self._pending_payload = None
            self._pending_cb = None
            self._run_payload(payload, cb)
        if ok and self._pending_js is not None:
            js, cb = self._pending_js
            self._pending_js = None
            self._run_js(js, cb)

    def display_verse(self, payload: dict):
        """Display a verse. payload matches the WS broadcast format:
        {action: "display", text, reference, translation, theme_data, ...}
        """
        self._run_payload(payload)

    def clear(self):
        """Hide the verse container with animation."""
        self._run_payload({"action": "clear"})

    def set_screen_white(self, on: bool):
        """Preview-only canvas override: white screen behind the render, or
        back to the page default. Page-level inline style (important), so
        payloads, theme changes and resets never disturb it — and it is never
        sent anywhere, so OBS output is unaffected. Queued pre-load like any
        other JS injection."""
        self._screen_white = on
        # Both root and body: the page stylesheet paints body black, which
        # would otherwise cover a root-only override everywhere but a strip.
        if on:
            js = ("document.documentElement.style.setProperty("
                  "'background', '#ffffff', 'important');"
                  "document.body.style.setProperty("
                  "'background', '#ffffff', 'important');")
        else:
            js = ("document.documentElement.style.removeProperty("
                  "'background');"
                  "document.body.style.removeProperty('background');")
        self._run_js(js)

    def apply_theme(self, theme_data: dict):
        """Apply a theme without changing the displayed content."""
        if not self._page_ready:
            return
        js = "applyTheme(" + json.dumps(theme_data) + ")"
        self.page().runJavaScript(js)

    def _run_payload(self, payload: dict, callback=None):
        """Execute handlePayload() with the given payload in the page."""
        if not self._page_ready:
            self._pending_payload = payload
            self._pending_cb = callback
            return
        js = "handlePayload(" + json.dumps(payload) + ")"
        if callback is None:
            self.page().runJavaScript(js)
        else:
            self.page().runJavaScript(js, callback)

    def refresh(self, payload: dict, callback=None):
        """Silent re-push for tab-switch resync: full render, no
        animations, transition memory untouched. callback fires after
        2 presented frames carry the update (or on page load if the
        view wasn't ready)."""
        self._run_js("refreshPayload(" + json.dumps(payload) + ")", callback)

    def refresh_clear(self, callback=None):
        """Silent blank for tab-switch resync (same frame-ack contract)."""
        self._run_js("refreshClear()", callback)

    def _run_js(self, js: str, callback=None):
        if not self._page_ready:
            self._pending_js = (js, callback)
            return
        if callback is None:
            self.page().runJavaScript(js)
        else:
            self.page().runJavaScript(js, callback)
