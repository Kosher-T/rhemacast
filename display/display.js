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
            handlePayload(data, !!(data && data.silent));
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
        "--rc-container-bg", "--rc-border-fill", "--rc-container-border",
        "--rc-border-radius",
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
        // The ring and border fill live on the layer, so clearing only the
        // container would leave the old theme's paint on screen.
        const layer = _borderLayer(container);
        if (layer) {
            layer.removeAttribute("style");
            layer.innerHTML = "";
        }
        // Border shadow hosts are siblings of their container, so a reset
        // that only cleared the container would leave one painted on the
        // canvas.
        if (typeof document !== "undefined" && document.querySelectorAll) {
            document.querySelectorAll(".rc-border-shadow").forEach(
                el => el.remove());
            container.__rcBorderShadow = null;
        }
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
    if (!el || !el.style) return;
    if (border == null) {
        // No authored border means no ring at all: the stylesheet default is
        // a fallback for themes that never ran through applyTheme.
        el.style.border = "none";
        return;
    }
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

// ─── Container paint layers ─────────────────────────────────────────────
// A container paints two things, in order:
//   1. its own background — the full assigned rectangle, square corners,
//      painted first (`container_background`);
//   2. a border layer — the border shape alone, inset by `border_padding`,
//      carrying the border fill (`background`) and the radius.
// The layer is a real child element, not a pseudo-element, so per-side
// borders, string shorthands and the `border.draw` overlay can write to it
// directly. `z-index: -1` inside an isolated stacking context paints it
// above the container's own background and below the content.

function _borderLayer(el) {
    if (!el || typeof el.querySelector !== "function") return null;
    const layer = el.querySelector(".rc-border-layer");
    return layer && layer.parentElement === el ? layer : null;
}

function _ensureBorderLayer(el) {
    let layer = _borderLayer(el);
    if (layer) return layer;
    if (!el || typeof document === "undefined"
        || typeof document.createElement !== "function") return null;
    layer = document.createElement("div");
    layer.className = "rc-border-layer";
    layer.setAttribute("aria-hidden", "true");
    el.insertBefore(layer, el.firstChild || null);
    return layer;
}

function _containerRadius(c, canvasW) {
    let value = null;
    if (c && c.border_radius != null) {
        value = _resolveLength(c.border_radius, canvasW);
    } else if (c && typeof c.border === "object" && c.border
               && c.border.radius != null) {
        value = c.border.radius;
    }
    if (value == null) return "0px";
    return (typeof value === "number") ? (value + "px") : String(value);
}

function _paintLength(value, axis, fallback) {
    if (value == null) return fallback;
    const resolved = _resolveLength(value, axis);
    return resolved == null ? fallback : (resolved + "px");
}

function _boxShadowCss(value) {
    if (value == null) return "none";
    if (typeof value === "object") {
        return (value.inset ? "inset " : "") + (value.x || 0) + "px "
            + (value.y || 0) + "px " + (value.blur || 0) + "px "
            + (value.spread || 0) + "px " + (value.color || "rgba(0,0,0,0.5)");
    }
    const text = String(value).trim();
    if (!text || text === "none" || text === "off") return "none";
    return text;
}

// A container background with no paint at all: absent, "none", "transparent"
// or a colour whose alpha is 0. This is the same rule the Designer's paint
// field uses to show its "None" state, so the row that is visible is the
// shadow that paints.
function _backgroundIsNone(value) {
    if (value == null) return true;
    const text = String(value).trim().toLowerCase();
    if (!text || text === "none" || text === "transparent") return true;
    const fn = text.match(/^rgba?\(([^)]+)\)$/);
    if (fn) {
        const parts = fn[1].split(/[,/ ]+/).filter(p => p.length > 0);
        return parts.length > 3 && parseFloat(parts[3]) === 0;
    }
    const hex = text.match(/^#([0-9a-f]{4}|[0-9a-f]{8})$/);
    if (hex) {
        const digits = hex[1];
        const alpha = digits.length === 4 ? digits.slice(3) : digits.slice(6);
        return parseInt(alpha, 16) === 0;
    }
    return false;
}

function _borderShadowHost(el) {
    const host = el && el.__rcBorderShadow;
    if (host && host.parentElement === el.parentElement) return host;
    return null;
}

function _ensureBorderShadowHost(el) {
    let host = _borderShadowHost(el);
    if (host) return host;
    const parent = el ? el.parentElement : null;
    if (!parent || typeof document === "undefined"
        || typeof document.createElement !== "function") return null;
    host = document.createElement("div");
    host.className = "rc-border-shadow";
    host.setAttribute("aria-hidden", "true");
    // A sibling of the container, never a child: `overflow: hidden` clips
    // every descendant, so a child's shadow could never reach the canvas.
    parent.insertBefore(host, el);
    host.__rcOwner = el;
    el.__rcBorderShadow = host;
    return host;
}

function _syncBorderShadow(el, c, canvasW) {
    const host = _ensureBorderShadowHost(el);
    if (!host) return;
    // Exactly one shadow paints: the container's owns a filled rectangle, the
    // border's owns the border shape. A hidden shadow is never painted.
    const value = _backgroundIsNone(c.container_background)
        ? _boxShadowCss(c.border_shadow) : "none";
    if (value === "none" || !el.offsetWidth || !el.offsetHeight) {
        host.style.display = "none";
        host.style.boxShadow = "none";
        return;
    }
    host.style.display = "block";
    const bp = _resolveLength(c.border_padding, canvasW);
    const gap = (bp == null || bp < 0) ? 0 : bp;
    // Same rect as the border layer: inset by `border_padding`, shaped by the
    // radius. The shadow itself paints outside it, onto the canvas.
    host.style.position = "absolute";
    host.style.left = (el.offsetLeft + gap) + "px";
    host.style.top = (el.offsetTop + gap) + "px";
    host.style.width = Math.max(0, el.offsetWidth - gap * 2) + "px";
    host.style.height = Math.max(0, el.offsetHeight - gap * 2) + "px";
    host.style.borderRadius = _containerRadius(c, canvasW);
    host.style.boxShadow = value;
    host.style.visibility = el.classList.contains("hidden") ? "hidden" : "";
}

function _scheduleBorderShadowSync(el, c, canvasW) {
    if (typeof requestAnimationFrame !== "function") return;
    if (el.__rcShadowFrame) return;
    el.__rcShadowFrame = requestAnimationFrame(function () {
        el.__rcShadowFrame = null;
        _syncBorderShadow(el, c, canvasW);
    });
}

function _syncBorderShadowVisibility() {
    if (typeof document === "undefined" || !document.querySelectorAll) return;
    Array.prototype.forEach.call(
        document.querySelectorAll(".rc-border-shadow"), function (host) {
            const el = host.__rcOwner;
            const hidden = !el || !el.parentElement
                || el.classList.contains("hidden")
                || el.style.display === "none";
            if (hidden) {
                host.style.visibility = "hidden";
            } else if (host.style.display !== "none") {
                host.style.visibility = "";
            }
        });
}

function _applyContainerPaint(el, c, canvasW) {
    if (!el || !el.style || !c) return;
    // 1. Outer fill: exactly the assigned rectangle, square corners. When
    // the border shape is rounded, this is what shows in the corner gaps.
    el.style.background = resolveBackground(c.container_background);
    el.style.border = "0";
    el.style.borderRadius = "0";
    // Shadows follow what is visible. A filled container is a rectangle, so
    // the container shadow paints and the border shadow does not; with no
    // container background the border shape owns the shadow instead. Both
    // stay on the canvas: the container shadow on the element itself, the
    // border shadow on a sibling host (a descendant would be clipped).
    el.style.boxShadow = _backgroundIsNone(c.container_background)
        ? "none" : _boxShadowCss(c.box_shadow);
    if (c.backdrop_filter && c.backdrop_filter !== "none") {
        el.style.backdropFilter = c.backdrop_filter;
    } else {
        el.style.backdropFilter = "";
    }

    // 2. Border shape. An absolutely positioned child's containing block is
    // the container's padding box, i.e. its inner border edge — and the
    // container draws no border of its own, so the padding box IS the
    // assigned rectangle and `border_padding` is the whole inset. Content
    // padding does not move the layer: it sits inside the same box.
    const layer = _ensureBorderLayer(el);
    if (!layer) return;
    const bp = _resolveLength(c.border_padding, canvasW);
    const gap = (bp == null || bp < 0) ? 0 : bp;
    layer.style.top = gap + "px";
    layer.style.right = gap + "px";
    layer.style.bottom = gap + "px";
    layer.style.left = gap + "px";
    _applyBorder(layer, c.border);
    layer.style.background = resolveBackground(c.background);
    layer.style.borderRadius = _containerRadius(c, canvasW);
    _syncBorderShadow(el, c, canvasW);
    _scheduleBorderShadowSync(el, c, canvasW);
}

// ─── Pin model (round 4) ─────────────────────────────────────────────────
// A container picks one of nine points of its own box (the pin) and says where
// on the canvas that pin goes: an aligned canvas point, a free x/y, or a
// distance in from one canvas edge. Resizing then grows the box around the
// pin. Files that never used the model have no `canvas`/`edge` payload and
// keep the legacy arithmetic below, untouched (docs/theme_file_reference §5.3).
const _RC_POINT_FRACTIONS = {
    top_left: [0, 0], top: [0.5, 0], top_right: [1, 0],
    left: [0, 0.5], center: [0.5, 0.5], right: [1, 0.5],
    bottom_left: [0, 1], bottom: [0.5, 1], bottom_right: [1, 1],
};

function _pointFraction(point) {
    return _RC_POINT_FRACTIONS[point] || _RC_POINT_FRACTIONS.top_left;
}

function _edgeDistance(edge, canvasW, canvasH) {
    const axis = (edge.edge === "left" || edge.edge === "right")
        ? canvasW : canvasH;
    const raw = edge.d != null ? edge.d : 0;
    if (typeof raw === "number") {
        return (edge.unit || "px") === "percent" ? axis * raw / 100 : raw;
    }
    const resolved = _resolveLength(raw, axis);
    return resolved == null ? 0 : resolved;
}

function _modelPosition(pos, width, height, canvasW, canvasH) {
    const canvas = pos.canvas || {};
    const edge = pos.edge || {};
    if ((pos.mode || "canvas") === "edge") {
        const af = _pointFraction(edge.anchor || canvas.anchor || "top_left");
        const pinned = edge.edge || "left";
        const distance = _edgeDistance(edge, canvasW, canvasH);
        let pinX = af[0] * canvasW;
        let pinY = af[1] * canvasH;
        if (pinned === "left") pinX = distance;
        else if (pinned === "right") pinX = canvasW - distance;
        else if (pinned === "top") pinY = distance;
        else if (pinned === "bottom") pinY = canvasH - distance;
        return { left: pinX - af[0] * width, top: pinY - af[1] * height };
    }
    const af = _pointFraction(canvas.anchor || "top_left");
    let pinX = 0;
    let pinY = 0;
    const aligned = _RC_POINT_FRACTIONS[canvas.aligned];
    if (aligned) {
        pinX = aligned[0] * canvasW;
        pinY = aligned[1] * canvasH;
    } else {
        pinX = canvas.x != null ? (Number(canvas.x) || 0) : 0;
        pinY = canvas.y != null ? (Number(canvas.y) || 0) : 0;
    }
    return { left: pinX - af[0] * width, top: pinY - af[1] * height };
}

function _computePosition(pos, width, height, canvasW, canvasH) {
    pos = pos || {};
    if (pos.canvas || pos.edge) {
        return _modelPosition(pos, width, height, canvasW, canvasH);
    }
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

// ─── Scene pass: ties between containers (round 5) ───────────────────────
// One container can stick to a point of another: put B's anchor on point P of
// A's rectangle, then shift by d along one axis. B is not parented or clipped
// by A. Every container is resolved once, after its target, so chains work and
// a shared target costs nothing extra. A tie that cannot be applied (missing
// target, or a loop in the file) falls back to that container's own canvas
// arithmetic and is reported in `errors`; nothing is rewritten.
let _sceneRects = {};
let _sceneErrors = {};

function _sceneRect(c) {
    if (!c || c.id == null) return null;
    return _sceneRects[String(c.id)] || null;
}

function _containerSize(c, canvasW, canvasH) {
    let w = _resolveLength(c.width, canvasW);
    let h = _resolveLength(c.height, canvasH);
    if (w == null && c.min_width != null) w = _resolveLength(c.min_width, canvasW);
    if (h == null && c.min_height != null) h = _resolveLength(c.min_height, canvasH);
    if (w == null) w = canvasW;
    if (h == null) h = canvasH;
    if (c.position && (c.position.canvas || c.position.edge)) {
        // A pinned box is placed by the size it is painted at.
        const minW = _resolveLength(c.min_width, canvasW);
        const minH = _resolveLength(c.min_height, canvasH);
        const maxW = _resolveLength(c.max_width, canvasW);
        const maxH = _resolveLength(c.max_height, canvasH);
        if (minW != null && w < minW) w = minW;
        if (minH != null && h < minH) h = minH;
        if (maxW != null && w > maxW) w = maxW;
        if (maxH != null && h > maxH) h = maxH;
    }
    return { w: w, h: h };
}

function _tieEdge(position) {
    if (!position || (position.mode || "canvas") !== "edge") return null;
    const edge = position.edge;
    if (!edge || typeof edge !== "object") return null;
    if (String(edge.target || "canvas") === "canvas") return null;
    return edge;
}

function _tieDistance(edge, extent) {
    const raw = edge.d != null ? edge.d : 0;
    if (typeof raw !== "number") {
        const resolved = _resolveLength(raw, extent);
        return resolved == null ? 0 : resolved;
    }
    return (edge.unit || "px") === "percent" ? extent * raw / 100 : raw;
}

function _tiePosition(edge, target, width, height) {
    const af = _pointFraction(edge.anchor || "top_left");
    const tf = _pointFraction(edge.targetPoint || edge.anchor || "top_left");
    const pointX = target.left + tf[0] * target.width;
    const pointY = target.top + tf[1] * target.height;
    const axis = edge.axis || "x";
    const extent = axis === "x" ? target.width : target.height;
    const shift = _tieDistance(edge, extent);
    return { left: pointX - af[0] * width + (axis === "x" ? shift : 0),
             top: pointY - af[1] * height + (axis === "y" ? shift : 0),
             width: width, height: height };
}

function _resolveScene(containers, canvasW, canvasH) {
    const rects = {};
    const errors = {};
    const byId = {};
    (containers || []).forEach(c => {
        if (c && typeof c === "object") byId[String(c.id)] = c;
    });
    const ids = Object.keys(byId);
    const sizes = {};
    const ties = {};
    ids.forEach(id => {
        sizes[id] = _containerSize(byId[id], canvasW, canvasH);
        ties[id] = _tieEdge(byId[id].position);
    });
    ids.forEach(id => {
        const edge = ties[id];
        if (edge && !byId[String(edge.target)]) {
            errors[id] = "Target container not found";
        }
    });
    ids.forEach(id => {
        if (errors[id] || !ties[id]) return;
        const seen = [];
        let node = id;
        while (node != null && byId[node] && seen.indexOf(node) < 0
               && !errors[node] && ties[node]) {
            seen.push(node);
            node = String(ties[node].target);
        }
        if (node != null && seen.indexOf(node) >= 0) {
            seen.slice(seen.indexOf(node)).forEach(m => {
                if (ties[m] && !errors[m]) errors[m] = "Tie would create a loop";
            });
        }
    });
    const resolve = id => {
        if (rects[id]) return rects[id];
        const size = sizes[id];
        const edge = ties[id];
        let rect;
        if (edge && !errors[id]) {
            const tied = _tiePosition(edge, resolve(String(edge.target)),
                                      size.w, size.h);
            // Only the origin: the paint code keeps its own size handling, so
            // an `auto` box still autosizes (docs/theme_file_reference.md).
            rect = {left: tied.left, top: tied.top};
        } else {
            const p = _computePosition(byId[id].position, size.w, size.h,
                                       canvasW, canvasH);
            rect = {left: p.left, top: p.top};
        }
        rects[id] = rect;
        return rect;
    };
    ids.forEach(resolve);
    return { rects: rects, errors: errors };
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

// The one converter from a stored `canvas.background` value to a CSS paint.
// The Designer preview and the OBS renderer both come through here, so
// "none"/"transparent", plain colours and gradients can never diverge between
// what the operator edits and what OBS shows.
function resolveBackground(value) {
    if (value === null || value === undefined) return "transparent";
    const text = String(value).trim();
    if (!text) return "transparent";
    const low = text.toLowerCase();
    if (low === "none" || low === "transparent") return "transparent";
    return text;
}

// Sizes and paints the canvas, then scales the whole canvas uniformly into
// the surface it is shown on. `canvas.fit` no longer exists: the canvas always
// behaves the way "contain" used to (and the way the Designer preview always
// did) — centred with letter/pillarbox bars, never cropped.
function applyCanvas(canvas) {
    const stg = document.getElementById("stage");
    if (!stg) return;
    const cw = (canvas && canvas.width) || 1920;
    const ch = (canvas && canvas.height) || 1080;
    stg.style.width = cw + "px";
    stg.style.height = ch + "px";
    stg.style.background = resolveBackground(canvas && canvas.background);

    if (typeof window === "undefined" || !window.innerWidth || !window.innerHeight) return;

    let boxW = window.innerWidth;
    let boxH = window.innerHeight;
    if (window.__RC_PREVIEW) {
        // The Designer preview is always a fixed 16:9 stage: the whole canvas
        // is contained inside a centred 16:9 box and letterboxed/pillarboxed
        // around it — never cropped, never reshaped.
        boxW = Math.min(window.innerWidth, window.innerHeight * 16 / 9);
        boxH = boxW * 9 / 16;
    }
    const scale = Math.min(boxW / cw, boxH / ch);
    const left = (window.innerWidth - cw * scale) / 2;
    const top = (window.innerHeight - ch * scale) / 2;
    stg.style.transformOrigin = "0 0";
    stg.style.transform = "translate(" + left + "px, " + top + "px) scale(" + scale + ")";
}

if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("resize", function () {
        if (_currentTheme && _currentTheme.canvas) {
            applyCanvas(_currentTheme.canvas);
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
        applyCanvas(theme.canvas);
    }

    let containers = [];
    if (Array.isArray(theme.containers)) {
        containers = theme.containers.filter(c => c && typeof c === "object" && c.visible !== false)
                                     .sort((a, b) => (a.layer || 0) - (b.layer || 0));
    } else if (theme.containers && typeof theme.containers === "object" && _isNewContainers(theme.containers)) {
        containers = Object.values(theme.containers).filter(c => c && typeof c === "object" && c.visible !== false);
    }
    // The scene pass needs every container, hidden ones included: a tie to a
    // hidden container still has geometry (only painting is skipped).
    let allContainers = [];
    if (Array.isArray(theme.containers)) {
        allContainers = theme.containers.filter(c => c && typeof c === "object");
    } else if (theme.containers && typeof theme.containers === "object") {
        allContainers = Object.values(theme.containers).filter(c => c && typeof c === "object");
    }
    const scene = _resolveScene(allContainers,
                                (theme.canvas && theme.canvas.width) || 1920,
                                (theme.canvas && theme.canvas.height) || 1080);
    _sceneRects = scene.rects;
    _sceneErrors = scene.errors;
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
    if (c.container_background) root.style.setProperty("--rc-container-bg", c.container_background);
    if (c.background)        root.style.setProperty("--rc-border-fill", c.background);
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
    // Per-side declarations cannot ride a single border custom property, so
    // the ring is painted by the container's border layer (see
    // `_applyContainerPaint`). The variables stay for the legacy absolute
    // `#ct-*` panels, which have no layer of their own.
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
    // The assigned rectangle is authoritative. The stylesheet used to cap a
    // container at 80 % of the canvas and raise it to 60 %, which silently
    // resized (and clipped) an authored 1920×1080 or a 600 px panel; min/max
    // now come only from the theme.
    container.style.minWidth = _paintLength(c.min_width, canvasW, "0px");
    container.style.maxWidth = _paintLength(c.max_width, canvasW, "none");
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
        if (c.position && (c.position.canvas || c.position.edge)) {
            // A pinned box is placed by the size it is painted at.
            const minW = _resolveLength(c.min_width, canvasW);
            const minH = _resolveLength(c.min_height, canvasH);
            const maxW = _resolveLength(c.max_width, canvasW);
            const maxH = _resolveLength(c.max_height, canvasH);
            if (minW != null && w < minW) w = minW;
            if (minH != null && h < minH) h = minH;
            if (maxW != null && w > maxW) w = maxW;
            if (maxH != null && h > maxH) h = maxH;
        }

        if (c.position) {
            const p = _sceneRect(c)
                || _computePosition(c.position, w, h, canvasW, canvasH);
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

    // Both paints are applied last: the content padding above decides where
    // the content sits inside the assigned rectangle.
    _applyContainerPaint(container, c, canvasW);

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
    const tShadowRaw = _textShadowCss(t.text_shadow);
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

// ─── Designer preview paint scheduler ──────────────────────────────────────
// Only the in-app preview (window.__RC_PREVIEW) runs through this; OBS still
// applies every payload synchronously. A left-panel edit hands the newest
// theme here: the scheduler paints it on the next animation frame, keeps a
// 60 Hz cadence while edits keep arriving and for a short grace window after
// the last one, then drops to a 1 Hz heartbeat that repaints the latest value
// as a safety net. The dirty flag is the coalescing point — there is no
// debounce, so the newest value always wins and is always painted.
const RC_PREVIEW_GRACE_MS = 500;
const RC_PREVIEW_IDLE_MS = 1000;
const RC_PREVIEW_FRAME_MS = 1000 / 60;

let _rcLiveTheme = null;
let _rcLiveFormat = undefined;
let _rcDirty = false;
let _rcRefreshContainers = false;
let _rcLastChange = 0;
let _rcLastPaint = -Infinity;
let _rcFrame = 0;
let _rcHeartbeat = 0;
let _rcActivePaints = 0;
let _rcIdlePaints = 0;
let _rcIdleTicks = 0;

function _rcPreviewActive() {
    return typeof window !== "undefined" && !!window.__RC_PREVIEW;
}

function _rcClock() {
    return (typeof performance !== "undefined" && performance
        && performance.now) ? performance.now() : Date.now();
}

function _rcPaint() {
    if (_rcLiveTheme === null) return;
    _rcDirty = false;
    _rcLastPaint = _rcClock();
    applyTheme(_rcLiveTheme, _rcLiveFormat);
    if (_rcRefreshContainers && _prevPayload && _currentContainers
            && _currentContainers.length > 1) {
        _renderMultiContainers(_prevPayload);
    }
    _rcRefreshContainers = false;
}

function _rcHeartbeatTick() {
    _rcIdleTicks++;
    if (!_rcPreviewActive()) {
        if (_rcHeartbeat) clearInterval(_rcHeartbeat);
        _rcHeartbeat = 0;
        return;
    }
    // Safety net only: a value whose frame never ran (rAF paused, a dropped
    // tick) is dirty. An unchanged frame is left alone — a redundant
    // applyTheme rebuilds outline layers and would disturb a running
    // right-panel animation.
    if (!_rcDirty) return;
    _rcPaint();
    _rcIdlePaints++;
}

function _rcStartHeartbeat() {
    if (_rcHeartbeat) return;
    _rcHeartbeat = setInterval(_rcHeartbeatTick, RC_PREVIEW_IDLE_MS);
}

function _rcTick() {
    _rcFrame = 0;
    const now = _rcClock();
    // rAF can run at 120 Hz; one paint per 16.7 ms is the ceiling.
    if (_rcDirty && now - _rcLastPaint >= RC_PREVIEW_FRAME_MS - 0.5) {
        _rcPaint();
        _rcActivePaints++;
    }
    if (now - _rcLastChange < RC_PREVIEW_GRACE_MS) {
        _rcFrame = requestAnimationFrame(_rcTick);
        return;
    }
    _rcStartHeartbeat();
}

function _rcWake() {
    _rcLastChange = _rcClock();
    if (_rcHeartbeat) {
        clearInterval(_rcHeartbeat);
        _rcHeartbeat = 0;
    }
    if (!_rcFrame) _rcFrame = requestAnimationFrame(_rcTick);
}

function scheduleThemeApply(theme, slideFormat) {
    if (!theme) return;
    _rcLiveTheme = theme;
    _rcLiveFormat = slideFormat;
    _rcDirty = true;
    if (!_rcPreviewActive()) { _rcPaint(); return; }
    _rcWake();
}

function applyThemeNow(theme, slideFormat) {
    if (!theme) return;
    _rcLiveTheme = theme;
    _rcLiveFormat = slideFormat;
    _rcDirty = false;
    _rcRefreshContainers = true;
    _rcLastChange = _rcClock();
    _rcPaint();
    if (_rcPreviewActive() && !_rcFrame) {
        _rcFrame = requestAnimationFrame(_rcTick);
    }
}

function previewRenderStats() {
    return {
        mode: _rcFrame ? "active" : "idle",
        activePaints: _rcActivePaints,
        idlePaints: _rcIdlePaints,
        idleTicks: _rcIdleTicks,
        dirty: _rcDirty,
        frameMs: Math.round(RC_PREVIEW_FRAME_MS),
        graceMs: RC_PREVIEW_GRACE_MS,
        idleMs: RC_PREVIEW_IDLE_MS,
    };
}

function applyThemeInPlace(theme) {
    // Style/geometry-only Designer edits. The single-container path is
    // already handled by applyTheme(); multi-panel themes also need their
    // geometry rebuilt from the payload already on screen. When that paint
    // lands is the scheduler's decision: next frame, or now for a release.
    _rcRefreshContainers = true;
    scheduleThemeApply(theme);
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

    // The wrapper is the canvas, not a 1920x1080 box: positions are authored
    // in canvas pixels, so a fixed 1920 frame pushed every verse into the left
    // edge of a wider wall (4270x1080) and clipped the rest.
    const canvasW = (theme.canvas && theme.canvas.width) || 1920;
    const canvasH = (theme.canvas && theme.canvas.height) || 1080;
    container.style.position = "absolute";
    container.style.width = canvasW + "px";
    container.style.height = canvasH + "px";
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
        inner.style.textShadow = _textShadowCss(style.text_shadow);
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
        if (verseNum) html = '<span class="verse-num"' + _verseNumAttrs(_verseNumBlock()) + '>' + verseNum + '</span> ' + html;
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
    _syncBorderShadowVisibility();
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
        if (c.position && (c.position.canvas || c.position.edge)) {
            // A pinned box is placed by the size it is painted at.
            const minW = _resolveLength(c.min_width, canvasW);
            const minH = _resolveLength(c.min_height, canvasH);
            const maxW = _resolveLength(c.max_width, canvasW);
            const maxH = _resolveLength(c.max_height, canvasH);
            if (minW != null && w < minW) w = minW;
            if (minH != null && h < minH) h = minH;
            if (maxW != null && w > maxW) w = maxW;
            if (maxH != null && h > maxH) h = maxH;
        }

        const pos = _sceneRect(c)
            || _computePosition(c.position, w, h, canvasW, canvasH);
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

        // Rebuild from scratch: the border layer is recreated first and the
        // blocks follow it, so every re-render starts from one known DOM.
        el.innerHTML = "";
        _applyContainerPaint(el, c, canvasW);

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
                html = '<span class="verse-num"' + _verseNumAttrs(vn, "#cccccc") + '>' + vnNum + '</span> ' + html;
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
            const tShadow = _textShadowCss(t.text_shadow);
            if (tShadow && tShadow !== "none") h1.style.textShadow = tShadow;
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
    const dur = (durationMs != null ? durationMs : RC_ANIM_DEFAULTS.duration_ms) + "ms";
    const ease = ANIM_EASINGS[easing] || ANIM_EASINGS[RC_ANIM_DEFAULTS.easing] || RC_ANIM_DEFAULTS.easing;
    el.style.animation = `${kfName} ${dur} ${ease} forwards`;
    el.addEventListener("animationend", () => { el.style.animation = ""; }, { once: true });
}

function _cancelAnimations(el) {
    if (!el) return;
    _cancelPropertyAnimations(el);
    const anim = _activeAnims.get(el);
    if (anim) {
        try { anim.cancel(); } catch (e) {}
        _activeAnims.delete(el);
    }
    _animatedEls.delete(el);
}

function _cancelAllAnimations() {
    _stopSustain();
    if (_phaseTimer) {
        clearTimeout(_phaseTimer);
        _phaseTimer = null;
    }
    _phaseToken++;
    _clearOverlapTimers();
    _removeOverlapLayer();
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
    const preset = (name) => ({ type: name, duration_ms: RC_ANIM_DEFAULTS.duration_ms, easing: RC_ANIM_DEFAULTS.easing });
    if (!slot || slot === "none") return null;
    if (typeof slot === "string") {
        if (registry && registry[slot]) return registry[slot];
        if (ANIM_PRESET_TYPES.indexOf(slot) !== -1) return preset(slot);
        // Unknown names mean no animation. Never invent a phase fallback.
        return null;
    }
    if (typeof slot === "object") {
        if (slot.use) {
            const base = (registry && registry[slot.use])
                || (ANIM_PRESET_TYPES.indexOf(slot.use) !== -1
                    ? preset(slot.use) : null);
            if (!base) return null;
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
    if (!split) return null;

    const spans = split.spans;
    const cfg = def.cursor && def.cursor !== "none" ? def.cursor : null;
    const cursor = _typewriterCursor(cfg);
    const total = Math.max(0, def.duration_ms != null ? def.duration_ms : RC_ANIM_DEFAULTS.typewriter_duration_ms);
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
        // never when the block's text has been rebuilt as outlined SVG. An
        // invalid context means no animation, not a silent fade.
        if (phase === "out" || (kind !== "text" && kind !== "reference"
                && kind !== "translation") || _outlineConflict(el)) {
            return null;
        }
        return _playTypewriter(el, def);
    }

    const duration = def.duration_ms != null ? def.duration_ms : RC_ANIM_DEFAULTS.duration_ms;
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
            easing: ANIM_EASINGS[def.easing] || def.easing || RC_ANIM_DEFAULTS.easing,
            fill: "forwards",
            iterations: opts.iterations || 1,
        });
    } catch (e) {
        return null;
    }
    if (def.origin) el.style.transformOrigin = def.origin;
    _trackAnimation(el, anim, phase === "out");
    return anim;
}

function _phaseDuration(def) {
    if (!def) return 0;
    return Math.max(0, def.delay_ms || 0)
        + Math.max(0, def.duration_ms != null ? def.duration_ms : RC_ANIM_DEFAULTS.duration_ms);
}

// ─── Property tracks ───────────────────────────────────────────────
// A property track animates something the keyframe channels cannot reach.
// Each animator owns its element overlay and cleanup; unknown track ids are
// ignored so a newer theme still plays the tracks this renderer knows.
const _SVG_NS = "http://www.w3.org/2000/svg";
const _propertyCleanups = new WeakMap();

function _addPropertyCleanup(el, cleanup) {
    const list = _propertyCleanups.get(el);
    if (list) list.push(cleanup);
    else _propertyCleanups.set(el, [cleanup]);
    _animatedEls.add(el);
}

function _removePropertyCleanup(el, cleanup) {
    const list = _propertyCleanups.get(el);
    if (!list) return;
    const index = list.indexOf(cleanup);
    if (index !== -1) list.splice(index, 1);
    if (!list.length) {
        _propertyCleanups.delete(el);
        if (!_activeAnims.get(el)) _animatedEls.delete(el);
    }
}

function _cancelPropertyAnimations(el) {
    if (!el) return;
    const list = _propertyCleanups.get(el);
    if (!list) return;
    _propertyCleanups.delete(el);
    list.slice().forEach(cleanup => {
        try { cleanup(); } catch (e) {}
    });
}

function _clamp01(value, fallback) {
    const number = Number(value);
    if (!isFinite(number)) return fallback;
    return Math.max(0, Math.min(1, number));
}

function _borderDirection(raw) {
    let start = "top";
    let clockwise = true;
    if (raw && typeof raw === "object") {
        const side = String(raw.start || "").toLowerCase();
        if (["top", "right", "bottom", "left"].indexOf(side) !== -1) start = side;
        if (String(raw.direction || "").toLowerCase().indexOf("counter") === 0) {
            clockwise = false;
        }
        return { start: start, clockwise: clockwise };
    }
    const text = String(raw == null ? "clockwise" : raw).trim().toLowerCase();
    if (text.indexOf("counter") === 0) {
        return { start: "top", clockwise: false };
    }
    if (text.indexOf("start:") === 0) {
        const parts = text.split(/\s+/);
        const side = parts[0].slice(6);
        if (["top", "right", "bottom", "left"].indexOf(side) !== -1) start = side;
        if (parts.slice(1).some(part => part.indexOf("counter") === 0)) {
            clockwise = false;
        }
    }
    return { start: start, clockwise: clockwise };
}

// A rounded rectangle path in the four cardinal directions. Corner arcs use
// sweep 1 (clockwise); counterclockwise is the same geometry mirrored.
function _roundedRectPathData(w, h, radius, start) {
    w = Math.max(1, w);
    h = Math.max(1, h);
    const r = Math.max(0, Math.min(radius, w / 2, h / 2));
    if (!r) {
        if (start === "right") return "M " + w + " 0 V " + h + " H 0 V 0 H " + w + " Z";
        if (start === "bottom") return "M " + w + " " + h + " H 0 V 0 H " + w + " V " + h + " Z";
        if (start === "left") return "M 0 " + h + " V 0 H " + w + " V " + h + " H 0 Z";
        return "M 0 0 H " + w + " V " + h + " H 0 Z";
    }
    const arc = " A " + r + " " + r + " 0 0 1 ";
    if (start === "right") {
        return "M " + w + " " + r + " V " + (h - r) + arc + (w - r) + " " + h
            + " H " + r + arc + "0 " + (h - r) + " V " + r + arc + r + " 0"
            + " H " + (w - r) + arc + w + " " + r + " Z";
    }
    if (start === "bottom") {
        return "M " + (w - r) + " " + h + " H " + r + arc + "0 " + (h - r)
            + " V " + r + arc + r + " 0 H " + (w - r) + arc + w + " " + r
            + " V " + (h - r) + arc + (w - r) + " " + h + " Z";
    }
    if (start === "left") {
        return "M 0 " + (h - r) + " V " + r + arc + r + " 0 H " + (w - r)
            + arc + w + " " + r + " V " + (h - r) + arc + (w - r) + " " + h
            + " H " + r + arc + "0 " + (h - r) + " Z";
    }
    return "M " + r + " 0 H " + (w - r) + arc + w + " " + r + " V " + (h - r)
        + arc + (w - r) + " " + h + " H " + r + arc + "0 " + (h - r)
        + " V " + r + arc + r + " 0 Z";
}

function _borderDrawMetrics(el) {
    if (!el || typeof getComputedStyle !== "function") return null;
    let cs;
    try { cs = getComputedStyle(el); } catch (e) { return null; }
    if (!cs) return null;
    const widths = ["Top", "Right", "Bottom", "Left"].map(side => {
        const value = parseFloat(cs["border" + side + "Width"]);
        return isFinite(value) ? value : 0;
    });
    const border = Math.max.apply(null, widths);
    if (!(border > 0)) return null;
    const w = Math.max(0, el.clientWidth || 0);
    const h = Math.max(0, el.clientHeight || 0);
    if (!w || !h) return null;
    const radius = Math.max(0, (parseFloat(cs.borderTopLeftRadius) || 0) - border);
    // The container clips at its padding box, so the stroke sits inside it.
    const inset = Math.min(w / 2, Math.max(0.5, border / 2));
    const iw = Math.max(1, w - inset * 2);
    const ih = Math.max(1, h - inset * 2);
    const r = Math.min(radius, iw / 2, ih / 2);
    const perimeter = 2 * (iw - 2 * r) + 2 * (ih - 2 * r) + 2 * Math.PI * r;
    let colour = cs.borderTopColor || cs.borderRightColor || "#ffffff";
    const transparent = value => !value || value === "transparent"
        || /rgba\([^)]*,\s*0(?:\.0+)?\)$/.test(value);
    const opaque = ["borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor"]
        .map(key => cs[key])
        .find(value => !transparent(value));
    if (opaque) colour = opaque;
    return {
        cs: cs, border: border, widths: widths, w: w, h: h,
        inset: inset, iw: iw, ih: ih, radius: r,
        perimeter: perimeter, colour: colour,
    };
}

function _borderDrawTiming(el, track) {
    const metrics = _borderDrawMetrics(el);
    if (!metrics) return null;
    const delay = Math.max(0, Number(track.delay_ms) || 0);
    let duration = Number(track.duration_ms);
    if (!isFinite(duration)) duration = 600;
    const speed = Number(track.speed);
    if (isFinite(speed) && speed > 0) {
        duration = (metrics.perimeter / speed) * 1000;
    }
    duration = Math.max(0, Math.min(5000, duration));
    return {
        metrics: metrics,
        delay: delay,
        duration: duration,
        from: _clamp01(track.from, 0),
        to: _clamp01(track.to, 1),
    };
}

function _playBorderDraw(el, track) {
    // Containers paint their ring on the border layer, so the overlay has to
    // follow the border it is replacing: measuring the container itself would
    // read `border: 0` and draw nothing.
    const target = _borderLayer(el) || el;
    const timing = _borderDrawTiming(target, track);
    if (!timing) return 0;
    const animate = timing.duration > 0 && timing.from !== timing.to;
    // A full static border needs no overlay. A partial draw does, even when
    // it has no duration: the final state is part of the border.
    if (animate || timing.to < 1) {
        _applyBorderDrawOverlay(target, track, timing, animate);
    }
    return timing.delay + timing.duration;
}

function _applyBorderDrawOverlay(el, track, timing, animate) {
    if (typeof document.createElementNS !== "function") return 0;
    const metrics = timing.metrics;
    const direction = _borderDirection(track.direction);
    const start = direction.clockwise ? direction.start
        : ({ top: "top", bottom: "bottom", left: "right", right: "left" })[direction.start];
    const d = _roundedRectPathData(metrics.iw, metrics.ih,
                                   metrics.radius, start);
    const svg = document.createElementNS(_SVG_NS, "svg");
    svg.setAttribute("class", "rc-border-draw");
    svg.setAttribute("data-rc-border-draw", "1");
    svg.setAttribute("data-rc-direction", direction.start +
        (direction.clockwise ? " clockwise" : " counterclockwise"));
    svg.setAttribute("data-rc-perimeter", String(Math.round(metrics.perimeter)));
    svg.setAttribute("viewBox", "0 0 " + metrics.w + " " + metrics.h);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    svg.style.position = "absolute";
    svg.style.inset = "0";
    svg.style.width = "100%";
    svg.style.height = "100%";
    svg.style.overflow = "visible";
    svg.style.pointerEvents = "none";
    svg.style.zIndex = "4";
    const group = document.createElementNS(_SVG_NS, "g");
    group.setAttribute("transform", "translate(" + metrics.inset + " "
        + metrics.inset + ")");
    const path = document.createElementNS(_SVG_NS, "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", metrics.colour);
    path.setAttribute("stroke-width", String(metrics.border));
    path.setAttribute("stroke-linecap", metrics.cs.borderTopStyle === "dotted"
        ? "round" : "butt");
    path.setAttribute("pathLength", "1");
    path.setAttribute("stroke-dasharray", "1 1");
    path.setAttribute("stroke-dashoffset", String(1 - timing.from));
    if (!direction.clockwise) {
        path.setAttribute("transform", "translate(" + metrics.iw + ",0) scale(-1,1)");
    }
    group.appendChild(path);
    svg.appendChild(group);

    // Hide the static border while the overlay owns the ring. The width and
    // style stay, so hiding never reflows the container.
    const savedColor = el.style.borderColor;
    const savedPosition = el.style.position;
    if (metrics.cs.position === "static") el.style.position = "relative";
    el.style.borderColor = "transparent";
    el.appendChild(svg);

    let anim = null;
    if (animate) {
        try {
            anim = path.animate([
                { strokeDashoffset: 1 - timing.from },
                { strokeDashoffset: 1 - timing.to },
            ], {
                duration: timing.duration,
                delay: timing.delay,
                easing: ANIM_EASINGS[track.easing] || track.easing || "ease-out",
                fill: "forwards",
            });
            svg.setAttribute("data-rc-duration-ms", String(Math.round(timing.duration)));
        } catch (e) { anim = null; }
    }

    let cleaned = false;
    const cleanup = function () {
        if (cleaned) return;
        cleaned = true;
        if (anim) { try { anim.cancel(); } catch (e) {} }
        if (svg.parentNode) svg.parentNode.removeChild(svg);
        el.style.borderColor = savedColor;
        el.style.position = savedPosition;
        _removePropertyCleanup(el, cleanup);
    };
    _addPropertyCleanup(el, cleanup);
    if (!anim && animate) {
        cleanup();
        return;
    }
    if (anim) {
        const finish = function () {
            if (timing.to >= 1) cleanup();
        };
        try {
            if (anim.finished && typeof anim.finished.then === "function") {
                anim.finished.then(finish, cleanup);
            } else {
                setTimeout(finish, timing.delay + timing.duration);
            }
        } catch (e) { finish(); }
    }
}

function _borderDrawDuration(el, track) {
    const timing = _borderDrawTiming(el, track);
    return timing ? timing.delay + timing.duration : 0;
}

const PROPERTY_ANIMATORS = {
    "border.draw": { domain: "geometry", play: _playBorderDraw,
                     duration: _borderDrawDuration },
};

function _hasPropertyTracks(anim, phase) {
    if (!anim || !anim.properties) return false;
    return Object.keys(anim.properties).some(trackId => {
        const track = anim.properties[trackId];
        return !!track && track.phase === phase
            && !!PROPERTY_ANIMATORS[trackId];
    });
}

function _playPropertyTracks(el, anim, phase) {
    if (!el || !anim || !anim.properties || _reducedMotion()) return 0;
    let total = 0;
    Object.keys(anim.properties).forEach(trackId => {
        const track = anim.properties[trackId];
        if (!track || track.phase !== phase) return;
        const animator = PROPERTY_ANIMATORS[trackId];
        if (!animator) return;
        total = Math.max(total, animator.play(el, track) || 0);
    });
    return total;
}

function _propertyPhaseDuration(el, anim, phase) {
    if (!el || !anim || !anim.properties) return 0;
    let total = 0;
    Object.keys(anim.properties).forEach(trackId => {
        const track = anim.properties[trackId];
        if (!track || track.phase !== phase) return;
        const animator = PROPERTY_ANIMATORS[trackId];
        if (!animator) return;
        total = Math.max(total, animator.duration(el, track) || 0);
    });
    return total;
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
        if (!t.anim) return;
        const trans = t.anim.transition;
        const tracks = _hasPropertyTracks(t.anim, "transition_out");
        if ((!trans || !trans.out) && !tracks) return;
        const relevant = (t.kind === "container" || t.kind === "body")
            ? changed.any : !!changed[t.kind];
        if (!relevant) return;
        const def = (trans && trans.out)
            ? _resolveSlotDef(trans.out, anims, "out") : null;
        if (def || tracks) {
            plan.push({ el: t.el, def: def, kind: t.kind, anim: t.anim });
        }
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
        if (!t.anim) return;
        const tracks = _hasPropertyTracks(t.anim, "out");
        if (!t.anim.out && !tracks) return;
        const def = t.anim.out ? _resolveSlotDef(t.anim.out, anims, "out") : null;
        if (def || tracks) {
            plan.push({ el: t.el, def: def, kind: t.kind, anim: t.anim });
        }
    });
    return plan;
}

function _runAnimation(phase, changed) {
    if (_reducedMotion()) return 0;
    const theme = _currentTheme;
    if (!theme) return 0;
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
        return 0;
    }

    const trackPhase = phase === "entry" ? "entry" : "transition_in";
    let total = 0;
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
        // Property tracks run even when the slot is empty or split owns the
        // text: they are independent of the keyframe channels.
        total = Math.max(total, _playPropertyTracks(t.el, t.anim, trackPhase));
        if (!slot) return;
        if (phase !== "out" && _splitConfig(t.anim)
            && _runSplitAnimation(t.el, t.anim, phase, anims)) return;
        const def = _resolveSlotDef(slot, anims, "in");
        if (def) {
            _playElementAnimation(t.el, def, { kind: t.kind, phase: phase });
            total = Math.max(total, _phaseDuration(def));
        }
    });
    return total;
}

// ─── Overlap pair ───────────────────────────────────────────────────
// `motion.transition` / `motion.in_out` may select `overlap`: the outgoing
// content keeps playing while the incoming content starts an offset later,
// stacked above it. The incoming theme supplies
// motion.overlap_in_offset_ms; the generated constant is the fallback for a
// theme that does not set it.
let _overlapLayer = null;
let _overlapTimers = [];
let _overlapInfo = null;

function _overlapOffset(theme) {
    const fallback = (typeof RC_ANIM_DEFAULTS !== "undefined")
        ? RC_ANIM_DEFAULTS.overlap_in_offset_ms : 0;
    const motion = theme && theme.motion;
    const raw = (motion && motion.overlap_in_offset_ms != null)
        ? motion.overlap_in_offset_ms : fallback;
    const value = Number(raw);
    return isFinite(value) && value > 0 ? value : 0;
}

function _overlapSupported(theme) {
    // v2 themes render into container elements this clone can freeze; a v1
    // theme keeps the sequential path.
    return !!(theme && theme.schema_version === 2
        && Array.isArray(theme.containers));
}

function _snapshotRootThemeVars() {
    // Theme custom properties live on :root. The clone inherits whatever the
    // new theme writes there, so the old values ride on the clone itself.
    const out = {};
    if (typeof document === "undefined" || !document.documentElement) {
        return out;
    }
    const style = document.documentElement.style;
    if (!style || typeof style.item !== "function") return out;
    for (let i = 0; i < style.length; i++) {
        const prop = style.item(i);
        if (prop && prop.indexOf("--rc-") === 0) {
            out[prop] = style.getPropertyValue(prop);
        }
    }
    return out;
}

function _captureOverlapLayer(plan, phase) {
    // Mark the outgoing targets in the live DOM, clone #stage once, then strip
    // the markers from the live DOM. The clone stays detached: the incoming
    // render must run first or resetTheme() would drop it.
    if (!plan || !plan.length || !stage
        || typeof stage.cloneNode !== "function") return null;
    const marks = [];
    plan.forEach(function (p, index) {
        if (!p.el || typeof p.el.setAttribute !== "function") return;
        const attr = "data-rc-overlap-" + index;
        try { p.el.setAttribute(attr, String(index)); } catch (e) { return; }
        marks.push({ el: p.el, attr: attr, def: p.def, kind: p.kind,
                     anim: p.anim });
    });
    let clone = null;
    try { clone = stage.cloneNode(true); } catch (e) { clone = null; }
    marks.forEach(function (m) {
        try { m.el.removeAttribute(m.attr); } catch (e) {}
    });
    if (!clone) return null;
    // The clone is positioned by CSS (.rc-overlap-layer), and it must not
    // shadow the live #stage for getElementById. Appending it last keeps the
    // duplicated inner ids from winning document-order lookups.
    clone.removeAttribute("id");
    clone.removeAttribute("aria-live");
    const targets = [];
    marks.forEach(function (m) {
        const el = (typeof clone.querySelector === "function")
            ? clone.querySelector("[" + m.attr + "]") : null;
        if (!el) return;
        el.removeAttribute(m.attr);
        targets.push({ el: el, def: m.def, kind: m.kind, anim: m.anim });
    });
    if (!targets.length) return null;
    return { el: clone, targets: targets, phase: phase };
}

function _attachOverlapLayer(layer, vars) {
    if (!layer || !layer.el || !stage) return false;
    const el = layer.el;
    Object.keys(vars || {}).forEach(function (prop) {
        try { el.style.setProperty(prop, vars[prop]); } catch (e) {}
    });
    // The cloned inline width/height/background stay. The live stage's fit
    // transform is already applied by the ancestor, so it must not repeat.
    el.style.transform = "none";
    el.style.transformOrigin = "0 0";
    el.style.position = "absolute";
    el.style.left = "0";
    el.style.top = "0";
    el.style.pointerEvents = "none";
    el.style.zIndex = "-1";
    el.classList.add("rc-overlap-layer");
    stage.appendChild(el);
    _overlapLayer = layer;
    return true;
}

function _removeOverlapLayer() {
    const active = !!_overlapLayer;
    if (_overlapLayer) {
        (_overlapLayer.targets || []).forEach(function (t) {
            if (t && t.el) _cancelAnimations(t.el);
        });
        if (_overlapLayer.el && _overlapLayer.el.parentNode) {
            _overlapLayer.el.parentNode.removeChild(_overlapLayer.el);
        }
        _overlapLayer = null;
    }
    _overlapInfo = null;
    // The incoming content is hidden while it waits for its offset. Any exit
    // from the overlap path (finish, interrupt, cloak, clear, out) restores
    // it before the caller sets its own visibility.
    if (active) _setContainersHidden(false);
}

function _clearOverlapTimers() {
    _overlapTimers.forEach(function (id) { clearTimeout(id); });
    _overlapTimers = [];
}

function _playOutPlan(plan) {
    let total = 0;
    (plan || []).forEach(function (p) {
        if (p.def) {
            _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "out" });
            total = Math.max(total, _phaseDuration(p.def));
        }
        total = Math.max(total,
            _playPropertyTracks(p.el, p.anim, "transition_out"));
    });
    return total;
}

function _runIncomingOverlap(phase, changed) {
    // The offset timer starts this, so the authored phase duration is measured
    // from that moment. A later variable offset only changes the timer.
    return _runAnimation(phase, changed);
}

function _runOverlapPair(data, changed, phases, outPlan, offset, kind,
                         preview) {
    const vars = _snapshotRootThemeVars();
    const layer = _captureOverlapLayer(outPlan, phases[0]);
    // Render the incoming content now but silently: sustain and the shown
    // state must wait for the whole pair, and _renderDisplay's cancel must
    // not touch a layer that is not attached yet.
    _renderDisplay(data, true, changed, null);
    if (!preview) {
        _prevPayload = data;
        _currentKind = kind;
        _motionState = "transitioning";
    }

    let outTotal = 0;
    const incomingPhase = phases[1] === "transition_in" ? "in" : "entry";
    if (layer && _attachOverlapLayer(layer, vars)) {
        // The outgoing plan targets the clone, never the live DOM: the live
        // nodes now hold the incoming content.
        outTotal = _playOutPlan(layer.targets);
        _setContainersHidden(true);
        _overlapInfo = { offset_ms: offset, outgoing: layer.targets.length,
                         incoming: 0 };
    } else {
        // No outgoing DOM to freeze: incoming starts at 0 so the stage never
        // goes blank. No fallback animation is invented.
        offset = 0;
    }
    const token = _phaseToken;
    let inTotal = 0;

    const finish = function () {
        if (token !== _phaseToken) return;
        _removeOverlapLayer();
        if (!preview) {
            _motionState = "shown";
            _currentKind = kind;
            _publishMotion();
            _scheduleSustain(0);
        }
    };

    const startIncoming = function () {
        if (token !== _phaseToken) return;
        _setContainersHidden(false);
        const before = _animatedEls.size;
        inTotal = _runIncomingOverlap(incomingPhase, changed);
        if (_overlapInfo) {
            _overlapInfo.incoming = _animatedEls.size - before;
            if (!preview) _publishMotion();
        }
        const total = Math.max(outTotal, offset + inTotal);
        _overlapTimers.push(setTimeout(function () {
            finish();
        }, Math.max(0, total - offset)));
    };

    if (offset > 0) {
        _overlapTimers.push(setTimeout(startIncoming, offset));
    } else {
        startIncoming();
    }
    if (!preview) _publishMotion();
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
        if (p.def) {
            _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "out" });
            total = Math.max(total, _phaseDuration(p.def));
        }
        total = Math.max(total, _playPropertyTracks(p.el, p.anim, "out"));
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

// Convert a text_shadow value to CSS. Structured shadows omit `spread`:
// the text-shadow grammar has no spread component, and a fourth length
// would invalidate the whole declaration. A shared reference is left for
// core.theme_shared; block text shadows are not expanded there today, so
// it paints nothing rather than the literal "[object Object]".
function _textShadowCss(value) {
    if (value == null) return "";
    if (typeof value === "string") {
        const text = value.trim();
        return text ? (_shadowIsNone(text) ? "none" : text) : "";
    }
    if (typeof value === "object") {
        if ("shared" in value) return "";
        const length = (v) => {
            if (v == null || v === "") return "0px";
            return typeof v === "number" ? (v + "px") : String(v);
        };
        const inset = value.inset ? "inset " : "";
        return inset + length(value.x) + " " + length(value.y) + " "
            + length(value.blur) + " "
            + (value.color || "rgba(0,0,0,0.5)");
    }
    return "";
}

// Inline style for the verse number span. Authored values win over the
// stylesheet defaults in themes.css; absent values leave CSS in charge.
function _verseNumAttrs(vn, fallbackColor) {
    vn = vn || {};
    const parts = [];
    const add = (prop, value, unit) => {
        if (value == null || value === "") return;
        parts.push(prop + ":" + (typeof value === "number" ? value + unit : String(value)));
    };
    const color = vn.color || fallbackColor;
    if (color) parts.push("color:" + color);
    add("font-size", vn.size, "px");
    add("font-weight", vn.weight, "");
    add("opacity", vn.opacity, "");
    add("line-height", vn.line_height, "");
    add("vertical-align", vn.vertical_align, "");
    add("margin-right", vn.margin_right, "px");
    return parts.length ? ' style="' + parts.join(";") + '"' : "";
}

function _verseNumBlock(theme) {
    theme = theme || _currentTheme || {};
    return _authoredBlock(themeContainer(theme), "verse_num")
        || theme.verse_num || {};
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
            verseTextContent = '<span class="verse-num"' + _verseNumAttrs(_verseNumBlock(data.theme_data)) + '>' + verseNum + '</span> ' + verseTextContent;
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
        const total = phase ? _runAnimation(phase, changed) : 0;
        _prevPayload = data;
        _motionState = "shown";
        _currentKind = data.kind || "other";
        _publishMotion();
        _scheduleSustain(total);
    }
}

// ─── Motion state ─────────────────────────────────────────────────
// Mirrors core/motion_state.py. The renderer only executes actions; the
// ordering/coverage policy comes from the Python state machine and the
// theme's `motion` object.
let _motionState = "empty";
let _motionCovered = "empty";
let _sustainTimer = null;
let _sustainToken = 0;
let _currentKind = "other";
let _lastPlan = null;
// A display payload that arrives without a content kind is treated as
// "other" (the OUT/IN path, never a silent scripture transition). The flag
// survives until the next labelled payload or a clear so the warning is not
// lost while that content is on screen.
let _kindUnlabelled = false;

// Page-side observable state (tests + the optional ?debug=1 readout).
window.__rcMotionState = {
    state: "empty", covered: "empty", kind: "other",
    unlabelled: false, plan: null
};

function _publishMotion() {
    if (typeof window === "undefined") return;
    window.__rcMotionState = {
        state: _motionState,
        covered: _motionCovered,
        kind: _currentKind,
        unlabelled: _kindUnlabelled,
        plan: _lastPlan ? {
            old: _lastPlan.old, new: _lastPlan.new,
            phases: _lastPlan.phases.slice(),
            order: _lastPlan.order || "sequential",
            offset_ms: _lastPlan.offset_ms || 0
        } : null
    };
    _updateDebug();
}

// ?debug=1 readout: last plan, kinds compared, phases and the overlap layers.
// Absent by default, so OBS and normal browser tabs are untouched.
let _debugEl = null;

function _debugEnabled() {
    try {
        return typeof location !== "undefined"
            && /(?:^|[?&])debug=1(?:&|$)/.test(location.search || "");
    } catch (e) {
        return false;
    }
}

function _updateDebug() {
    if (!_debugEnabled() || typeof document === "undefined"
        || !document.createElement || !document.body) return;
    if (!_debugEl) {
        _debugEl = document.createElement("div");
        _debugEl.id = "rc-motion-debug";
        _debugEl.style.cssText = "position:fixed;left:8px;bottom:8px;"
            + "z-index:2147483647;padding:4px 6px;background:rgba(0,0,0,.65);"
            + "color:#fff;font:11px/1.4 monospace;white-space:pre;"
            + "pointer-events:none;";
        document.body.appendChild(_debugEl);
    }
    const plan = _lastPlan;
    let text = "state " + _motionState + " | kind " + _currentKind
        + (_kindUnlabelled ? " | UNLABELLED" : "");
    if (plan) {
        text += "\n" + plan.old + " -> " + plan.new
            + "\n" + plan.phases.join(" -> ");
        if (plan.order === "overlap") {
            text += "\noverlap offset " + (plan.offset_ms || 0) + "ms";
        }
    }
    if (_overlapInfo) {
        text += "\noutgoing clone (" + _overlapInfo.outgoing
            + ") | incoming live (" + _overlapInfo.incoming + ")";
    }
    _debugEl.textContent = text;
}

// Cloak must blank the canvas background too, not just its containers.
function _setPageHidden(hidden) {
    if (typeof stage !== "undefined" && stage && stage.style) {
        stage.style.visibility = hidden ? "hidden" : "";
    }
}

function _themeMotion(theme) {
    const m = theme && theme.motion;
    return {
        in_out: (m && m.in_out) || "sequential",
        transition: (m && m.transition) || "sequential",
        sustain_when_cloaked: (m && m.sustain_when_cloaked) || "pause",
        deck_steps: (m && m.deck_steps) || "out_in"
    };
}

function _setContainersHidden(hidden) {
    if (typeof container !== "undefined" && container) {
        container.classList.toggle("hidden", !!hidden);
    }
    if (typeof document !== "undefined" && document.querySelectorAll) {
        document.querySelectorAll(".rc-dynamic-container").forEach(function (el) {
            // The frozen outgoing layer keeps its own copy visible.
            if (el.closest && el.closest(".rc-overlap-layer")) return;
            el.classList.toggle("hidden", !!hidden);
        });
    }
    // A cloaked container must take its border shadow with it.
    _syncBorderShadowVisibility();
}

function _sustainTargets(theme) {
    const plan = [];
    if (!theme || theme.schema_version !== 2) return plan;
    _animationTargets(theme).forEach(function (t) {
        if (!t.anim) return;
        const tracks = _hasPropertyTracks(t.anim, "sustain");
        if (!t.anim.sustain && !tracks) return;
        const def = t.anim.sustain
            ? _resolveSlotDef(t.anim.sustain, theme.animations || {}, "in") : null;
        if (def || tracks) {
            plan.push({ el: t.el, def: def, kind: t.kind, anim: t.anim });
        }
    });
    return plan;
}

function _stopSustain() {
    _sustainToken++;
    if (_sustainTimer) {
        clearTimeout(_sustainTimer);
        _sustainTimer = null;
    }
}

function _sustainAllowed(theme) {
    if (_motionState === "shown") return true;
    return _motionState === "cloaked"
        && _motionCovered === "shown"
        && _themeMotion(theme).sustain_when_cloaked === "run";
}

function _startSustain(theme) {
    _stopSustain();
    theme = theme || _currentTheme;
    if (_reducedMotion() || !_sustainAllowed(theme)) return;
    const plan = _sustainTargets(theme);
    if (!plan.length) return;
    // One infinite animation per target: no timer loop, no frame gap
    // between iterations. _cancelAllAnimations() ends them.
    plan.forEach(function (p) {
        if (p.def) {
            _playElementAnimation(p.el, p.def, {
                kind: p.kind, phase: "sustain", iterations: Infinity
            });
        }
        _playPropertyTracks(p.el, p.anim, "sustain");
    });
}

function _scheduleSustain(delay) {
    _stopSustain();
    if (delay > 0) {
        const token = _sustainToken;
        _sustainTimer = setTimeout(function () {
            _sustainTimer = null;
            if (token !== _sustainToken) return;
            _startSustain(_currentTheme);
        }, delay);
        return;
    }
    _startSustain(_currentTheme);
}

function _motionAllChanged() {
    return { any: true, text: true, reference: true,
             translation: true, title: true };
}

function handlePayload(data, silent) {
    if (data.action === "cloak") {
        _cancelAllAnimations();
        _stopSustain();
        _motionCovered = _motionState === "out" ? "out"
            : (_motionState === "empty" ? "empty" : "shown");
        _motionState = "cloaked";
        _setContainersHidden(true);
        _setPageHidden(true);
        _publishMotion();
        // `run` keeps sustain alive behind the cloak; the default `pause`
        // leaves it stopped until uncloak.
        if (_motionCovered === "shown"
            && _themeMotion(_currentTheme).sustain_when_cloaked === "run") {
            _startSustain(_currentTheme);
        }
        return;
    }

    if (data.action === "uncloak") {
        if (_motionState !== "cloaked") return;
        const reveal = data.reveal !== false;
        if (reveal) {
            _motionState = "shown";
            _setContainersHidden(false);
            _setPageHidden(false);
            _scheduleSustain(0);
        } else {
            _motionState = _motionCovered === "out" ? "out" : "empty";
            _setContainersHidden(true);
            _setPageHidden(true);
        }
        _publishMotion();
        return;
    }

    if (data.action === "out") {
        if (_motionState === "cloaked" || _motionState === "out"
            || _motionState === "empty" || !_prevPayload) return;
        _cancelAllAnimations();
        _stopSustain();
        const theme = _currentTheme || _prevPayload.theme_data;
        const plan = _collectExit(theme);
        plan.forEach(function (p) {
            if (p.def) {
                _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "out" });
            }
            _playPropertyTracks(p.el, p.anim, "out");
        });
        _motionState = "out";
        if (!plan.length) _setContainersHidden(true);
        _publishMotion();
        return;
    }

    if (data.action === "in") {
        if (_motionState !== "out") return;
        _cancelAllAnimations();
        _setContainersHidden(false);
        _motionState = "entering";
        const total = _runAnimation("entry", _motionAllChanged());
        _motionState = "shown";
        _scheduleSustain(total);
        _publishMotion();
        return;
    }

    if (data.action === "clear") {
        _cancelAllAnimations();
        _stopSustain();
        _motionState = "empty";
        _motionCovered = "empty";
        _currentKind = "other";
        _kindUnlabelled = false;
        _publishMotion();
        if (silent) {
            container.classList.add("hidden");
            container.style.animation = "";
            if (typeof document !== "undefined" && document.querySelectorAll) {
                document.querySelectorAll(".rc-dynamic-container").forEach(el => el.classList.add("hidden"));
            }
            _syncBorderShadowVisibility();
            _prevPayload = null;
            return;
        }
        _runExitAnimation(() => {
            container.classList.add("hidden");
            container.style.animation = "";
            if (typeof document !== "undefined" && document.querySelectorAll) {
                document.querySelectorAll(".rc-dynamic-container").forEach(el => el.classList.add("hidden"));
            }
            _syncBorderShadowVisibility();
            _cancelAllAnimations();
        });
        _prevPayload = null;
        return;
    }

    if (data.action !== "display") return;

    const previousKind = _currentKind;
    // Pairing rule: an unlabelled payload is "other", so it plays OUT/IN
    // instead of borrowing the scripture transition path. The warning makes
    // a sender that forgot to label visible in the console.
    const declaredKind = typeof data.kind === "string" ? data.kind.trim() : "";
    _kindUnlabelled = !declaredKind || !!data.kind_missing;
    if (_kindUnlabelled) {
        console.warn("RhemaCast display payload has no kind; "
            + "treating it as other (OUT/IN):", data.ref || data.reference || "");
    }
    _currentKind = declaredKind || "other";

    if (_motionState === "cloaked") {
        // Content staged behind the cloak: update the DOM silently so the
        // eventual uncloak reveals it with no entry.
        _renderDisplay(data, true, _changedSources(_prevPayload, data), null);
        _prevPayload = data;
        _motionCovered = "shown";
        // _renderDisplay always shows the container; the cloak must win.
        _setContainersHidden(true);
        _setPageHidden(true);
        _publishMotion();
        return;
    }

    const previous = _prevPayload;
    const changed = _changedSources(previous, data);
    const kind = _currentKind;
    const oldKind = previous ? (previous.kind || previousKind || "other")
                             : previousKind;

    // A theme can make Prev/Next inside one deck instant. Only the OUT/IN
    // pair is affected; scripture pairs and cross-deck jumps keep the rule.
    const motion = _themeMotion(data.theme_data || _currentTheme);
    const sameDeck = !!(previous && previous.action === "display"
        && previous.deck_id != null && data.deck_id != null
        && String(previous.deck_id) === String(data.deck_id));
    const deckInstant = sameDeck && oldKind !== "scripture"
        && kind !== "scripture" && motion.deck_steps === "instant";
    if (deckInstant) {
        _cancelAllAnimations();
        _lastPlan = { old: oldKind, new: kind, phases: [] };
        _publishMotion();
    }

    // Pairing rule: scripture -> scripture plays transition out/in; every
    // other pairing plays OUT then IN. No fallback between the two.
    if (!silent && previous && previous.action === "display" && changed.any
        && _motionState !== "out" && !deckInstant) {
        _cancelAllAnimations();
        const oldTheme = _currentTheme || previous.theme_data;
        const scripturePair = oldKind === "scripture" && kind === "scripture";
        const phases = scripturePair
            ? ["transition_out", "transition_in"]
            : ["out", "in"];
        const pairMode = scripturePair ? motion.transition : motion.in_out;
        const overlap = pairMode === "overlap" && !_reducedMotion()
            && _overlapSupported(data.theme_data || _currentTheme)
            && _overlapSupported(oldTheme);
        const offset = overlap
            ? _overlapOffset(data.theme_data || _currentTheme) : 0;
        _lastPlan = { old: oldKind, new: kind, phases: phases.slice(),
                      order: overlap ? "overlap" : "sequential",
                      offset_ms: offset };
        _publishMotion();
        // Reduced motion skips the wait entirely: swap now and suppress
        // the incoming phase. Normal playback keeps the authored timing.
        const outPlan = _reducedMotion() ? [] : (phases[0] === "transition_out"
            ? _collectTransitionOut(oldTheme, changed)
            : _collectExit(oldTheme));
        if (overlap && outPlan.length) {
            _runOverlapPair(data, changed, phases, outPlan, offset, kind);
            return;
        }
        let total = 0;
        outPlan.forEach(function (p) {
            if (p.def) {
                _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "out" });
                total = Math.max(total, _phaseDuration(p.def));
            }
            total = Math.max(total, _playPropertyTracks(p.el, p.anim,
                phases[0] === "transition_out" ? "transition_out" : "out"));
        });
        const token = _phaseToken;
        const finish = function () {
            _renderDisplay(data, false, changed, null);
            _stopSustain();
            const inTotal = phases[1] === "transition_in"
                ? _runAnimation("in", _motionAllChanged())
                : _runAnimation("entry", _motionAllChanged());
            _motionState = "shown";
            _currentKind = kind;
            _publishMotion();
            _scheduleSustain(inTotal);
        };
        if (total > 0) {
            _phaseTimer = setTimeout(function () {
                _phaseTimer = null;
                if (token === _phaseToken) finish();
            }, total);
        } else {
            finish();
        }
        return;
    }

    // First content, a re-broadcast of the same content, or resync.
    let phase = "entry";
    if (_motionState === "out") {
        phase = "entry";
    } else if (previous && previous.action === "display") {
        phase = null;
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

// ─── Designer preview replay ────────────────────────────────────────────
// The live display still uses handlePayload().  These helpers are only used
// by the Theme Designer preview and its tests.  They deliberately reuse the
// normal render/animation functions instead of maintaining a second engine.
let _rcPreviewState = {
    phase: null, status: "idle", token: 0, animations: 0,
    targets: 0, started_at: 0, finished_at: 0
};

function previewState() {
    return Object.assign({}, _rcPreviewState);
}

function _previewPlan(plan, trackPhase) {
    let total = 0;
    (plan || []).forEach(p => {
        if (p.def) {
            _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "out" });
            total = Math.max(total, _phaseDuration(p.def));
        }
        total = Math.max(total,
            _playPropertyTracks(p.el, p.anim, trackPhase || "out"));
    });
    return total;
}

function _previewDuration(plan, trackPhase) {
    let total = 0;
    (plan || []).forEach(p => {
        total = Math.max(total, _phaseDuration(p.def));
        total = Math.max(total,
            _propertyPhaseDuration(p.el, p.anim, trackPhase || "out"));
    });
    return total;
}

function _previewStart(phase, plan) {
    const token = _phaseToken;
    Object.assign(_rcPreviewState, {
        phase: phase, status: "running", token: token,
        animations: plan.length, targets: plan.length,
        started_at: Date.now(), finished_at: 0
    });
    return token;
}

function _previewFinish(token, status) {
    if (token !== _rcPreviewState.token) return;
    _rcPreviewState.status = status || "finished";
    _rcPreviewState.finished_at = Date.now();
}

function _previewDoneAfter(token, total) {
    if (total <= 0) {
        _previewFinish(token);
        return;
    }
    setTimeout(function() { _previewFinish(token); }, total);
}

function _collectTransitionIn(theme, changed) {
    const plan = [];
    if (_reducedMotion() || !theme || !changed || !changed.any) return plan;
    const anims = theme.animations || {};
    _animationTargets(theme).forEach(t => {
        if (!t.anim) return;
        const trans = t.anim.transition;
        const tracks = _hasPropertyTracks(t.anim, "transition_in");
        if ((!trans || !trans.in) && !tracks) return;
        const relevant = (t.kind === "container" || t.kind === "body")
            ? changed.any : !!changed[t.kind];
        if (!relevant) return;
        const def = (trans && trans.in)
            ? _resolveSlotDef(trans.in, anims, "in") : null;
        if (def || tracks) {
            plan.push({ el: t.el, def: def, kind: t.kind, anim: t.anim });
        }
    });
    return plan;
}

function previewReplay(phase, current, alternate) {
    if (!current || !current.theme_data) return previewState();
    const theme = current.theme_data;
    const all = { any: true, text: true, reference: true, translation: true, title: true };
    const alternateTheme = (alternate && alternate.theme_data) || theme;
    const canOverlap = (theme.motion && theme.motion.transition === "overlap")
        && !_reducedMotion() && _overlapSupported(theme)
        && _overlapSupported(alternateTheme);

    if (phase === "entry") {
        _renderDisplay(current, true, all, null);
        const plan = _animationTargets(theme).filter(t => t.anim
            && (t.anim.entry || _hasPropertyTracks(t.anim, "entry")));
        const token = _previewStart("entry", plan);
        _runAnimation("entry", all);
        let total = 0;
        plan.forEach(p => {
            if (p.anim.entry) {
                const def = _resolveSlotDef(p.anim.entry, theme.animations || {}, "in");
                total = Math.max(total, _phaseDuration(def));
            }
            total = Math.max(total,
                _propertyPhaseDuration(p.el, p.anim, "entry"));
        });
        _previewDoneAfter(token, total);
        return previewState();
    }

    if (phase === "transition_in") {
        _renderDisplay(alternate, true, all, null);
        if (canOverlap) {
            const outPlan = _collectTransitionOut(alternateTheme, all);
            if (outPlan.length) {
                const offset = _overlapOffset(theme);
                const token = _previewStart("transition_in", outPlan);
                _runOverlapPair(
                    current, all, ["transition_out", "transition_in"],
                    outPlan, offset, current.kind || "scripture", true);
                const inPlan = _collectTransitionIn(theme, all);
                _rcPreviewState.animations = outPlan.length + inPlan.length;
                _rcPreviewState.targets = _rcPreviewState.animations;
                const total = Math.max(
                    _previewDuration(outPlan, "transition_out"),
                    offset + _previewDuration(inPlan, "transition_in"));
                _previewDoneAfter(token, total);
                return previewState();
            }
        }
        _renderDisplay(current, true, all, null);
        const plan = _collectTransitionIn(theme, all);
        const token = _previewStart("transition_in", plan);
        _runAnimation("in", all);
        _previewDoneAfter(token, _previewDuration(plan, "transition_in"));
        return previewState();
    }

    if (phase === "transition_out") {
        _renderDisplay(current, true, all, null);
        const outPlan = _collectTransitionOut(theme, all);
        if (canOverlap && outPlan.length) {
            const offset = _overlapOffset(alternateTheme);
            const token = _previewStart("transition_out", outPlan);
            _runOverlapPair(
                alternate, all, ["transition_out", "transition_in"],
                outPlan, offset, alternate.kind || "scripture", true);
            const inPlan = _collectTransitionIn(alternateTheme, all);
            _rcPreviewState.animations = outPlan.length + inPlan.length;
            _rcPreviewState.targets = _rcPreviewState.animations;
            const total = Math.max(
                _previewDuration(outPlan, "transition_out"),
                offset + _previewDuration(inPlan, "transition_in"));
            setTimeout(function() {
                // The pair render advances _phaseToken; the preview token is
                // the stable guard for this replay.
                if (token !== _rcPreviewState.token) return;
                _previewFinish(token);
                _renderDisplay(current, true, all, null);
            }, Math.max(0, total));
            return previewState();
        }
        const plan = _collectTransitionOut(theme, all);
        const token = _previewStart("transition_out", plan);
        const total = _previewPlan(plan, "transition_out");
        setTimeout(function() {
            if (token !== _phaseToken) return;
            _previewFinish(token);
            _renderDisplay(alternate, true, all, null);
            _renderDisplay(current, true, all, null);
        }, Math.max(0, total));
        return previewState();
    }

    if (phase === "sustain") {
        _renderDisplay(current, true, all, null);
        const plan = _sustainTargets(theme);
        const token = _previewStart("sustain", plan);
        let total = 0;
        plan.forEach(p => {
            if (p.def) {
                _playElementAnimation(p.el, p.def, { kind: p.kind, phase: "sustain" });
                total = Math.max(total, _phaseDuration(p.def));
            }
            total = Math.max(total,
                _playPropertyTracks(p.el, p.anim, "sustain"));
        });
        _previewDoneAfter(token, total);
        return previewState();
    }

    if (phase === "out") {
        _renderDisplay(current, true, all, null);
        const plan = _collectExit(theme);
        const token = _previewStart("out", plan);
        const total = _previewPlan(plan, "out");
        setTimeout(function() {
            if (token !== _phaseToken) return;
            _previewFinish(token);
            _renderDisplay(current, true, all, null);
        }, Math.max(0, total));
        return previewState();
    }
    return previewState();
}

window.__rcPreviewState = _rcPreviewState;
window.previewState = previewState;
window.previewReplay = previewReplay;

connect();

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
