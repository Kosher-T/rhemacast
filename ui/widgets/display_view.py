"""
ui/widgets/display_view.py

QWebEngineView wrapper that renders verses using the same HTML/CSS/JS as OBS.
Live mode connects to WebSocket; Preview mode receives content via JS injection.
"""

import json
import logging

from PyQt6.QtCore import Qt, QUrl
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
document.fonts.ready.then(() => { try { applyOutlineLayers(); } catch (e) {} });

// Inline run markup: [words (k=v; k=v)] → <span>. Payloads arrive
// HTML-escaped by sanitize_payload(); conversion happens here at render
// time (same contract as display/display.js — keep the two in sync).
const _INLINE_TRUE = new Set(["true", "1", "yes"]);
const _INLINE_FALSE = new Set(["false", "0", "no"]);
const _INLINE_KEYS = new Set(["size", "bold", "color", "italics", "case",
    "underline", "strike", "align", "spacing", "super", "sub",
    "outline", "shadow", "dir", "hr", "font"]);

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
                        const body = (parsed.outline && parsed.outline !== "none")
                            ? _outlineRun(inner, _attrEscape(disp), parsed.outline)
                            : inner;
                        out += '<span style="' + spanStyle(parsed) + '">' + body + '</span>';
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
}

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
            text = _ocApplyTransform(text, r.style.transform);
            if (!text) continue;
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
        // container); ink stays exactly where layout put it.
        const pad = width;
        const svg = document.createElementNS(_OC_SVG_NS, "svg");
        svg.setAttribute("width", String(Math.max(1, Math.ceil(totalW + 2 * pad))));
        svg.setAttribute("height", String(boxH + 2 * pad));
        svg.style.verticalAlign = String(-(descent + pad)) + "px";
        const textEl = document.createElementNS(_OC_SVG_NS, "text");
        textEl.setAttribute("y", (boxH - descent + pad).toFixed(2));
        textEl.setAttribute("font-size", String(runs[0].style.size));
        textEl.setAttribute("stroke", color);
        textEl.setAttribute("stroke-width", String(2 * width));
        textEl.setAttribute("paint-order", "stroke fill");
        textEl.setAttribute("stroke-linejoin", "round");
        textEl.setAttribute("stroke-linecap", "round");
        let x = pad;
        for (const m of measured) {
            for (const k of m.tokens) {
                if (k.text) {
                    const ts = document.createElementNS(_OC_SVG_NS, "tspan");
                    ts.setAttribute("x", x.toFixed(2));
                    ts.setAttribute("fill", m.style.color);
                    ts.setAttribute("font-family", m.style.family);
                    ts.setAttribute("font-weight", m.style.weight);
                    ts.setAttribute("font-style", m.style.fontStyle);
                    ts.textContent = k.text;
                    textEl.appendChild(ts);
                }
                x += k.advance;
            }
        }
        svg.appendChild(textEl);
        frag.appendChild(svg);
        if (li < plan.length - 1) frag.appendChild(document.createElement("br"));
    }
    el.textContent = "";
    el.appendChild(frag);
    el.dataset.rcOcDone = key;
    return true;
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
        // Outermost wins: one conversion keeps every nested color; nested
        // run outlines defer to the block value.
        verseText.querySelectorAll(".rc-oc").forEach(function (n) {
            n.classList.remove("rc-oc");
        });
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
    if (m) return { width: Math.max(1, Math.min(25, Math.round(parseFloat(m[1])))), color: hex(m[2]) };
    const c = _parseInlineColor(raw);
    return c ? { width: 1, color: c } : null;
}

// One inline run with a true outward outline: a stroke-only copy behind the
// opaque glyphs. `inner` is the already-escaped run content (may hold <sup>,
// <sub>); `plain` is the text the copy repeats.
function _colorA(color, alpha) {
    const d = color.replace("#", "");
    const r = parseInt(d.slice(0, 2), 16), g = parseInt(d.slice(2, 4), 16),
          b = parseInt(d.slice(4, 6), 16);
    return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
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
        size: Math.max(1, Math.min(25, size)),
        opacity: Math.max(0, Math.min(100, opacity)),
        distance: Math.max(0, Math.min(60, distance)),
        color: color,
        angle: angle,
    };
}

// A hard text-shadow ring at a given thickness, opacity, distance and
// direction (degrees, 0 = east, 90 = south). distance 0 hugs the glyphs
// (an outline drawn in shadow).
function _shadowRing(sh) {
    const steps = Math.min(48, Math.max(12, Math.round(sh.size * 1.9)));
    const alpha = Math.round(Math.max(0, Math.min(100, sh.opacity)) / 100 * 1000) / 1000;
    const rad = (sh.angle || 45) * Math.PI / 180;
    const ox = Math.round(sh.distance * Math.cos(rad));
    const oy = Math.round(sh.distance * Math.sin(rad));
    const paint = alpha >= 1 ? sh.color : _colorA(sh.color, alpha);
    const parts = [], seen = {};
    for (let i = 0; i < steps; i++) {
        const a = (Math.PI * 2 * i) / steps;
        const dx = Math.round(Math.cos(a) * sh.size) + ox;
        const dy = Math.round(Math.sin(a) * sh.size) + oy;
        const key = dx + "," + dy;
        if (seen[key]) continue;
        seen[key] = true;
        parts.push(dx + "px " + dy + "px 0 " + paint);
    }
    return parts.join(",");
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
    return Math.min(25, Math.max(1, Math.round(thickness))) + "px " + keys[0];
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
    const r = Math.max(1, Math.min(25, Math.round(px)));
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
    // The theme's outline (explicit text_outline, or a hard text_shadow in
    // disguise) drives the same property a deck's outline= does, so a deck can
    // broaden it or switch it off. A genuine drop shadow stays a drop shadow.
    const tOutline = _themeOutline(t);
    if (tOutline) root.style.setProperty("--rc-text-outline", tOutline);
    const tShadow = tOutline ? "" : String(t.text_shadow || "").trim();
    if (tShadow) root.style.setProperty("--rc-text-shadow", tShadow);
    // A theme-only change carries no fresh text: restore pristine markup so
    // the new metrics reconvert below instead of persisting stale SVGs.
    try {
        if (verseText && verseText.dataset.rcOcSrc !== undefined) {
            verseText.innerHTML = verseText.dataset.rcOcSrc;
            delete verseText.dataset.rcOcSrc;
            delete verseText.dataset.rcOcDone;
        }
    } catch (e) {}
    if (typeof applyOutlineLayers === "function") applyOutlineLayers();
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
    // Deck outline: absent -> the theme's outline stays; "none" -> off.
    // Deck outline (absent -> the theme's outline applies; "none" -> off).
    const deckOutline = (f.outline && f.outline !== "none") ? f.outline
                        : (f.outline === "none" ? "none" : null);
    if (deckOutline) root.style.setProperty("--rc-text-outline-value", deckOutline);
    else root.style.removeProperty("--rc-text-outline-value");
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
        // No fitting to do, but the outline still needs (re)building: layout
        // is measurable here (callers invoke autoFitText once visible).
        applyOutlineLayers();
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
    applyOutlineLayers();   // the outline copy must track the fitted size
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

function handlePayload(data, silent) {
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
            // No conversion here: the theme is not applied yet (and the
            // container may still be hidden), so metrics would be stale and
            // the markers consumed. Conversion runs post-theme at the end of
            // autoFitText, which always follows below once visible.
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
        
        // Contract three-step: reset is UNCONDITIONAL — a payload without
        // theme_data renders CSS fallbacks, never leftover variables.
        resetTheme();
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

// Silent resync (mirror of display.js): full render, no animation
// state, resolves after 2 presented frames so the caller can reveal
// the view knowing current content is on screen.
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
        self._pending_cb = None
        self._pending_js = None  # (js, callback) silent-refresh queued pre-load
        # Render-only surface: must never steal keyboard focus (page
        # loads/flushes otherwise yank focus out of the editors mid-flow).
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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
