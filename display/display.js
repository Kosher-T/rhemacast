const WS_HOST = window.location.hostname || "127.0.0.1";
const OUTPUT_ID = new URLSearchParams(window.location.search).get("output") || "1";
const WS_URL = `ws://${WS_HOST}:8765?output=${OUTPUT_ID}`;
const RECONNECT_DELAY = 2000;

let socket = null;
let isConnecting = false;
let _prevPayload = null;
let _animStyleEl = null;

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
        "--rc-text-font-family",
        "--rc-ref-color", "--rc-ref-size", "--rc-ref-weight",
        "--rc-ref-text-transform", "--rc-ref-letter-spacing",
        "--rc-ref-font-family",
        "--rc-translation-color", "--rc-translation-margin-left",
        "--rc-verse-num-color", "--rc-verse-num-font-family"
    ];
    props.forEach(p => root.style.removeProperty(p));
}

function applyTheme(theme) {
    if (!theme) return;
    resetTheme();
    const root = document.documentElement;
    const c = theme.container || {};
    const t = theme.text || {};
    const r = theme.reference || {};
    const tr = theme.translation || {};
    const b = theme.body || {};

    // Container
    if (c.background)        root.style.setProperty("--rc-container-bg", c.background);
    if (c.border)            root.style.setProperty("--rc-container-border", c.border);
    if (c.border_radius)     root.style.setProperty("--rc-border-radius", c.border_radius);
    if (c.box_shadow)        root.style.setProperty("--rc-container-shadow", c.box_shadow);
    if (c.backdrop_filter)   root.style.setProperty("--rc-backdrop-filter", c.backdrop_filter);
    if (c.padding)           root.style.setProperty("--rc-padding", c.padding);
    if (c.max_width)         root.style.setProperty("--rc-max-width", c.max_width);
    if (c.min_width)         root.style.setProperty("--rc-min-width", c.min_width);
    if (c.width)             root.style.setProperty("--rc-width", c.width);
    if (c.height)            root.style.setProperty("--rc-height", c.height);
    if (c.display)           root.style.setProperty("--rc-container-display", c.display);
    if (c.flex_direction)    root.style.setProperty("--rc-container-flex-direction", c.flex_direction);
    if (c.justify_content)   root.style.setProperty("--rc-container-justify-content", c.justify_content);
    if (c.align_items)       root.style.setProperty("--rc-container-align-items", c.align_items);

    // Body
    if (b.vertical_align) root.style.setProperty("--rc-vertical-align", b.vertical_align);
    if (b.padding_bottom) root.style.setProperty("--rc-padding-bottom", b.padding_bottom);

    // Text
    if (t.color)        root.style.setProperty("--rc-text-color", t.color);
    if (t.size)         root.style.setProperty("--rc-text-size", t.size);
    if (t.weight)       root.style.setProperty("--rc-text-weight", t.weight);
    if (t.line_height)  root.style.setProperty("--rc-text-line-height", t.line_height);
    if (t.text_shadow)  root.style.setProperty("--rc-text-shadow", t.text_shadow);
    if (t.letter_spacing) root.style.setProperty("--rc-text-letter-spacing", t.letter_spacing);
    if (t.margin_bottom) root.style.setProperty("--rc-text-margin-bottom", t.margin_bottom);
    if (t.min_size)     root.style.setProperty("--rc-text-min-size", t.min_size);
    if (t.max_size)     root.style.setProperty("--rc-text-max-size", t.max_size);
    if (t.font_family)  root.style.setProperty("--rc-text-font-family", t.font_family);

    // Reference
    if (r.color)        root.style.setProperty("--rc-ref-color", r.color);
    if (r.size)         root.style.setProperty("--rc-ref-size", r.size);
    if (r.weight)       root.style.setProperty("--rc-ref-weight", r.weight);
    if (r.text_transform) root.style.setProperty("--rc-ref-text-transform", r.text_transform);
    if (r.letter_spacing) root.style.setProperty("--rc-ref-letter-spacing", r.letter_spacing);
    if (r.font_family)  root.style.setProperty("--rc-ref-font-family", r.font_family);

    // Translation
    if (tr.color)       root.style.setProperty("--rc-translation-color", tr.color);
    if (tr.margin_left) root.style.setProperty("--rc-translation-margin-left", tr.margin_left);

    // Verse number
    const vn = theme.verse_num || {};
    if (vn.color)        root.style.setProperty("--rc-verse-num-color", vn.color);
    if (vn.font_family)  root.style.setProperty("--rc-verse-num-font-family", vn.font_family);

    autoFitText();
    _applyContainers(theme);
}

function extractVerseNumber(reference) {
    // Extract verse number from formats like "ESTHER 5:9" or "ESTHER 5:9 GSV"
    const match = reference.match(/(\d+:\d+)$/);
    if (match) {
        return match[1].split(':').pop(); // Get just the verse number
    }
    return null;
}

function autoFitText() {
    const rootStyle = getComputedStyle(document.documentElement);
    const containerH = parseInt(rootStyle.getPropertyValue('--rc-height'));

    if (!containerH || isNaN(containerH)) {
        verseText.style.fontSize = '';
        return;
    }

    if (!verseText.textContent.trim()) return;

    // Get min/max font size from theme (defaults: min 40px, max 55px for fullscreen)
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

// ─── Container (absolute positioning) support ───────────────────────────────
let _activeContainers = null;

function _applyContainers(theme) {
    const ct = theme.containers;
    const verseContent = document.getElementById("verse-content");
    const ctText = document.getElementById("ct-text");
    const ctRef = document.getElementById("ct-reference");
    const ctTrans = document.getElementById("ct-translation");

    if (!ct) {
        // No containers — flex mode
        _activeContainers = null;
        verseContent.style.display = "";
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

    // Absolute mode
    _activeContainers = ct;
    verseContent.style.display = "none";

    // Make container fill the viewport (1920x1080 virtual)
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

    // Apply element-specific styles
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

    // Text
    const ctTextInner = document.querySelector("#ct-text > *");
    if (ctTextInner) {
        let html = data.text || "";
        if (verseNum) html = '<span class="verse-num">' + verseNum + '</span> ' + html;
        ctTextInner.innerHTML = html;
    }

    // Reference
    const ctRefInner = document.querySelector("#ct-reference > *");
    if (ctRefInner) ctRefInner.innerHTML = refText;

    // Translation
    const ctTransInner = document.querySelector("#ct-translation > *");
    if (ctTransInner) ctTransInner.innerHTML = data.translation || "";
}

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

const ANIM_EASINGS = {
    "ease-out":     "cubic-bezier(0.16, 1, 0.3, 1)",
    "ease-in":      "cubic-bezier(0.55, 0.085, 0.68, 0.53)",
    "ease-in-out":  "cubic-bezier(0.65, 0, 0.35, 1)",
    "linear":       "linear",
    "spring":       "cubic-bezier(0.34, 1.56, 0.64, 1)",
    "smooth":       "cubic-bezier(0.25, 0.1, 0.25, 1)",
};

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
    if (!type || type === "none" || !el) return;
    const kfName = `rc-${type}`;
    const dur = (durationMs || 600) + "ms";
    const ease = ANIM_EASINGS[easing] || ANIM_EASINGS["ease-out"];
    el.style.animation = `${kfName} ${dur} ${ease} forwards`;
    el.addEventListener("animationend", () => { el.style.animation = ""; }, { once: true });
}

function _runAnimation(data, phase) {
    const anims = data.theme_data && data.theme_data.animations;
    if (!anims) return;
    _injectAnimStyle();
    if (phase === "display_enter" && anims.display_enter) {
        const a = anims.display_enter;
        _applyAnimation(container, a.type, a.duration_ms, a.easing);
    } else if (phase === "between_slides" && anims.between_slides) {
        const a = anims.between_slides;
        _applyAnimation(container, a.in_type, a.duration_ms, a.easing);
    }
}

function _runExitAnimation(callback) {
    // Check if the previous payload had exit animation
    const anims = _prevPayload && _prevPayload.theme_data && _prevPayload.theme_data.animations;
    if (!anims || !anims.display_exit || !anims.display_exit.type) {
        callback();
        return;
    }
    const a = anims.display_exit;
    _injectAnimStyle();
    const kfName = `rc-${a.type}`;
    const dur = (a.duration_ms || 400) + "ms";
    const ease = ANIM_EASINGS[a.easing] || ANIM_EASINGS["ease-out"];
    container.style.animation = `${kfName} ${dur} ${ease} forwards`;
    container.addEventListener("animationend", () => {
        container.style.animation = "";
        callback();
    }, { once: true });
}

function handlePayload(data) {
    if (data.action === "clear") {
        _runExitAnimation(() => {
            container.classList.add("hidden");
            container.style.animation = "";
        });
        _prevPayload = null;
        return;
    }
    
    if (data.action === "display") {
        const isTransition = _prevPayload && _prevPayload.action === "display";
        // Update scripture text
        if (data.text) {
            let verseTextContent = data.text;
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
        
        // Update reference and translation as separate elements
        if (data.reference) {
            verseRefText.innerHTML = data.reference;
        } else if (data.book && data.chapter && data.verse) {
            verseRefText.innerHTML = data.book + " " + data.chapter + ":" + data.verse;
        }
        
        if (data.translation) {
            verseRefTranslation.innerHTML = data.translation;
        }
        
        // Legacy: if only ref is provided (no reference/translation), parse it
        if (!data.reference && !data.translation && data.ref) {
            const m = data.ref.match(/^\[([^\]]+)\]\s*(.+)$/);
            if (m) {
                verseRefTranslation.innerHTML = m[1];
                verseRefText.innerHTML = m[2];
            } else {
                verseRefText.innerHTML = data.ref;
            }
        }
        
        // Apply theme (full theme dict or just name for CSS class fallback)
        if (data.theme_data) {
            applyTheme(data.theme_data);
            document.body.className = "";
        } else if (data.theme) {
            document.body.className = "theme-" + data.theme;
        }
        
        // Show
        container.classList.remove("hidden");
        autoFitText();
        _populateContainers(data);

        // Play enter animation
        if (isTransition) {
            _runAnimation(data, "between_slides");
        } else {
            _runAnimation(data, "display_enter");
        }
        _prevPayload = data;
    }
}

// Initialize connection
connect();
