const WS_HOST = window.location.hostname || "127.0.0.1";
const WS_URL = `ws://${WS_HOST}:8765`;
const RECONNECT_DELAY = 2000;

let socket = null;
let isConnecting = false;

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
        "--rc-ref-color", "--rc-ref-size", "--rc-ref-weight",
        "--rc-ref-text-transform", "--rc-ref-letter-spacing",
        "--rc-translation-color", "--rc-translation-margin-left"
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

    // Reference
    if (r.color)        root.style.setProperty("--rc-ref-color", r.color);
    if (r.size)         root.style.setProperty("--rc-ref-size", r.size);
    if (r.weight)       root.style.setProperty("--rc-ref-weight", r.weight);
    if (r.text_transform) root.style.setProperty("--rc-ref-text-transform", r.text_transform);
    if (r.letter_spacing) root.style.setProperty("--rc-ref-letter-spacing", r.letter_spacing);

    // Translation
    if (tr.color)       root.style.setProperty("--rc-translation-color", tr.color);
    if (tr.margin_left) root.style.setProperty("--rc-translation-margin-left", tr.margin_left);

    autoFitText();
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

function handlePayload(data) {
    if (data.action === "clear") {
        container.classList.add("hidden");
        return;
    }
    
    if (data.action === "display") {
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
    }
}

// Initialize connection
connect();
